"""Canonical asynchronous run application use case.

``AgentService`` owns process resources such as the thread pool and exposes
the historical facade methods.  This module owns the domain-neutral async
lifecycle: submission/idempotency, worker execution, SQLite claim/recovery,
memory-mode bookkeeping, bounded polling evidence, and artifact recovery.

The interface is intentionally small at the seam.  Runtime selection,
workflow normalization, and synchronous execution are injected ports, so the
module does not know about GIS, a particular planner, or a transport.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Dict, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.failure_contract import build_failure_evidence
from agent.domain_routing_evidence import (
    DomainRoutingEvidenceError,
    bind_domain_routing_evidence,
    normalize_domain_routing_evidence,
    routing_evidence_identity,
    unavailable_domain_routing_evidence,
)
from agent.models import AgentRunResult, RunStatus
from agent.runtime_context import assert_runtime_context_compatible
from agent.service_async import (
    async_event as _async_event,
    async_fingerprint as _async_fingerprint,
    async_response as _async_response,
    async_status as _async_status,
    build_async_observability as _build_async_observability,
    build_async_result_evidence as _build_async_result_evidence,
    failure_category_for as _failure_category,
    normalize_async_result_evidence as _normalize_async_result_evidence,
    unavailable_async_result_evidence as _unavailable_async_result_evidence,
)
from agent.service_format import result_type as _result_type
from agent.service_sessions import async_job_payload as _async_job_payload
from agent.trace_formatter import format_trace
from agent.evidence_registry import normalize_evidence_registry
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from result_contract import build_lineage_index, build_result_contract


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


def _canonical_result(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Preserve a previously normalized public Result envelope."""
    candidate = payload.get("result")
    if not isinstance(candidate, Mapping):
        return None
    try:
        return normalize_result_contract(candidate)
    except (NestedSchemaError, TypeError, ValueError):
        return None


