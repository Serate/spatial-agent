import os
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from agent.artifact_store import ArtifactStore
from agent.cost_governance import (
    ConcurrencyLimited,
    RunTokenCapExceeded,
    extract_tokens as _extract_tokens,
)
from agent.errors import ToolError
from agent.failure_contract import build_failure_evidence, failure_from_payload
from agent.geojson_exporter import export_run_summary
from agent.provenance import build_provenance
from agent.runtime_factory import build_runtime
from agent.scenario import BuildabilityComparisonScenario, ConstrainedBuildabilityComparisonScenario
from agent.service_state import ServiceState
from agent.trace_formatter import format_trace
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from agent.models import AgentRunResult, RunStatus
from result_contract import (
    build_comparison_views,
    build_comparison_lineage,
    build_lineage_index,
    build_result_contract,
)

from agent.service_async import (
    build_async_observability as _build_async_observability,
    async_event as _async_event,
    async_fingerprint as _async_fingerprint,
    async_response as _async_response,
    async_status as _async_status,
    async_worker_count as _async_worker_count,
    as_float as _as_float,
    duration_summary as _duration_summary,
    epoch_to_iso as _epoch_to_iso,
    failure_category_for as _failure_category,
    process_is_alive as _process_is_alive,
    round_ms as _round_ms,
)
from agent.service_format import (
    _attach_error_category,
    analysis_ready_summary as _analysis_ready_summary,
    contextualize_request as _contextualize_request,
    crs_name as _crs_name,
    exported_geometry_evidence as _exported_geometry_evidence,
    format_result as _format_result,
    normalize_spatial_context as _normalize_spatial_context,
    normalize_workflow_payload as _normalize_workflow_payload,
    result_type as _result_type,
    tag_geometry_features as _tag_geometry_features,
)
from agent.service_sessions import (
    async_job_payload as _async_job_payload,
    attach_history_lineage as _attach_history_lineage,
    dedupe_run_records as _dedupe_run_records,
    memory_session_display_name as _memory_session_display_name,
    validate_session_id as _validate_session_id,
)


_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.NEEDS_CLARIFICATION,
    RunStatus.REJECTED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
}


