import os
import json
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from agent.artifact_store import ArtifactStore
from agent.action_contract import ActionContractError
from agent.cost_governance import RunTokenCapExceeded, extract_tokens as _extract_tokens
from agent.decision_lifecycle import DecisionLifecycleError
from agent.errors import ToolError
from agent.execution_contract import build_execution_record
from agent.failure_contract import build_failure_evidence, failure_from_payload
from agent.geojson_exporter import export_run_summary
from agent.provenance import build_provenance
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.domain_registry import resolve_domain_id
from agent.domain_registry import domain_registry
from agent.runtime_context import assert_runtime_context_compatible
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from agent.scenario import BuildabilityComparisonScenario, ConstrainedBuildabilityComparisonScenario
from agent.service_state import ServiceState
from agent.trace_formatter import format_trace
from agent.models import AgentRunResult, RunStatus
from result_contract import (
    build_action_result_contract,
    build_comparison_views,
    build_comparison_lineage,
    build_lineage_index,
    build_result_contract,
)

from agent.service_async import (
    build_async_observability as _build_async_observability,
    build_async_result_evidence as _build_async_result_evidence,
    normalize_async_result_evidence as _normalize_async_result_evidence,
    unavailable_async_result_evidence as _unavailable_async_result_evidence,
    async_event as _async_event,
    async_fingerprint as _async_fingerprint,
    async_response as _async_response,
    async_status as _async_status,
    async_worker_count as _async_worker_count,
    duration_summary as _duration_summary,
    failure_category_for as _failure_category,
    process_is_alive as _process_is_alive,
)
from agent.service_format import (
    _attach_error_category,
    analysis_ready_summary as _analysis_ready_summary,
    contextualize_request as _contextualize_request,
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
    validate_session_id as _validate_session_id,
)


_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.NEEDS_CLARIFICATION,
    RunStatus.WAITING_FOR_DECISION,
    RunStatus.REJECTED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
}


def _bind_domain_pack(domain_pack: Any) -> Callable[..., Any]:
    """Bind one explicit Domain Pack to the generic Runtime Factory seam."""
    if domain_pack is None:
        raise ValueError("domain_pack is required")

    def factory(planner: str, backend: str, **kwargs: Any) -> Any:
        return build_runtime(
            planner,
            backend,
            domain_pack=domain_pack,
            **kwargs,
        )

    return factory


def _bind_domain_id(domain_id: str) -> Callable[..., Any]:
    """Bind a registered domain id without exposing import paths to callers."""
    if not isinstance(domain_id, str) or not domain_id.strip():
        raise ValueError("domain_id must be a non-empty string")

    def factory(planner: str, backend: str, **kwargs: Any) -> Any:
        return build_runtime(
            planner,
            backend,
            domain_id=domain_id,
            **kwargs,
        )

    return factory


def _runtime_result_registry(runtime):
    """Read the optional result registry from legacy/custom runtimes."""
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


def _action_result_type(runtime, action_id: str) -> str:
    """Resolve a declared action's result type without reflecting methods."""
    resolver = getattr(runtime, "domain_actions", None)
    catalog = resolver() if callable(resolver) else {}
    for item in (catalog.get("actions", []) if isinstance(catalog, dict) else []):
        if isinstance(item, dict) and str(item.get("id") or "") == action_id:
            return str(item.get("result_type") or "action_result")[:96]
    return "action_result"