class AsyncApplication:
    """Own the complete async run use case behind a compact application seam.

    The injected ``submit_job`` callback is the only executor port.  It keeps
    thread-pool construction and shutdown in the resource-owning facade while
    allowing this module to define when and why work is scheduled.
    """

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        memory_result_provider: Callable[[str], Any],
        run_provider: Callable[..., Dict[str, Any]],
        domain_id_provider: Callable[[str, str], str],
        resolved_domain_id: Callable[[], Optional[str]],
        configured_domain_id: Callable[[], Optional[str]],
        normalize_workflow: Callable[[Any, str, str], Dict[str, Any]],
        submission_runtime_context: Callable[[str, str], Optional[Dict[str, Any]]],
        runtime_context_provider: Callable[[str, str], Optional[Dict[str, Any]]],
        process_is_alive: Callable[[int], bool],
        submit_job: Callable[[Callable[[Dict[str, Any]], None], Dict[str, Any]], Any],
        worker_count: int,
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._runtime_provider = runtime_provider
        self._memory_result_provider = memory_result_provider
        self._run_provider = run_provider
        self._domain_id_provider = domain_id_provider
        self._resolved_domain_id = resolved_domain_id
        self._configured_domain_id = configured_domain_id
        self._normalize_workflow = normalize_workflow
        self._submission_runtime_context = submission_runtime_context
        self._runtime_context = runtime_context_provider
        self._process_is_alive = process_is_alive
        self._submit_job = submit_job
        self.worker_count = int(worker_count)

    @property
    def _jobs(self) -> Dict[str, Dict[str, Any]]:
        return self._state.jobs_view

    @property
    def _lock(self):
        return self._state.jobs_lock

    def submit(self, **kwargs: Any) -> Dict[str, Any]:
        """Accept one idempotent async request and schedule at most one job."""
        request = kwargs.get("request", "")
        session_id = kwargs.get("session_id", "default")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        kwargs = dict(kwargs)
        planner = kwargs.get("planner", "rule")
        backend = kwargs.get("backend", "memory")
        kwargs["workflow"] = self._normalize_workflow(
            kwargs.get("workflow"), planner, backend
        )
        run_id = kwargs.get("run_id")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        idempotency_key = kwargs.get("idempotency_key")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string")
        self._state.cost.check_budget(session_id)

        domain_id = self._domain_id_provider(planner, backend)
        routing_evidence = (
            normalize_domain_routing_evidence(
                kwargs.get("_domain_routing_evidence"),
                expected_domain_id=domain_id,
                strict=True,
            )
            if kwargs.get("_domain_routing_evidence") is not None
            else unavailable_domain_routing_evidence()
        )
        kwargs["_domain_routing_evidence"] = routing_evidence
        kwargs["domain_id"] = domain_id
        kwargs["runtime_context"] = self._submission_runtime_context(planner, backend)
        job_payload = _async_job_payload(kwargs)
        if run_id:
            idempotency_key = idempotency_key or "run_id:" + run_id.strip()
        else:
            idempotency_key = idempotency_key or _async_fingerprint(job_payload)
            run_id = str(uuid.uuid4())
        job_payload["run_id"] = run_id
        if routing_evidence.get("available") is True:
            job_payload["domain_routing_evidence"] = bind_domain_routing_evidence(
                routing_evidence,
                run_id=run_id,
                domain_id=domain_id,
            )

        early = None  # (run_id, status, reused), built before polling evidence.
        with self._lock:
            if self._state.persistent:
                existing_any = self._state.get_run(run_id)
                existing_domain = (
                    getattr(existing_any, "domain_id", None)
                    or self._resolved_domain_id()
                    or self._configured_domain_id()
                    or "gis"
                ) if existing_any is not None else None
                if existing_any is not None and existing_domain != domain_id:
                    raise ValueError("run_id belongs to another domain: " + str(run_id))
                existing_result = self._state.get_run(run_id, domain_id=domain_id)
                if existing_result is not None and not self._state.async_job(
                    run_id, domain_id=domain_id
                ):
                    if routing_evidence_identity(
                        getattr(existing_result, "domain_routing_evidence", None)
                    ) != routing_evidence_identity(job_payload.get("domain_routing_evidence")):
                        raise DomainRoutingEvidenceError(
                            "run_id conflicts with domain routing identity",
                            code="domain_routing_evidence_idempotency_conflict",
                        )
                    early = (run_id, existing_result.status.value, True)
                else:
                    job = self._state.create_async_job(
                        idempotency_key, run_id, job_payload
                    )
                    created = bool(job.pop("created", False))
                    if not created:
                        existing_payload = (
                            job.get("payload")
                            if isinstance(job.get("payload"), dict)
                            else {}
                        )
                        existing_domain = (
                            existing_payload.get("domain_id")
                            or self._resolved_domain_id()
                            or self._configured_domain_id()
                            or "gis"
                        )
                        if existing_domain != domain_id:
                            raise ValueError("idempotency_key belongs to another domain")
                        if routing_evidence_identity(
                            existing_payload.get("domain_routing_evidence")
                        ) != routing_evidence_identity(
                            job_payload.get("domain_routing_evidence")
                        ):
                            raise DomainRoutingEvidenceError(
                                "idempotency_key conflicts with domain routing identity",
                                code="domain_routing_evidence_idempotency_conflict",
                            )
                        self._ensure_run_snapshot(job)
                        early = (
                            job["run_id"],
                            _async_status(self._state.state_store, job),
                            True,
                        )
                    else:
                        self._state.save_run(
                            AgentRunResult(
                                run_id=run_id,
                                status=RunStatus.PLANNING,
                                request=request,
                                session_id=session_id,
                                domain_id=domain_id,
                                domain_routing_evidence=job_payload.get(
                                    "domain_routing_evidence"
                                ),
                                runtime_context=job_payload.get("runtime_context"),
                                workflow=job_payload.get("workflow"),
                            )
                        )
                        if not self._state.claim_async_job(run_id, os.getpid()):
                            # The insert and claim are separate store seams. A
                            # concurrent worker may win the claim; submission
                            # is still the first accepted request.
                            early = (run_id, "QUEUED", False)
                        else:
                            self._schedule(job_payload)
            else:
                job = self._jobs.get(idempotency_key)
                if job is not None:
                    existing_payload = (
                        job.get("payload") if isinstance(job.get("payload"), dict) else {}
                    )
                    if routing_evidence_identity(
                        existing_payload.get("domain_routing_evidence")
                    ) != routing_evidence_identity(
                        job_payload.get("domain_routing_evidence")
                    ):
                        raise DomainRoutingEvidenceError(
                            "idempotency_key conflicts with domain routing identity",
                            code="domain_routing_evidence_idempotency_conflict",
                        )
                    early = (job["run_id"], job["status"], True)
                else:
                    submitted_at = time.time()
                    job = {
                        "run_id": run_id,
                        "payload": job_payload,
                        "status": "QUEUED",
                        "created_at": submitted_at,
                        "started_at": None,
                        "finished_at": None,
                        "queue_wait_ms": None,
                        "run_duration_ms": None,
                        "failure_category": None,
                        "recovery_count": 0,
                        "cancel_requested_at": None,
                        "last_event": "submitted",
                    }
                    self._jobs[idempotency_key] = job
                    self._schedule(job_payload)
        if early is not None:
            # Polling evidence re-enters the memory lock; never build it while
            # holding that non-reentrant lock.
            return self.submission_response(early[0], early[1], early[2])
        return self.submission_response(run_id, "QUEUED", False)

    def _schedule(self, payload: Dict[str, Any]) -> None:
        self._submit_job(self.run_job, payload)

    def run_job(self, job_payload: Dict[str, Any]) -> None:
        """Execute one claimed payload and make worker failures durable."""
        run_id = job_payload["run_id"]
        kwargs = dict(job_payload)
        kwargs.pop("run_id", None)
        domain_id = kwargs.pop("domain_id", None) or self._resolved_domain_id()
        runtime_context = kwargs.pop("runtime_context", None)
        routing_evidence = kwargs.pop("domain_routing_evidence", None)
        completed = False
        failure_category = None
        self._mark_started(run_id)
        try:
            if runtime_context is not None:
                current_context = self._runtime_context(
                    kwargs.get("planner", "rule"), kwargs.get("backend", "memory")
                )
                if current_context is not None:
                    assert_runtime_context_compatible(runtime_context, current_context)
            payload = self._run_provider(
                run_id=run_id,
                _force_run_id=True,
                _async_requested=True,
                _domain_routing_evidence=(
                    routing_evidence
                    if isinstance(routing_evidence, Mapping)
                    and routing_evidence.get("available") is True
                    else None
                ),
                **kwargs,
            )
            status = str(payload.get("status") or "FAILED")
            completed = True
        except Exception as exc:
            status = "FAILED"
            failure_category = _failure_category(status, str(exc), source="worker")
            if self._state.persistent:
                result = self._state.get_run(run_id, domain_id=domain_id)
                if result is None:
                    result = AgentRunResult(
                        run_id=run_id,
                        status=RunStatus.FAILED,
                        request=str(kwargs.get("request") or ""),
                        session_id=kwargs.get("session_id"),
                        domain_id=domain_id,
                        domain_routing_evidence=job_payload.get(
                            "domain_routing_evidence"
                        ),
                        runtime_context=runtime_context,
                        error=str(exc),
                        error_category=failure_category,
                        error_code=getattr(exc, "code", None),
                    )
                elif result.status in {
                    RunStatus.CREATED,
                    RunStatus.PLANNING,
                    RunStatus.EXECUTING,
                }:
                    result.status = RunStatus.FAILED
                    result.error = str(exc)
                    result.error_category = failure_category
                    result.error_code = getattr(exc, "code", None)
                result.failure = build_failure_evidence(
                    status=result.status.value,
                    category=result.error_category or failure_category,
                    code=result.error_code,
                    retryable=getattr(exc, "retryable", None),
                )
                self._state.save_run(result)
        if self._state.persistent and not completed:
            self._state.finish_async_job(run_id, status, os.getpid(), failure_category)
        elif not self._state.persistent:
            self._finish_memory_job(run_id, status, failure_category)

    def finalize_job(self, payload: Dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        status = str(payload.get("status") or "FAILED")
        failure_category = _failure_category(status, payload.get("error"))
        if not self._state.persistent:
            self._finish_memory_job(run_id, status, failure_category)
            return
        job = self._state.async_job(
            run_id, domain_id=self._resolved_domain_id()
        )
        if job and job.get("owner_pid") == os.getpid():
            self._state.finish_async_job(
                run_id, status, os.getpid(), failure_category
            )

    def recover(self) -> int:
        """Claim orphaned SQLite jobs and submit them to the current worker."""
        if not self._state.persistent:
            return 0
        recovered = 0
        for job in self._state.recover_async_jobs(
            os.getpid(), domain_id=self._configured_domain_id()
        ):
            run_id = job["run_id"]
            owner_pid = job.get("owner_pid")
            if owner_pid and owner_pid != os.getpid() and self._process_is_alive(owner_pid):
                continue
            if not self._state.claim_async_job(
                run_id,
                os.getpid(),
                recover=True,
                previous_owner_pid=owner_pid,
            ):
                continue
            self._schedule(job["payload"])
            recovered += 1
        return recovered

    def _ensure_run_snapshot(self, job: Dict[str, Any]) -> None:
        """Close the idempotent-submit window before polling starts."""
        if not self._state.persistent or not isinstance(job, dict):
            return
        if str(job.get("status") or "") not in {
            "QUEUED",
            "RUNNING",
            "CANCEL_REQUESTED",
        }:
            return
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        self._state.ensure_run_snapshot(
            AgentRunResult(
                run_id=str(job.get("run_id") or ""),
                status=RunStatus.PLANNING,
                request=str(payload.get("request") or ""),
                session_id=payload.get("session_id"),
                domain_id=(
                    payload.get("domain_id")
                    or self._resolved_domain_id()
                    or self._configured_domain_id()
                    or "gis"
                ),
                domain_routing_evidence=payload.get("domain_routing_evidence"),
                runtime_context=payload.get("runtime_context"),
                workflow=payload.get("workflow"),
            )
        )

    def _mark_started(self, run_id: str) -> None:
        if self._state.persistent:
            return
        now = time.time()
        with self._lock:
            for job in self._jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = "RUNNING"
                job["started_at"] = job.get("started_at") or now
                if job.get("queue_wait_ms") is None:
                    job["queue_wait_ms"] = max(
                        0, (now - job["created_at"]) * 1000
                    )
                job["last_event"] = "started"
                return

    def _finish_memory_job(
        self, run_id: str, status: str, failure_category: str = None
    ) -> None:
        finished_at = time.time()
        with self._lock:
            for job in self._jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = status
                job["finished_at"] = finished_at
                started_at = job.get("started_at")
                if started_at is not None:
                    job["run_duration_ms"] = max(
                        0, (finished_at - started_at) * 1000
                    )
                job["failure_category"] = failure_category
                job["last_event"] = _async_event(status)
                return

    def get_observability(self, run_id: str) -> Dict[str, Any]:
        """Return bounded lifecycle/evidence without request or error text."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        job = (
            self._state.async_job(run_id, domain_id=self._resolved_domain_id())
            if self._state.persistent
            else None
        )
        if job is None:
            with self._lock:
                job = next(
                    (item for item in self._jobs.values() if item.get("run_id") == run_id),
                    None,
                )
        if job is None:
            artifact_observation = self._artifact_observability(run_id)
            if artifact_observation is not None:
                return artifact_observation
            raise ValueError("async run not found: " + run_id)

        result = (
            self._state.get_run(run_id, domain_id=self._resolved_domain_id())
            if self._state.persistent
            else self._memory_result_provider(run_id)
        )
        lineage = None
        result_evidence = None
        if result is not None:
            result_payload = result.to_dict()
            submitted_payload = job.get("payload")
            if isinstance(submitted_payload, dict) and "spatial_context" in submitted_payload:
                result_payload["spatial_context"] = submitted_payload.get(
                    "spatial_context"
                )
            explicit_geometry = result_payload.pop("geometry_evidence", None)
            if explicit_geometry is not None:
                result_payload["_geometry_evidence"] = explicit_geometry
            result_payload["trace_summary"] = format_trace(result)
            lineage = build_lineage_index(result_payload)
            context = result_payload.get("runtime_context")
            planner = context.get("planner", "rule") if isinstance(context, dict) else "rule"
            backend = context.get("backend", "memory") if isinstance(context, dict) else "memory"
            runtime = self._runtime_provider(planner, backend)
            result_payload["result_type"] = _result_type(result_payload)
            result_contract = _canonical_result(result_payload)
            if result_contract is None:
                result_contract = build_result_contract(
                    result_payload,
                    registry=_runtime_result_registry(runtime),
                )
            artifact_ref = result_payload.get("artifact_ref")
            if not artifact_ref:
                artifact = self._artifact_store.read_run(
                    run_id, domain_id=self._resolved_domain_id()
                )
                if isinstance(artifact, dict):
                    artifact_ref = artifact.get("artifact_ref")
            result_evidence = _build_async_result_evidence(
                result_contract,
                status=result.status.value,
                artifact_ref=artifact_ref,
            )
        return _build_async_observability(
            job,
            result,
            lineage=lineage,
            result_evidence=result_evidence,
        )

    def _artifact_observability(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Rebuild async evidence when the SQLite job row is unavailable."""
        artifact = self._artifact_store.read_run(
            run_id, domain_id=self._resolved_domain_id()
        )
        if not isinstance(artifact, dict):
            return None
        is_async = bool(
            artifact.get("async_requested")
            or "async_result_evidence" in artifact
            or isinstance(artifact.get("async_observability"), dict)
        )
        if not is_async:
            return None
        status = str(artifact.get("status") or "UNKNOWN")[:32]
        evidence = artifact.get("async_result_evidence")
        if evidence is None and isinstance(artifact.get("async_observability"), dict):
            evidence = artifact["async_observability"].get("result_evidence")
        if evidence is None:
            evidence = _unavailable_async_result_evidence(
                status=status, artifact_ref=artifact.get("artifact_ref")
            )
        else:
            evidence = _normalize_async_result_evidence(
                evidence,
                status=status,
                artifact_ref=artifact.get("artifact_ref"),
            )
        artifact_registry = normalize_evidence_registry(
            artifact.get("evidence_registry")
        )
        if artifact_registry.get("available") and not (
            isinstance(evidence.get("evidence_registry"), dict)
            and evidence["evidence_registry"].get("available")
        ):
            evidence["evidence_registry"] = artifact_registry
        return _build_async_observability(
            {
                "run_id": run_id,
                "status": status,
                "payload": {},
                "recovery_count": 1,
                "last_event": "artifact_recovered",
            },
            result_evidence=evidence,
        )

    def submission_response(
        self, run_id: str, status: str, reused: bool
    ) -> Dict[str, Any]:
        response = _async_response(run_id, status, reused)
        try:
            response["async_observability"] = self.get_observability(run_id)
        except ValueError:
            pass
        return response

    def attach_observability(
        self, payload: Dict[str, Any], run_id: Optional[str]
    ) -> None:
        if not run_id:
            return
        try:
            payload["async_observability"] = self.get_observability(run_id)
        except ValueError:
            return

    def mark_cancel_requested(self, run_id: str) -> None:
        with self._lock:
            for job in self._jobs.values():
                if job.get("run_id") == run_id and job.get("status") in {
                    "QUEUED",
                    "RUNNING",
                }:
                    job["status"] = "CANCEL_REQUESTED"
                    job["cancel_requested_at"] = time.time()
                    job["last_event"] = "cancel_requested"
                    return

    def metrics(self) -> Dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())
        status_counts: Dict[str, int] = {}
        failure_categories: Dict[str, int] = {}
        queue_waits = []
        run_durations = []
        recovered_jobs = 0
        for job in jobs:
            observation = _build_async_observability(job)
            status = observation["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            category = observation.get("failure_category")
            if category:
                failure_categories[category] = failure_categories.get(category, 0) + 1
            if observation.get("queue_wait_ms") is not None:
                queue_waits.append(observation["queue_wait_ms"])
            if observation.get("run_duration_ms") is not None:
                run_durations.append(observation["run_duration_ms"])
            if observation.get("recovered"):
                recovered_jobs += 1

        def duration_summary(values):
            if not values:
                return {"count": 0, "total_ms": 0.0, "average_ms": None, "max_ms": None}
            total = sum(values)
            return {
                "count": len(values),
                "total_ms": round(total, 3),
                "average_ms": round(total / len(values), 3),
                "max_ms": round(max(values), 3),
            }

        return {
            "count": len(jobs),
            "worker_count": self.worker_count,
            "status_counts": status_counts,
            "failure_categories": failure_categories,
            "recovered_jobs": recovered_jobs,
            "queue_wait_ms": duration_summary(queue_waits),
            "run_duration_ms": duration_summary(run_durations),
        }