def _runtime_result_registry(runtime):
    """Read the optional result registry from legacy/custom runtimes."""
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(
        self,
        artifact_store: ArtifactStore = None,
        state_db_path: str = None,
        runtime_factory: Callable[..., Any] = None,
    ):
        self._artifact_store = artifact_store or ArtifactStore()
        self._state_db_path = state_db_path or os.environ.get("SPATIAL_AGENT_STATE_DB")
        self._runtime_factory = runtime_factory or build_runtime
        self._state = ServiceState(
            state_db_path=self._state_db_path,
            runtime_factory=self._runtime_factory,
        )
        self._async_worker_count = _async_worker_count()
        self._async_executor = ThreadPoolExecutor(
            max_workers=self._async_worker_count, thread_name_prefix="spatial-agent"
        )
        self._recover_async_jobs()

    def start_reaper(self) -> None:
        """Start the periodic wall-clock timeout reaper (production entry points)."""
        self._state.start_reaper()

    # ------------------------------------------------------------------ #
    # Legacy state accessors: ownership lives in ServiceState; these keep
    # the facade methods readable while every mutation goes through the
    # converged state object.
    # ------------------------------------------------------------------ #

    @property
    def _state_store(self):
        return self._state.state_store

    @property
    def _conversation_store(self):
        return self._state.conversation_store

    @property
    def _runtimes(self):
        return self._state.runtimes()

    @property
    def _memory_sessions(self):
        return self._state.sessions_view

    @property
    def _memory_session_lock(self):
        return self._state.session_lock

    @property
    def _async_jobs(self):
        return self._state.jobs_view

    @property
    def _async_lock(self):
        return self._state.jobs_lock

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
        run_id: str = None,
        preview_fingerprint: str = None,
        _force_run_id: bool = False,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        workflow_context = _normalize_workflow_payload(workflow)
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        if preview_fingerprint is not None and (
            not isinstance(preview_fingerprint, str) or not preview_fingerprint.strip()
        ):
            raise ValueError("preview_fingerprint must be a non-empty string")
        if run_id is not None and not _force_run_id:
            existing = (
                self._state.get_run(run_id)
                if self._state.persistent
                else self._runtime(planner, backend).get_run(run_id)
            )
            if existing is not None:
                payload = _format_result(
                    existing,
                    _normalize_spatial_context(spatial_context),
                    result_registry=_runtime_result_registry(self._runtime(planner, backend)),
                )
                self._attach_async_observability(payload, run_id)
                return payload
        if self._state.conversation_store is not None:
            self._state.conversation_store.ensure_session(session_id)
        else:
            self._state.ensure_session(session_id)
        normalized_context = _normalize_spatial_context(spatial_context)
        cost = self._state.cost
        cost.acquire_concurrency()
        try:
            cost.check_budget(session_id)
            result = self._run_governed(
                request,
                session_id,
                planner,
                backend,
                normalized_context,
                runtime_kwargs={
                    "session_id": session_id,
                    "timeout_seconds": timeout_seconds,
                    "run_id": run_id,
                    "expected_plan_fingerprint": preview_fingerprint,
                },
                workflow_context=workflow_context,
                export_artifact=export_artifact,
                export_geojson=export_geojson,
                geojson_max_features=geojson_max_features,
            )
        finally:
            cost.release_concurrency()
        payload = result
        if isinstance(payload.get("plan_evidence"), dict) and payload["plan_evidence"].get("plan_identity"):
            payload["plan_identity"] = dict(payload["plan_evidence"]["plan_identity"])
        cost.charge(session_id, _extract_tokens(payload.get("planner_metrics")))
        try:
            cost.check_run_cap(_extract_tokens(payload.get("planner_metrics")))
        except RunTokenCapExceeded as exc:
            payload["status"] = "FAILED"
            payload["error"] = str(exc)
            payload["error_category"] = "budget"
            payload["error_code"] = "budget_exceeded"
            payload["failure"] = build_failure_evidence(
                status="FAILED",
                category="budget",
                code="budget_exceeded",
                phase="control",
            )
            if isinstance(payload.get("result"), dict):
                payload["result"]["failure"] = dict(payload["failure"])
            _attach_error_category(payload)
        return payload

    def preview(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        workflow_context = _normalize_workflow_payload(workflow)
        normalized_context = _normalize_spatial_context(spatial_context)
        cost = self._state.cost
        cost.acquire_concurrency()
        try:
            cost.check_budget(session_id)
            payload = self._runtime(planner, backend).preview(
                _contextualize_request(request, normalized_context),
                session_id=session_id,
                timeout_seconds=timeout_seconds,
                workflow=workflow_context,
            )
        finally:
            cost.release_concurrency()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        cost.charge(session_id, _extract_tokens(payload.get("planner_metrics")))
        try:
            cost.check_run_cap(_extract_tokens(payload.get("planner_metrics")))
        except RunTokenCapExceeded as exc:
            payload["status"] = "FAILED"
            payload["error"] = str(exc)
            payload["error_category"] = "budget"
        return payload

    def _run_governed(
        self,
        request: str,
        session_id: str,
        planner: str,
        backend: str,
        normalized_context: Dict[str, Any],
        *,
        runtime_kwargs: Dict[str, Any],
        workflow_context: Optional[Dict[str, Any]],
        export_artifact: bool,
        export_geojson: bool,
        geojson_max_features: int,
    ) -> Dict:
        runtime = self._runtime(planner, backend)
        if workflow_context is not None:
            runtime_kwargs["workflow"] = workflow_context
        result = runtime.run(
            _contextualize_request(request, normalized_context), **runtime_kwargs
        )
        payload = result.to_dict()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        if payload.get("failure") is None:
            failure = failure_from_payload(payload)
            if failure is not None:
                payload["failure"] = failure
                payload.setdefault("error_category", failure["category"])
                payload.setdefault("error_code", failure["code"])
                result.failure = dict(failure)
                result.error_category = payload["error_category"]
                result.error_code = payload["error_code"]
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
            result.artifact_ref = payload["artifact_ref"]
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                            dataset=(step.get("result") or {}).get("dataset"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"], payload["_geometry_evidence"] = _exported_geometry_evidence(payload["geojson_ref"])
            result.geometry_evidence = payload["_geometry_evidence"]
            result.geojson_ref = payload["geojson_ref"]
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        payload.pop("_geometry_feature_count", None)
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        if export_artifact:
            # Refresh the durable artifact so it carries the final navigational
            # references (geojson_ref, result_type, session_id) that lineage
            # navigation needs after the in-memory store is gone.
            self._artifact_store.write_run(payload)
        if self._state.persistent:
            self._state.save_run(result)
        self._attach_async_observability(payload, payload.get("run_id"))
        payload["memory_evidence"] = self._state.memory.evidence(
            str(payload.get("session_id") or "default")
        )
        # Mark the durable job terminal only after every final snapshot read
        # is complete. Pollers use this marker as the worker quiescence boundary.
        self._finalize_async_job(payload)
        return payload

    def run_async(self, **kwargs) -> Dict:
        request = kwargs.get("request", "")
        session_id = kwargs.get("session_id", "default")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        planner = kwargs.get("planner", "rule")
        backend = kwargs.get("backend", "memory")
        kwargs = dict(kwargs)
        kwargs["workflow"] = _normalize_workflow_payload(kwargs.get("workflow"))
        run_id = kwargs.get("run_id")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        idempotency_key = kwargs.get("idempotency_key")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string")
        self._state.cost.check_budget(session_id)

        job_payload = _async_job_payload(kwargs)
        if run_id:
            idempotency_key = idempotency_key or "run_id:" + run_id.strip()
        else:
            idempotency_key = idempotency_key or _async_fingerprint(job_payload)
            run_id = str(uuid.uuid4())
        job_payload["run_id"] = run_id

        early = None  # (run_id, status, reused) built under the lock, responded after it.
        with self._async_lock:
            if self._state.persistent:
                existing_result = self._state.get_run(run_id)
                if existing_result is not None and not self._state.async_job(run_id):
                    early = (run_id, existing_result.status.value, True)
                else:
                    job = self._state.create_async_job(
                        idempotency_key, run_id, job_payload
                    )
                    created = bool(job.pop("created", False))
                    if not created:
                        self._ensure_async_run_snapshot(job)
                        early = (job["run_id"], _async_status(self._state_store, job), True)
                    else:
                        self._state.save_run(
                            AgentRunResult(
                                run_id=run_id,
                                status=RunStatus.PLANNING,
                                request=request,
                                session_id=session_id,
                                workflow=job_payload.get("workflow"),
                            )
                        )
                        if not self._state.claim_async_job(run_id, os.getpid()):
                            # Another worker may claim the just-created job between the
                            # INSERT and this claim. The caller is still the first
                            # accepted submission, so preserve idempotent=false.
                            early = (run_id, "QUEUED", False)
                        else:
                            self._async_executor.submit(self._run_async_job, job_payload)
            else:
                job = self._async_jobs.get(idempotency_key)
                if job is not None:
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
                    self._async_jobs[idempotency_key] = job
                    self._async_executor.submit(self._run_async_job, job_payload)
        if early is not None:
            # Never respond while holding _async_lock: get_async_observability
            # re-acquires the same non-reentrant lock and would deadlock on a
            # duplicate memory-mode submission (production issue found via the
            # container acceptance chain).
            return self._async_submission_response(early[0], early[1], early[2])
        return self._async_submission_response(run_id, "QUEUED", False)

    def _run_async_job(self, job_payload: Dict[str, Any]) -> None:
        run_id = job_payload["run_id"]
        kwargs = dict(job_payload)
        kwargs.pop("run_id", None)
        completed = False
        failure_category = None
        self._mark_async_started(run_id)
        try:
            payload = self.run(run_id=run_id, _force_run_id=True, **kwargs)
            status = str(payload.get("status") or "FAILED")
            completed = True
        except Exception as exc:
            status = "FAILED"
            failure_category = _failure_category(status, str(exc), source="worker")
            if self._state.persistent:
                result = self._state.get_run(run_id)
                if result is None:
                    result = AgentRunResult(
                        run_id=run_id,
                        status=RunStatus.FAILED,
                        request=str(kwargs.get("request") or ""),
                        session_id=kwargs.get("session_id"),
                        error=str(exc),
                        error_category=failure_category,
                        error_code=getattr(exc, "code", None),
                    )
                elif result.status in {RunStatus.CREATED, RunStatus.PLANNING, RunStatus.EXECUTING}:
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
            self._finish_memory_async_job(run_id, status, failure_category)

    def _finalize_async_job(self, payload: Dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        status = str(payload.get("status") or "FAILED")
        failure_category = _failure_category(status, payload.get("error"))
        if not self._state.persistent:
            self._finish_memory_async_job(run_id, status, failure_category)
            return
        job = self._state.async_job(run_id)
        if job and job.get("owner_pid") == os.getpid():
            self._state.finish_async_job(
                run_id, status, os.getpid(), failure_category
            )

    def _recover_async_jobs(self) -> None:
        if not self._state.persistent:
            return
        for job in self._state.recover_async_jobs(os.getpid()):
            run_id = job["run_id"]
            owner_pid = job.get("owner_pid")
            if owner_pid and owner_pid != os.getpid() and _process_is_alive(owner_pid):
                continue
            if not self._state.claim_async_job(
                run_id,
                os.getpid(),
                recover=True,
                previous_owner_pid=owner_pid,
            ):
                continue
            self._async_executor.submit(self._run_async_job, job["payload"])

    def _ensure_async_run_snapshot(self, job: Dict[str, Any]) -> None:
        """Close the idempotent-submit window before a caller starts polling."""
        if not self._state.persistent or not isinstance(job, dict):
            return
        if str(job.get("status") or "") not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
            return
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        self._state.ensure_run_snapshot(
            AgentRunResult(
                run_id=str(job.get("run_id") or ""),
                status=RunStatus.PLANNING,
                request=str(payload.get("request") or ""),
                session_id=payload.get("session_id"),
                workflow=payload.get("workflow"),
            )
        )

    def _mark_async_started(self, run_id: str) -> None:
        """SQLite claims record the start atomically; memory mode needs the same data."""
        if self._state.persistent:
            return
        now = time.time()
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = "RUNNING"
                job["started_at"] = job.get("started_at") or now
                if job.get("queue_wait_ms") is None:
                    job["queue_wait_ms"] = max(0, (now - job["created_at"]) * 1000)
                job["last_event"] = "started"
                return

    def _finish_memory_async_job(
        self, run_id: str, status: str, failure_category: str = None
    ) -> None:
        finished_at = time.time()
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = status
                job["finished_at"] = finished_at
                started_at = job.get("started_at")
                if started_at is not None:
                    job["run_duration_ms"] = max(0, (finished_at - started_at) * 1000)
                job["failure_category"] = failure_category
                job["last_event"] = _async_event(status)
                return

    def get_async_observability(self, run_id: str) -> Dict[str, Any]:
        """Return a bounded lifecycle summary with no request or error text."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        job = self._state.async_job(run_id) if self._state.persistent else None
        if job is None:
            with self._async_lock:
                job = next(
                    (item for item in self._async_jobs.values() if item.get("run_id") == run_id),
                    None,
                )
        if job is None:
            raise ValueError("async run not found: " + run_id)
        result = self._state.get_run(run_id) if self._state.persistent else self._memory_run(run_id)
        lineage = None
        if result is not None:
            result_payload = result.to_dict()
            explicit_geometry = result_payload.pop("geometry_evidence", None)
            if explicit_geometry is not None:
                result_payload["_geometry_evidence"] = explicit_geometry
            result_payload["trace_summary"] = format_trace(result)
            lineage = build_lineage_index(result_payload)
        return _build_async_observability(job, result, lineage=lineage)

    def _async_submission_response(self, run_id: str, status: str, reused: bool) -> Dict[str, Any]:
        response = _async_response(run_id, status, reused)
        try:
            response["async_observability"] = self.get_async_observability(run_id)
        except ValueError:
            pass
        return response

    def _attach_async_observability(self, payload: Dict[str, Any], run_id: str) -> None:
        if not run_id:
            return
        try:
            payload["async_observability"] = self.get_async_observability(run_id)
        except ValueError:
            return

    def _mark_memory_cancel_requested(self, run_id: str) -> None:
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") == run_id and job.get("status") in {"QUEUED", "RUNNING"}:
                    job["status"] = "CANCEL_REQUESTED"
                    job["cancel_requested_at"] = time.time()
                    job["last_event"] = "cancel_requested"
                    return

    def _memory_run(self, run_id: str):
        for runtime in self._runtimes.values():
            result = runtime.get_run(run_id)
            if result is not None:
                return result
        return None

    def retry(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
    ) -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        runtime = self._runtime(planner, backend)
        result = runtime.retry_failed(run_id)
        payload = result.to_dict()
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        payload["result_type"] = _result_type(payload)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
            result.artifact_ref = payload["artifact_ref"]
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                            dataset=(step.get("result") or {}).get("dataset"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"], payload["_geometry_evidence"] = _exported_geometry_evidence(payload["geojson_ref"])
            result.geometry_evidence = payload["_geometry_evidence"]
            result.geojson_ref = payload["geojson_ref"]
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        payload.pop("_geometry_feature_count", None)
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        if export_artifact:
            # Refresh the durable artifact so it carries the final navigational
            # references (geojson_ref, result_type, session_id) that lineage
            # navigation needs after the in-memory store is gone.
            self._artifact_store.write_run(payload)
        if self._state.persistent:
            self._state.save_run(result)
        return payload

    def cancel(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = self._runtime(planner, backend).cancel(run_id)
        if not self._state.persistent:
            self._mark_memory_cancel_requested(run_id)
        return {
            "run_id": run_id,
            "status": "CANCEL_REQUESTED",
            "current_status": result.status.value,
        }

    def get_run(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = None
        # A terminal run snapshot can be written just before the durable async
        # job marker is finalized. Wait long enough for readers to observe one
        # consistent terminal state instead of returning while the worker
        # still owns the SQLite file.
        for _ in range(1000):
            result = (
                self._state.get_run(run_id)
                if self._state.persistent
                else self._runtime(planner, backend).get_run(run_id)
            )
            if result is None or not self._state.persistent:
                break
            job = self._state.async_job(run_id)
            job_payload = (
                job.get("payload")
                if isinstance(job, dict) and isinstance(job.get("payload"), dict)
                else {}
            )
            requested_artifact = job_payload.get("export_artifact") is True
            requested_geojson = job_payload.get("export_geojson") is True
            missing_requested_refs = result.status == RunStatus.COMPLETED and (
                (requested_artifact and not result.artifact_ref)
                or (requested_geojson and not result.geojson_ref)
            )
            if (
                result.status in _TERMINAL_RUN_STATUSES
                and job is not None
                and (
                    job.get("status") in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
                    or missing_requested_refs
                )
            ):
                time.sleep(0.005)
                continue
            break
        if result is None and not self._state.persistent:
            # Lineage navigation is backend-agnostic: a run created under a
            # different planner/backend (e.g. a comparison child run) is still
            # found by scanning every live runtime before falling back to the
            # durable artifact.
            result = self._memory_run(run_id)
        if result is None and not self._state.persistent:
            # Durable lineage navigation: after a process restart the in-memory
            # run store is gone, but the exported artifact survives on disk.
            # Serve a degraded detail (answer/trace/provenance/context) from the
            # artifact instead of requiring the model to re-run the request.
            payload = (
                self._artifact_store.read_run(run_id)
                if self._artifact_store is not None
                else None
            )
            if payload is not None:
                artifact_result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                payload["trace_summary"] = payload.get("trace_summary") or []
                payload["provenance"] = payload.get("provenance") or build_provenance(payload)
                payload["result_type"] = _result_type(payload)
                payload["result"] = build_result_contract(
                    payload,
                    registry=_runtime_result_registry(self._runtime(planner, backend)),
                )
                if isinstance(artifact_result.get("views"), dict):
                    payload["result"]["views"] = artifact_result["views"]
                _attach_error_category(payload)
                self._attach_async_observability(payload, run_id)
                return payload
        if result is None:
            raise ValueError("run not found: " + run_id)
        payload = result.to_dict()
        explicit_geometry = payload.pop("geometry_evidence", None)
        if explicit_geometry is not None:
            payload["_geometry_evidence"] = explicit_geometry
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(self._runtime(planner, backend)),
        )
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        self._attach_async_observability(payload, run_id)
        return payload

    def list_runs(self, limit: int = 20) -> Dict:
        if self._state.persistent:
            records = self._state.list_runs(limit=limit)
        else:
            records = self._artifact_store.list_runs(limit=limit)
        return {"runs": _attach_history_lineage(records)}

    def list_session_runs(self, session_id: str, limit: int = 20) -> Dict:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if not self._state.persistent:
            records = []
            for runtime in self._runtimes.values():
                records.extend(runtime._state_store.list_runs(limit=limit, session_id=session_id))
            records = _dedupe_run_records(records)
            return {"runs": _attach_history_lineage(records[:limit])}
        return {"runs": _attach_history_lineage(
            self._state.list_runs(limit=limit, session_id=session_id)
        )}

    def list_sessions(self, limit: int = 50) -> Dict:
        if self._conversation_store is None:
            if limit < 1:
                raise ValueError("limit must be positive")
            with self._memory_session_lock:
                sessions = list(self._memory_sessions.values())
            return {"sessions": sessions[-limit:][::-1]}
        return {"sessions": self._conversation_store.list_sessions(limit=limit)}

    def create_session(self) -> Dict:
        if self._conversation_store is None:
            with self._memory_session_lock:
                number = 1
                while "conversation-{}".format(number) in self._memory_sessions:
                    number += 1
                session_id = "conversation-{}".format(number)
                session = {"session_id": session_id, "display_name": "对话{}".format(number)}
                self._memory_sessions[session_id] = session
                return dict(session)
        return self._conversation_store.create_session()

    def clear_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state.clear_session_runs(session_id)
        if self._conversation_store:
            self._conversation_store.clear_session(session_id)
        else:
            for runtime in self._runtimes.values():
                cleared_runs += runtime._state_store.clear_session_runs(session_id)
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "cleared_runs": cleared_runs}

    def delete_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state.clear_session_runs(session_id)
        deleted = self._conversation_store.delete_session(session_id) if self._conversation_store else False
        if self._conversation_store is None:
            for runtime in self._runtimes.values():
                cleared_runs += runtime._state_store.clear_session_runs(session_id)
            with self._memory_session_lock:
                deleted = self._memory_sessions.pop(session_id, None) is not None
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "deleted": deleted, "cleared_runs": cleared_runs}

    def _ensure_memory_session(self, session_id: str) -> None:
        with self._memory_session_lock:
            if session_id in self._memory_sessions:
                return
            self._memory_sessions[session_id] = {
                "session_id": session_id,
                "display_name": _memory_session_display_name(session_id),
            }

    def metrics(self) -> Dict:
        if self._state.persistent:
            metrics = self._state.store_metrics()
            metrics.setdefault("async_jobs", {})["worker_count"] = self._async_worker_count
        else:
            metrics = self._artifact_store.metrics()
            metrics["async_jobs"] = self._memory_async_metrics()
        metrics["cost_governance"] = self._state.cost.summary()
        return metrics

    def capabilities(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the capability catalog owned by the selected Domain Pack."""
        return self._runtime(planner, backend).capability_catalog()

    def close(self) -> None:
        """Shut down the async executor and reaper, draining in-flight jobs.

        Lets callers (tests, server teardown) release SQLite file handles
        deterministically instead of racing the worker threads.
        """
        self._state.stop_reaper()
        self._async_executor.shutdown(wait=True)

    def list_memory(
        self,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
        global_scope: bool = False,
    ) -> Dict:
        """Return bounded memory facts (session-scoped or explicit global)."""
        if global_scope:
            facts = self._state.memory.recall_global(query=query, limit=limit)
        else:
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("session_id must be a non-empty string")
            facts = self._state.memory.recall(session_id=session_id, query=query, limit=limit)
        return {
            "memory_enabled": self._state.memory.enabled,
            "global_scope": bool(global_scope),
            "fact_count": len(facts),
            "facts": [
                {
                    "run_id": fact.get("run_id"),
                    "session_id": fact.get("session_id"),
                    "result_type": fact.get("result_type"),
                    "admin_names": list(fact.get("admin_names") or []),
                    "summary": fact.get("summary"),
                    "facts": dict(fact.get("facts") or {}),
                }
                for fact in facts
            ],
        }

    def register_tool(
        self,
        name: str,
        definition: Dict[str, Any],
        handler,
    ) -> Dict:
        """Register one dynamic tool on every live runtime (M81.2)."""
        if not isinstance(definition, dict):
            raise ValueError("definition must be an object")
        registered = None
        for runtime in self._state.runtimes().values():
            registry = getattr(runtime, "_registry", None)
            if registry is not None and hasattr(registry, "register_tool"):
                registered = registry.register_tool(name, definition, handler)
        if registered is None:
            # No runtime built yet; register lazily by touching the default one.
            runtime = self._runtime("rule", "memory")
            registered = runtime._registry.register_tool(name, definition, handler)
        return registered

    def list_dynamic_tools(self) -> Dict:
        tools = []
        for runtime in self._state.runtimes().values():
            registry = getattr(runtime, "_registry", None)
            if registry is not None and hasattr(registry, "dynamic_tools"):
                for item in registry.dynamic_tools():
                    if item not in tools:
                        tools.append(item)
        return {"dynamic_tools": tools, "count": len(tools)}

    @staticmethod
    def estimate_area_handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dynamic demo tool: estimate area from admin feature coordinates.

        Pure computation over the passed polygon coordinates; no data access,
        no side effects. Demonstrates a runtime-registered capability that is
        still schema-validated and dispatched through the ToolRegistry.
        """
        import math

        coordinates = arguments.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 3:
            raise ToolError("estimate_area requires a polygon ring with 3+ points")
        ring = []
        for point in coordinates:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                raise ToolError("estimate_area points must be [lon, lat] pairs")
            ring.append((float(point[0]), float(point[1])))
        # Planar shoelace approximation on lon/lat; demo only, not geodesic.
        area = 0.0
        for index in range(len(ring)):
            x1, y1 = ring[index]
            x2, y2 = ring[(index + 1) % len(ring)]
            area += x1 * y2 - x2 * y1
        area = abs(area) / 2.0
        return {
            "estimated_area_degrees": area,
            "vertices": len(ring),
            "warning": "平面经纬度估算，仅用于演示动态工具；不代表精确面积。",
        }

    def _memory_async_metrics(self) -> Dict[str, Any]:
        with self._async_lock:
            jobs = list(self._async_jobs.values())
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
        return {
            "count": len(jobs),
            "worker_count": self._async_worker_count,
            "status_counts": status_counts,
            "failure_categories": failure_categories,
            "recovered_jobs": recovered_jobs,
            "queue_wait_ms": _duration_summary(queue_waits),
            "run_duration_ms": _duration_summary(run_durations),
        }

    def compare_buildability(
        self,
        admin_name: str,
        thresholds,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict:
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        scenario = BuildabilityComparisonScenario.for_thresholds(admin_name, thresholds)
        admin_name = scenario.admin_names[0]
        rows = []
        for value in scenario.thresholds:
            result = self.run(
                f"分析{admin_name}建设适宜性，坡度不超过{value:g}度",
                session_id=f"comparison-{admin_name}-{value:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
                export_artifact=True,
            )
            step = next((item for item in result.get("steps", []) if item.get("tool") == "get_zonal_buildability_analysis"), {})
            tool_result = step.get("result") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append({
                "run_id": result.get("run_id"),
                "slope_limit_degrees": value,
                "status": result.get("status"),
                "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                "valid_pixel_count": statistics.get("valid_pixel_count"),
                "candidate_ratio": statistics.get("candidate_ratio"),
                "error": statistics.get("error") or result.get("error"),
                "planner_metrics": result.get("planner_metrics"),
                "actual_tools": [step.get("tool") for step in result.get("steps", []) if isinstance(step, dict)],
                "failed_steps": [
                    {
                        "tool": step.get("tool"),
                        "error": step.get("error"),
                    }
                    for step in result.get("steps", [])
                    if isinstance(step, dict) and step.get("status") == "FAILED"
                ],
                "analysis_ready": _analysis_ready_summary(result),
                "lineage": (result.get("result") or {}).get("lineage"),
            })
        evidence = next(
            (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
            None,
        )
        return {
            "admin_name": admin_name,
            "thresholds": list(scenario.thresholds),
            "scenario": scenario.to_dict(),
            "spatial_context": normalized_context,
            "results": rows,
            "views": build_comparison_views(
                rows,
                "buildability_threshold_comparison",
                title="建设适宜性阈值对比",
                x_field="slope_limit_degrees",
                x_label="坡度阈值",
                y_field="candidate_pixel_count",
                y_label="候选像元",
                table_columns=[
                    ("坡度", "slope_limit_degrees"),
                    ("候选像元", "candidate_pixel_count"),
                    ("候选比例", "candidate_ratio"),
                    ("状态", "status"),
                ],
                note="坡度阈值越高，候选像元通常应保持不减；本图用于展示筛选敏感性。",
            ),
            "lineage": build_comparison_lineage(rows, "buildability_threshold_comparison"),
            **({"analysis_ready": evidence} if evidence else {}),
        }

    def compare_buildability_regions(
        self,
        admin_names,
        threshold: float = 20,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict:
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold must be a number") from exc
        scenario = BuildabilityComparisonScenario.for_regions(admin_names, threshold_value)
        names = list(scenario.admin_names)
        rows = []
        for admin_name in names:
            result = self.compare_buildability(
                admin_name=admin_name,
                thresholds=[threshold_value],
                planner=planner,
                backend=backend,
            )
            row = (result.get("results") or [{}])[0]
            rows.append({"admin_name": admin_name, **row})
        return {
            "admin_names": names,
            "slope_limit_degrees": threshold_value,
            "scenario": scenario.to_dict(),
            "results": rows,
            "views": build_comparison_views(
                rows,
                "buildability_region_comparison",
                title="多区域建设适宜性对比",
                x_field="admin_name",
                x_label="行政区",
                y_field="candidate_pixel_count",
                y_label="候选像元",
                table_columns=[
                    ("行政区", "admin_name"),
                    ("候选像元", "candidate_pixel_count"),
                    ("候选比例", "candidate_ratio"),
                    ("状态", "status"),
                ],
                note="同一坡度阈值下对比不同区域的候选规模。",
            ),
            "lineage": build_comparison_lineage(rows, "buildability_region_comparison"),
            **({
                "analysis_ready": next(
                    (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
                    None,
                )
            } if any(row.get("analysis_ready") for row in rows) else {}),
        }

    def _runtime(self, planner: str, backend: str):
        return self._state.runtime(planner, backend)

    def compare_constrained_buildability(
        self,
        admin_name: str,
        road_distances,
        slope_limit_degrees: float = 15.0,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict:
        """Compare eligible constrained candidates across road distances.

        A wider road distance can only keep or add candidates, so the number of
        eligible features must be monotonic non-decreasing as ``road_distance_m``
        grows. The response keeps this invariant explicit for the live baseline.
        """
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        scenario = ConstrainedBuildabilityComparisonScenario.for_road_distances(
            admin_name, slope_limit_degrees, road_distances
        )
        admin_name = scenario.admin_name
        rows = []
        for distance in scenario.road_distances:
            result = self.run(
                f"筛选{admin_name}坡度不超过{scenario.slope_limit_degrees:g}度、"
                f"距道路{distance:g}米内、排除水体的建设候选区域",
                session_id=f"constrained-compare-{admin_name}-{distance:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
                export_artifact=True,
            )
            step = next(
                (
                    item
                    for item in result.get("steps", [])
                    if item.get("tool") == "get_zonal_constrained_buildability_analysis"
                ),
                {},
            )
            tool_result = step.get("result") or {}
            constraint_summary = tool_result.get("constraint_summary") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append({
                "run_id": result.get("run_id"),
                "road_distance_m": distance,
                "slope_limit_degrees": scenario.slope_limit_degrees,
                "status": result.get("status"),
                "candidate_features": constraint_summary.get("candidate_features"),
                "eligible_features": constraint_summary.get("eligible_features"),
                "water_excluded_features": constraint_summary.get("water_excluded_features"),
                "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                "candidate_ratio": statistics.get("candidate_ratio"),
                "error": (
                    constraint_summary.get("error")
                    or statistics.get("error")
                    or result.get("error")
                ),
                "planner_metrics": result.get("planner_metrics"),
                "actual_tools": [
                    step.get("tool")
                    for step in result.get("steps", [])
                    if isinstance(step, dict)
                ],
                "failed_steps": [
                    {
                        "tool": step.get("tool"),
                        "error": step.get("error"),
                    }
                    for step in result.get("steps", [])
                    if isinstance(step, dict) and step.get("status") == "FAILED"
                ],
                "analysis_ready": _analysis_ready_summary(result),
                "lineage": (result.get("result") or {}).get("lineage"),
            })
        eligible = [
            row.get("eligible_features")
            for row in rows
            if row.get("status") == "COMPLETED"
            and row.get("eligible_features") is not None
        ]
        monotonic = (
            len(eligible) >= 2
            and all(
                later >= earlier
                for earlier, later in zip(eligible, eligible[1:])
            )
        )
        evidence = next(
            (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
            None,
        )
        return {
            "admin_name": admin_name,
            "slope_limit_degrees": scenario.slope_limit_degrees,
            "road_distances": list(scenario.road_distances),
            "scenario": scenario.to_dict(),
            "results": rows,
            "monotonic_eligible_features": monotonic,
            "views": build_comparison_views(
                rows,
                "constrained_buildability_road_distance_comparison",
                title="道路距离约束对比",
                x_field="road_distance_m",
                x_label="道路距离",
                y_field="eligible_features",
                y_label="满足道路约束",
                table_columns=[
                    ("道路距离", "road_distance_m"),
                    ("满足道路约束", "eligible_features"),
                    ("水体排除", "water_excluded_features"),
                    ("候选几何样本", "candidate_features"),
                    ("状态", "status"),
                ],
                note="道路距离放宽时，满足道路约束的候选数应单调不减；水体排除仅作演示约束。",
            ),
            "lineage": build_comparison_lineage(
                rows, "constrained_buildability_road_distance_comparison"
            ),
            **({"analysis_ready": evidence} if evidence else {}),
        }