def _action_input_fingerprint(action_id: str, payload: Any) -> str:
    encoded = json.dumps(
        {"action_id": str(action_id), "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _action_response_from_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    response = dict(artifact.get("action_result") or {})
    response.update({
        "action_id": artifact.get("action_id"),
        "domain_id": artifact.get("domain_id"),
        "runtime_context": artifact.get("runtime_context"),
        "status": artifact.get("status"),
        "action_execution_id": artifact.get("action_execution_id"),
        "action_execution": artifact.get("action_execution"),
        "idempotency_key": artifact.get("idempotency_key"),
        "trace_summary": artifact.get("trace_summary") or [],
        "artifact_ref": artifact.get("artifact_ref"),
        "result": artifact.get("result"),
        "idempotency_reused": True,
        "execution_record": artifact.get("execution_record")
        or build_execution_record(artifact, kind="action"),
    })
    if artifact.get("error"):
        response["error"] = artifact["error"]
    if artifact.get("action_error_code"):
        response["action_error_code"] = artifact["action_error_code"]
    return response


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(
        self,
        artifact_store: ArtifactStore = None,
        state_db_path: str = None,
        runtime_factory: Callable[..., Any] = None,
        domain_pack: Any = None,
        domain_id: str = None,
    ):
        self._artifact_store = artifact_store or ArtifactStore()
        self._state_db_path = state_db_path or os.environ.get("SPATIAL_AGENT_STATE_DB")
        self._configured_domain_id = None
        self._configured_domain_pack = None
        self._resolved_domain_id = None
        if runtime_factory is not None and (domain_pack is not None or domain_id is not None):
            raise ValueError("runtime_factory cannot be combined with domain_pack or domain_id")
        if domain_pack is not None and domain_id is not None:
            raise ValueError("domain_pack and domain_id are mutually exclusive")
        if runtime_factory is not None:
            self._runtime_factory = runtime_factory
        elif domain_pack is not None:
            self._configured_domain_pack = domain_pack
            self._configured_domain_id = str(
                getattr(domain_pack, "domain_id", "unknown")
            )[:80]
            self._runtime_factory = _bind_domain_pack(domain_pack)
        elif domain_id is not None:
            self._configured_domain_id = resolve_domain_id(domain_id)
            self._runtime_factory = _bind_domain_id(self._configured_domain_id)
        else:
            # Resolve once at the application boundary so all runtimes and
            # persistence reads in this service use one selected Domain.
            self._configured_domain_id = resolve_domain_id()
            self._runtime_factory = build_runtime
        self._resolved_domain_id = self._configured_domain_id
        self._state = ServiceState(
            state_db_path=self._state_db_path,
            runtime_factory=self._runtime_factory,
            domain_id=self._configured_domain_id,
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
        require_confirmation: bool = False,
        decision_id: str = None,
        decision_version: int = None,
        _force_run_id: bool = False,
        _async_requested: bool = False,
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
            domain_id = self._domain_id(planner, backend)
            existing = (
                self._state.get_run(run_id, domain_id=domain_id)
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
                    "require_confirmation": bool(require_confirmation),
                    "decision_id": decision_id,
                    "decision_version": decision_version,
                    "decision_input": {
                        "export_artifact": bool(export_artifact),
                        "export_geojson": bool(export_geojson),
                        "geojson_max_features": int(geojson_max_features),
                    },
                },
                workflow_context=workflow_context,
                export_artifact=export_artifact,
                export_geojson=export_geojson,
                geojson_max_features=geojson_max_features,
                async_requested=_async_requested,
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
        payload["execution_record"] = build_execution_record(payload, kind="run")
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

    def get_decision(self, decision_id: str) -> Dict[str, Any]:
        """Read one bounded decision projection within the selected Domain."""
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        domain_id = self._resolved_domain_id or self._configured_domain_id or "unknown"
        record = self._state.decision_store.get(decision_id, domain_id=domain_id)
        if record is None:
            raise ValueError("decision not found: " + decision_id)
        return {
            "schema_version": record.schema_version,
            "decision": record.as_dict(),
            "evidence": record.evidence(),
        }

    def resolve_decision(
        self,
        decision_id: str,
        choice: str,
        expected_version: int = None,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Approve/reject a waiting run and resume only its persisted plan."""
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ValueError("decision_id must be a non-empty string")
        domain_id = self._resolved_domain_id or self._configured_domain_id or "unknown"
        try:
            record = self._state.decision_store.resolve(
                decision_id,
                choice=choice,
                expected_version=expected_version,
                domain_id=domain_id,
            )
        except DecisionLifecycleError:
            raise
        result = (
            self._state.get_run(record.subject_id, domain_id=domain_id)
            if self._state.persistent
            else self._memory_run(record.subject_id)
        )
        if result is None:
            raise ValueError("decision subject run not found: " + record.subject_id)
        if record.status == "REJECTED":
            result.status = RunStatus.REJECTED
            result.error = "用户拒绝执行当前计划。"
            result.answer = "已拒绝执行当前计划。"
            result.decision_evidence = record.evidence()
            if self._state.persistent:
                self._state.save_run(result)
            else:
                runtime = self._runtime(planner, backend)
                runtime._state_store.save(result)
            payload = _format_result(
                result,
                {},
                result_registry=_runtime_result_registry(self._runtime(planner, backend)),
            )
            payload["decision"] = record.as_dict()
            return payload

        context = result.runtime_context if isinstance(result.runtime_context, dict) else {}
        selected_planner = str(context.get("planner") or planner)
        selected_backend = str(context.get("backend") or backend)
        options = record.input_data if isinstance(record.input_data, dict) else {}
        payload = self.run(
            request=result.request,
            session_id=result.session_id or "default",
            planner=selected_planner,
            backend=selected_backend,
            export_artifact=bool(options.get("export_artifact")),
            export_geojson=bool(options.get("export_geojson")),
            geojson_max_features=int(options.get("geojson_max_features", 100)),
            workflow=result.workflow,
            run_id=result.run_id,
            preview_fingerprint=record.subject_fingerprint,
            decision_id=record.decision_id,
            decision_version=record.version,
            _force_run_id=True,
        )
        payload["decision"] = record.as_dict()
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
        async_requested: bool = False,
    ) -> Dict:
        runtime = self._runtime(planner, backend)
        if workflow_context is not None:
            runtime_kwargs["workflow"] = workflow_context
        result = runtime.run(
            _contextualize_request(request, normalized_context), **runtime_kwargs
        )
        payload = result.to_dict()
        if async_requested:
            # Internal marker consumed only by ArtifactStore.  It is kept out
            # of the public result envelope while allowing a partial artifact
            # to be identified as an async run during recovery.
            payload["_async_requested"] = True
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
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
        payload["execution_record"] = build_execution_record(payload, kind="run")
        if export_artifact:
            # Refresh the durable artifact so it carries the final navigational
            # references (geojson_ref, result_type, session_id) that lineage
            # navigation needs after the in-memory store is gone.
            self._artifact_store.write_run(payload)
        if self._state.persistent:
            self._state.save_run(result)
        self._attach_async_observability(payload, payload.get("run_id"))
        if export_artifact and async_requested:
            # The first artifact write happens before the final async
            # observation exists.  Refresh it once more so artifact-only
            # recovery can render the same bounded evidence.
            self._artifact_store.write_run(payload)
        payload["memory_evidence"] = self._state.memory.evidence(
            str(payload.get("session_id") or "default")
        )
        # Mark the durable job terminal only after every final snapshot read
        # is complete. Pollers use this marker as the worker quiescence boundary.
        self._finalize_async_job(payload)
        if async_requested:
            # The job is terminal now, so a final observation can be rebuilt
            # even when the pre-finalization snapshot was not yet visible to
            # this worker.  Persist that terminal evidence for artifact-only
            # recovery as well.
            self._attach_async_observability(payload, payload.get("run_id"))
            if export_artifact:
                self._artifact_store.write_run(payload)
        payload.pop("_async_requested", None)
        return payload

    def run_async(self, **kwargs) -> Dict:
        request = kwargs.get("request", "")
        session_id = kwargs.get("session_id", "default")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
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

        domain_id = self._domain_id(
            kwargs.get("planner", "rule"), kwargs.get("backend", "memory")
        )
        kwargs["domain_id"] = domain_id
        kwargs["runtime_context"] = self._submission_runtime_context(
            kwargs.get("planner", "rule"), kwargs.get("backend", "memory")
        )
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
                existing_any = self._state.get_run(run_id)
                if (
                    existing_any is not None
                    and getattr(existing_any, "domain_id", "gis") != domain_id
                ):
                    raise ValueError("run_id belongs to another domain: " + str(run_id))
                existing_result = self._state.get_run(run_id, domain_id=domain_id)
                if existing_result is not None and not self._state.async_job(
                    run_id, domain_id=domain_id
                ):
                    early = (run_id, existing_result.status.value, True)
                else:
                    job = self._state.create_async_job(
                        idempotency_key, run_id, job_payload
                    )
                    created = bool(job.pop("created", False))
                    if not created:
                        existing_domain = (
                            job.get("payload", {}).get("domain_id", "gis")
                            if isinstance(job.get("payload"), dict)
                            else "gis"
                        )
                        if existing_domain != domain_id:
                            raise ValueError(
                                "idempotency_key belongs to another domain"
                            )
                        self._ensure_async_run_snapshot(job)
                        early = (job["run_id"], _async_status(self._state_store, job), True)
                    else:
                        self._state.save_run(
                            AgentRunResult(
                                run_id=run_id,
                                status=RunStatus.PLANNING,
                                request=request,
                                session_id=session_id,
                                domain_id=domain_id,
                                runtime_context=job_payload.get("runtime_context"),
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
        domain_id = kwargs.pop("domain_id", None) or self._resolved_domain_id
        runtime_context = kwargs.pop("runtime_context", None)
        completed = False
        failure_category = None
        self._mark_async_started(run_id)
        try:
            if runtime_context is not None:
                current_context = self._runtime_context(
                    kwargs.get("planner", "rule"),
                    kwargs.get("backend", "memory"),
                )
                # Legacy/custom Runtime implementations may not expose the
                # optional Context seam. Preserve their existing async
                # behavior; strict drift detection applies when both sides
                # provide a Context snapshot.
                if current_context is not None:
                    assert_runtime_context_compatible(runtime_context, current_context)
            payload = self.run(
                run_id=run_id,
                _force_run_id=True,
                _async_requested=True,
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
                        runtime_context=runtime_context,
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
        job = self._state.async_job(run_id, domain_id=self._resolved_domain_id)
        if job and job.get("owner_pid") == os.getpid():
            self._state.finish_async_job(
                run_id, status, os.getpid(), failure_category
            )

    def _recover_async_jobs(self) -> None:
        if not self._state.persistent:
            return
        for job in self._state.recover_async_jobs(
            os.getpid(), domain_id=self._configured_domain_id
        ):
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
                domain_id=payload.get("domain_id", "gis"),
                runtime_context=payload.get("runtime_context"),
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

    def _artifact_async_observability(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Rebuild async evidence when the SQLite job row is unavailable.

        Only artifacts explicitly marked as async (or carrying the new
        evidence field) enter this path.  That keeps synchronous run artifacts
        from unexpectedly gaining an async polling payload while allowing a
        partially written/legacy async artifact to report an explicit
        unavailable/unknown evidence state.
        """
        artifact = self._artifact_store.read_run(
            run_id, domain_id=self._resolved_domain_id
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
            # Accept the transitional nested shape used by early async
            # artifacts while keeping the persisted projection flat going
            # forward.
            evidence = artifact["async_observability"].get("result_evidence")
        if evidence is None:
            evidence = _unavailable_async_result_evidence(
                status=status,
                artifact_ref=artifact.get("artifact_ref"),
            )
        else:
            evidence = _normalize_async_result_evidence(
                evidence,
                status=status,
                artifact_ref=artifact.get("artifact_ref"),
            )
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

    def get_async_observability(self, run_id: str) -> Dict[str, Any]:
        """Return a bounded lifecycle summary with no request or error text."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        job = (
            self._state.async_job(run_id, domain_id=self._resolved_domain_id)
            if self._state.persistent
            else None
        )
        if job is None:
            with self._async_lock:
                job = next(
                    (item for item in self._async_jobs.values() if item.get("run_id") == run_id),
                    None,
                )
        if job is None:
            artifact_observation = self._artifact_async_observability(run_id)
            if artifact_observation is not None:
                return artifact_observation
            raise ValueError("async run not found: " + run_id)
        result = (
            self._state.get_run(run_id, domain_id=self._resolved_domain_id)
            if self._state.persistent
            else self._memory_run(run_id)
        )
        lineage = None
        result_evidence = None
        if result is not None:
            result_payload = result.to_dict()
            explicit_geometry = result_payload.pop("geometry_evidence", None)
            if explicit_geometry is not None:
                result_payload["_geometry_evidence"] = explicit_geometry
            result_payload["trace_summary"] = format_trace(result)
            lineage = build_lineage_index(result_payload)
            context = result_payload.get("runtime_context")
            planner = context.get("planner", "rule") if isinstance(context, dict) else "rule"
            backend = context.get("backend", "memory") if isinstance(context, dict) else "memory"
            runtime = self._runtime(planner, backend)
            result_payload["result_type"] = _result_type(result_payload)
            result_contract = build_result_contract(
                result_payload,
                registry=_runtime_result_registry(runtime),
            )
            artifact_ref = result_payload.get("artifact_ref")
            if not artifact_ref and self._artifact_store is not None:
                # SQLite snapshots can become visible just before the final
                # artifact_ref column is refreshed.  The artifact itself is
                # the durable source of truth for this bounded evidence; use
                # only its safe reference, never its contents.
                artifact = self._artifact_store.read_run(
                    run_id, domain_id=self._resolved_domain_id
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

    def _infer_run_runtime_selection(
        self, run_id: str, planner: str, backend: str
    ) -> tuple[str, str]:
        """Use persisted Runtime Context when a detail URL omits selectors.

        HTTP clients historically called ``GET /runs/{id}`` without planner or
        backend query parameters.  Rebuilding the default rule/memory Runtime
        for an OpenAI/local run can execute the wrong Domain factory (and can
        fail before the result is even formatted).  The run snapshot and
        async submission payload already carry the immutable selection, so
        recover it without inventing a new Runtime.
        """
        if (planner, backend) != ("rule", "memory"):
            return planner, backend

        context = None
        if self._state.persistent:
            domain_id = self._resolved_domain_id or self._configured_domain_id
            snapshot = self._state.get_run(run_id, domain_id=domain_id)
            context = getattr(snapshot, "runtime_context", None) if snapshot else None
            if not isinstance(context, dict):
                job = self._state.async_job(run_id, domain_id=domain_id)
                payload = job.get("payload") if isinstance(job, dict) else None
                context = payload.get("runtime_context") if isinstance(payload, dict) else None
                if isinstance(payload, dict):
                    planner = str(payload.get("planner") or planner)
                    backend = str(payload.get("backend") or backend)
        else:
            snapshot = self._memory_run(run_id)
            context = getattr(snapshot, "runtime_context", None) if snapshot else None

        if isinstance(context, dict):
            planner = str(context.get("planner") or planner)
            backend = str(context.get("backend") or backend)
        if planner not in {"rule", "openai"}:
            planner = "rule"
        if backend not in {"memory", "local"}:
            backend = "memory"
        return planner, backend

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
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
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
        payload["execution_record"] = build_execution_record(payload, kind="run")
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
        planner, backend = self._infer_run_runtime_selection(run_id, planner, backend)
        domain_id = self._domain_id(planner, backend)
        result = None
        # A terminal run snapshot can be written just before the durable async
        # job marker is finalized. Wait long enough for readers to observe one
        # consistent terminal state instead of returning while the worker
        # still owns the SQLite file.
        for _ in range(1000):
            result = (
                self._state.get_run(run_id, domain_id=domain_id)
                if self._state.persistent
                else self._runtime(planner, backend).get_run(run_id)
            )
            if result is None or not self._state.persistent:
                break
            job = self._state.async_job(run_id, domain_id=domain_id)
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
        if result is None:
            # Durable lineage navigation: after a process restart or when the
            # SQLite row has been removed, the exported artifact may be the
            # only surviving run snapshot.  Serve a degraded detail from it
            # instead of requiring the model to re-run the request.
            payload = (
                self._artifact_store.read_run(run_id, domain_id=domain_id)
                if self._artifact_store is not None
                else None
            )
            if payload is not None:
                artifact_result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
                normalized_artifact_result = None
                nested_schema_error = payload.get("nested_schema_warning")
                if artifact_result:
                    try:
                        normalized_artifact_result = normalize_result_contract(
                            artifact_result
                        )
                    except NestedSchemaError as exc:
                        # The artifact itself remains readable, but an
                        # unknown nested future view must never be copied into
                        # the current result contract.  Build a bounded
                        # unavailable view below instead.
                        nested_schema_error = exc.reason_code
                if nested_schema_error:
                    payload["_nested_schema_error"] = nested_schema_error
                payload["trace_summary"] = payload.get("trace_summary") or []
                payload["provenance"] = payload.get("provenance") or build_provenance(
                    payload,
                    registry=_runtime_result_registry(
                        self._runtime(planner, backend)
                    ),
                )
                payload["result_type"] = _result_type(payload)
                payload["result"] = build_result_contract(
                    payload,
                    registry=_runtime_result_registry(self._runtime(planner, backend)),
                )
                artifact_views = (
                    normalized_artifact_result.get("views")
                    if isinstance(normalized_artifact_result, dict)
                    else None
                )
                artifact_panels = (
                    artifact_views.get("panels")
                    if isinstance(artifact_views, dict)
                    else None
                )
                # Keep newly generated bounded unavailable views when an old
                # artifact has an empty view map; a non-empty artifact view
                # remains authoritative for successful/recovered rendering.
                if isinstance(artifact_views, dict) and (
                    isinstance(artifact_panels, dict) and artifact_panels
                ):
                    payload["result"]["views"] = artifact_views
                payload.pop("_nested_schema_error", None)
                payload.pop("nested_schema_warning", None)
                _attach_error_category(payload)
                payload["execution_record"] = payload.get("execution_record") or build_execution_record(
                    payload, kind="run"
                )
                self._attach_async_observability(payload, run_id)
                return payload
            self._reject_cross_domain_run_id(run_id, domain_id)
        if result is None:
            raise ValueError("run not found: " + run_id)
        payload = result.to_dict()
        explicit_geometry = payload.pop("geometry_evidence", None)
        if explicit_geometry is not None:
            payload["_geometry_evidence"] = explicit_geometry
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(
                self._runtime(planner, backend)
            ),
        )
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(self._runtime(planner, backend)),
        )
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        payload["execution_record"] = build_execution_record(payload, kind="run")
        self._attach_async_observability(payload, run_id)
        return payload

    def list_runs(self, limit: int = 20) -> Dict:
        if self._state.persistent:
            records = self._state.list_runs(
                limit=limit, domain_id=self._resolved_domain_id
            )
        else:
            records = self._artifact_store.list_runs(
                limit=limit, domain_id=self._resolved_domain_id
            )
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
            self._state.list_runs(
                limit=limit,
                session_id=session_id,
                domain_id=self._resolved_domain_id,
            )
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

    def metrics(self) -> Dict:
        if self._state.persistent:
            metrics = self._state.store_metrics(domain_id=self._resolved_domain_id)
            metrics.setdefault("async_jobs", {})["worker_count"] = self._async_worker_count
        else:
            metrics = self._artifact_store.metrics(domain_id=self._resolved_domain_id)
            metrics["async_jobs"] = self._memory_async_metrics()
        metrics["cost_governance"] = self._state.cost.summary()
        metrics["actions"] = self._artifact_store.action_metrics(
            domain_id=self._resolved_domain_id
        )
        metrics["observability"] = {
            "schema_version": "spatial-agent.observability.v1",
            "event_count": self._state.observability.event_count,
        }
        return metrics

    def capabilities(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the capability catalog owned by the selected Domain Pack."""
        return self._runtime(planner, backend).capability_catalog()

    def domains(self) -> Dict[str, Any]:
        """Return the bounded deployment Domain Registry catalog."""
        return domain_registry().catalog()

    def actions(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the bounded actions declared by the selected Domain Pack."""
        runtime = self._runtime(planner, backend)
        resolver = getattr(runtime, "domain_actions", None)
        if not callable(resolver):
            return {
                "schema_version": "spatial-agent.actions.v1",
                "domain_id": "unknown",
                "actions": [],
            }
        value = resolver()
        return dict(value) if isinstance(value, dict) else {
            "schema_version": "spatial-agent.actions.v1",
            "domain_id": "unknown",
            "actions": [],
        }

    def execute_action(
        self,
        action_id: str,
        payload: Dict[str, Any],
        planner: str = "rule",
        backend: str = "local",
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Execute and durably observe a declared Domain Pack action."""
        runtime = self._runtime(planner, backend)
        resolver = getattr(runtime, "execute_domain_action", None)
        if not callable(resolver):
            raise ValueError("domain action execution is unavailable")
        domain_id = self._domain_id(planner, backend)
        runtime_context = self._runtime_context(planner, backend)
        action_id = str(action_id or "")[:96]
        action_payload = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(action_payload, dict):
            action_payload.pop("idempotency_key", None)
        if idempotency_key is None and isinstance(payload, dict):
            idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None:
            idempotency_key = str(idempotency_key).strip()
            if not idempotency_key or len(idempotency_key) > 128 or "/" in idempotency_key or "\\" in idempotency_key:
                raise ValueError("idempotency_key must be a safe non-empty value")
        input_fingerprint = _action_input_fingerprint(action_id, action_payload)
        if idempotency_key:
            existing = self._artifact_store.find_action_by_idempotency_key(
                idempotency_key, domain_id=domain_id
            )
            if existing is not None:
                if existing.get("input_fingerprint") != input_fingerprint:
                    raise ActionContractError(
                        "idempotency_key conflicts with a previous action input",
                        action_id=action_id,
                        code="idempotency_conflict",
                    )
                if existing.get("status") == "FAILED":
                    error = ActionContractError(
                        str(existing.get("error") or "action execution failed"),
                        action_id=action_id,
                        code=str(existing.get("action_error_code") or "action_execution_failed"),
                    )
                    error.action_execution_id = existing.get("action_execution_id")
                    error.artifact_ref = existing.get("artifact_ref")
                    raise error
                return _action_response_from_artifact(existing)
        execution_id = "action-" + uuid.uuid4().hex
        catalog = runtime.capability_catalog()
        domain_id = str(catalog.get("domain_id") or domain_id)[:80]
        result_type = _action_result_type(runtime, action_id)
        started = time.perf_counter()
        try:
            result = resolver(action_id, action_payload, context=self)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            action_error_code = str(getattr(exc, "code", "action_execution_failed"))[:96]
            record = {
                "action_execution_id": execution_id,
                "action_id": action_id,
                "domain_id": domain_id,
                "runtime_context": runtime_context,
                "idempotency_key": idempotency_key,
                "input_fingerprint": input_fingerprint,
                "status": "FAILED",
                "result_type": result_type,
                "error": str(exc),
                "error_code": "action_execution_failed",
                "action_error_code": action_error_code,
                "action_result": {},
                "action_execution": {
                    "schema_version": "spatial-agent.action-execution.v1",
                    "status": "FAILED",
                    "action_id": action_id,
                    "input_validated": action_error_code != "action_invalid_input",
                    "error_code": action_error_code,
                    "duration_ms": duration_ms,
                },
                "trace_summary": [
                    "Received action: " + action_id,
                    "Action " + action_id + " failed: " + str(exc),
                ],
            }
            record["result"] = build_action_result_contract(
                record,
                registry=_runtime_result_registry(runtime),
            )
            artifact_ref = self._artifact_store.write_action(record)
            record["artifact_ref"] = artifact_ref
            record["execution_record"] = build_execution_record(record, kind="action")
            record["result"] = build_action_result_contract(
                record,
                registry=_runtime_result_registry(runtime),
            )
            self._artifact_store.write_action(record)
            self._state.observability.emit_action(
                execution_id=execution_id,
                action_id=action_id,
                domain_id=domain_id,
                status="FAILED",
                duration_ms=duration_ms,
                attributes={
                    "action_error_code": action_error_code,
                    "input_validated": action_error_code != "action_invalid_input",
                    "artifact_available": True,
                },
            )
            for name, value in {
                "action_execution_id": execution_id,
                "artifact_ref": artifact_ref,
            }.items():
                try:
                    setattr(exc, name, value)
                except Exception:
                    pass
            raise
        if not isinstance(result, dict):
            raise ValueError("domain action must return an object")
        action_result = dict(result)
        response = dict(action_result)
        response.setdefault("action_id", action_id)
        response.setdefault("action_schema_version", "spatial-agent.actions.v1")
        response.setdefault("domain_id", domain_id)
        response.setdefault("status", "COMPLETED")
        action_execution = {
            "schema_version": "spatial-agent.action-execution.v1",
            "status": "COMPLETED",
            "action_id": action_id,
            "input_validated": True,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        record = {
            "action_execution_id": execution_id,
            "action_id": action_id,
            "domain_id": domain_id,
            "runtime_context": runtime_context,
            "idempotency_key": idempotency_key,
            "input_fingerprint": input_fingerprint,
            "status": "COMPLETED",
            "result_type": str(action_result.get("result_type") or result_type),
            "action_result": action_result,
            "action_execution": action_execution,
            "trace_summary": [
                "Received action: " + action_id,
                "Action " + action_id + " completed.",
            ],
        }
        record["result"] = build_action_result_contract(
            record,
            registry=_runtime_result_registry(runtime),
        )
        artifact_ref = self._artifact_store.write_action(record)
        record["artifact_ref"] = artifact_ref
        record["execution_record"] = build_execution_record(record, kind="action")
        record["result"] = build_action_result_contract(
            record,
            registry=_runtime_result_registry(runtime),
        )
        self._artifact_store.write_action(record)
        self._state.observability.emit_action(
            execution_id=execution_id,
            action_id=action_id,
            domain_id=domain_id,
            status="COMPLETED",
            duration_ms=action_execution["duration_ms"],
            attributes={
                "result_type": record["result_type"],
                "input_validated": True,
                "artifact_available": True,
            },
        )
        response.update({
            "action_execution_id": execution_id,
            "action_execution": action_execution,
            "runtime_context": runtime_context,
            "idempotency_key": idempotency_key,
            "idempotency_reused": False,
            "trace_summary": list(record["trace_summary"]),
            "artifact_ref": artifact_ref,
            "result": record["result"],
            "execution_record": record["execution_record"],
        })
        return response

    def get_action_execution(self, execution_id: str) -> Dict[str, Any]:
        """Recover one action result from its artifact without dispatching it."""
        value = self._artifact_store.read_action(
            execution_id, domain_id=self._resolved_domain_id
        )
        if value is None:
            raise ValueError("action execution not found: " + str(execution_id))
        value.setdefault(
            "execution_record", build_execution_record(value, kind="action")
        )
        return value

    def list_action_executions(self, limit: int = 20) -> Dict[str, Any]:
        """Return bounded action history for Console and operational clients."""
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        return {
            "schema_version": "spatial-agent.action-history.v1",
            "actions": self._artifact_store.list_actions(
                limit=limit, domain_id=self._resolved_domain_id
            ),
        }

    def runtime_capabilities(
        self,
        max_files: int = 10,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return generic runtime evidence from the selected Domain Pack."""
        return self._runtime(planner, backend).runtime_capabilities(
            max_files=max_files
        )

    def release_evidence(
        self,
        config_path: str = None,
        max_files: int = 10,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict[str, Any]:
        """Return release evidence from the selected Domain Pack."""
        return self._runtime(planner, backend).release_evidence(
            config_path=config_path,
            max_files=max_files,
        )

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
        runtime = self._state.runtime(planner, backend)
        runtime_domain_id = getattr(runtime, "domain_id", None)
        if runtime_domain_id:
            self._resolved_domain_id = str(runtime_domain_id)[:80]
        return runtime

    def _runtime_context(self, planner: str, backend: str) -> Optional[Dict[str, Any]]:
        runtime = self._runtime(planner, backend)
        builder = getattr(runtime, "runtime_context", None)
        value = builder() if callable(builder) else None
        return dict(value) if isinstance(value, dict) else None

    def _submission_runtime_context(
        self, planner: str, backend: str
    ) -> Optional[Dict[str, Any]]:
        """Build a context snapshot without blocking async submission."""
        if self._configured_domain_id or self._runtime_factory is build_runtime:
            return build_runtime_context_snapshot(
                planner,
                backend,
                domain_pack=self._configured_domain_pack,
                domain_id=(
                    None
                    if self._configured_domain_pack is not None
                    else self._configured_domain_id
                ),
            )
        runtimes = self._state.runtimes()
        # ServiceState caches runtimes by the validated `(planner, backend)`
        # tuple.  Looking up a string key silently dropped the context for
        # custom factories, causing async polling to rebuild the default
        # rule/memory Runtime and fail before the first HTTP response.
        runtime = runtimes.get((str(planner), str(backend)))
        if runtime is None:
            # Keep compatibility with any legacy state facade that exposed
            # string keys while making the tuple key the canonical path.
            runtime = runtimes.get(str(planner) + ":" + str(backend))
        builder = getattr(runtime, "runtime_context", None) if runtime else None
        value = builder() if callable(builder) else None
        return dict(value) if isinstance(value, dict) else None

    def _domain_id(self, planner: str, backend: str) -> str:
        """Return the service's selected domain, resolving custom factories lazily."""
        if self._resolved_domain_id:
            return self._resolved_domain_id
        runtime = self._runtime(planner, backend)
        return self._resolved_domain_id or str(
            getattr(runtime, "domain_id", "unknown")
        )[:80]

    def _reject_cross_domain_run_id(self, run_id: str, domain_id: str) -> None:
        """Never overwrite a durable run owned by another Domain Pack."""
        if self._state.persistent:
            other = self._state.get_run(run_id)
            if other is not None and getattr(other, "domain_id", "gis") != domain_id:
                raise ValueError("run_id belongs to another domain: " + str(run_id))
        else:
            artifact = self._artifact_store.read_run(run_id)
            if artifact is not None and artifact.get("domain_id", "gis") != domain_id:
                raise ValueError("run_id belongs to another domain: " + str(run_id))

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
