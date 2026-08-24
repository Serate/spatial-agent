import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.action_lifecycle import project_action_lifecycle
from agent.cost_governance import RunTokenCapExceeded, extract_tokens as _extract_tokens
from agent.errors import ToolError
from agent.execution_contract import build_execution_record
from agent.failure_contract import build_failure_evidence, failure_from_payload
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES, export_run_summary
from agent.provenance import build_provenance
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.domain_registry import DomainSelectionError, resolve_domain_id
from agent.domain_registry import domain_registry
from agent.runtime_context import assert_runtime_context_compatible
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from agent.domain_routing_evidence import (
    DomainRoutingEvidenceError,
    bind_domain_routing_evidence,
    normalize_domain_routing_evidence,
    routing_evidence_identity,
    unavailable_domain_routing_evidence,
)
from agent.evidence_registry import normalize_evidence_registry
from agent.evidence_projection import project_evidence_projection, project_evidence_recovery
from agent.recovery_action import (
    project_legacy_interaction_receipt,
)
from agent.scenario import BuildabilityComparisonScenario, ConstrainedBuildabilityComparisonScenario
from agent.service_state import ServiceState
from agent.trace_formatter import format_trace
from agent.models import AgentRunResult, RunStatus
from result_contract import (
    build_comparison_views,
    build_comparison_lineage,
    build_lineage_index,
    build_result_contract,
)

from agent.service_async import (
    async_worker_count as _async_worker_count,
    process_is_alive as _process_is_alive,  # legacy patch/import seam
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
    attach_history_lineage as _attach_history_lineage,
    dedupe_run_records as _dedupe_run_records,
    validate_session_id as _validate_session_id,
)
from agent.application.run import RunApplication
from agent.application.actions import ActionApplication
from agent.application.decisions import DecisionApplication
from agent.application.interactions import InteractionApplication
from agent.application.sessions import SessionApplication
from agent.application.async_runs import AsyncApplication


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


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(
        self,
        artifact_store: ArtifactStore = None,
        state_db_path: str = None,
        runtime_factory: Callable[..., Any] = None,
        domain_pack: Any = None,
        domain_id: str = None,
        legacy_domain_id: str = None,
    ):
        self._artifact_store = artifact_store
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
        selected_legacy_domain = str(
            legacy_domain_id or self._configured_domain_id or "gis"
        ).strip()
        if not selected_legacy_domain or len(selected_legacy_domain) > 80:
            raise ValueError("legacy_domain_id must be a non-empty bounded value")
        self._legacy_domain_id = selected_legacy_domain
        if self._artifact_store is None:
            # A legacy artifact without domain_id belongs to the selected
            # Domain, not implicitly to GIS. Explicitly supplied stores keep
            # their own compatibility configuration for shared repositories.
            self._artifact_store = ArtifactStore(
                legacy_domain_id=self._legacy_domain_id
            )
        self._state = ServiceState(
            state_db_path=self._state_db_path,
            runtime_factory=self._runtime_factory,
            domain_id=self._configured_domain_id,
            legacy_domain_id=self._legacy_domain_id,
        )
        self._async_worker_count = _async_worker_count()
        self._async_executor = ThreadPoolExecutor(
            max_workers=self._async_worker_count, thread_name_prefix="spatial-agent"
        )
        self._run_application = RunApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=self._runtime,
            resolved_domain_id=lambda: self._resolved_domain_id,
            configured_domain_id=lambda: self._configured_domain_id,
            legacy_domain_id=self._legacy_domain_id,
            attach_async_observability=self._attach_async_observability,
            finalize_async_job=self._finalize_async_job,
        )
        self._session_application = SessionApplication(
            state=self._state,
            domain_id=lambda: self._resolved_domain_id,
        )
        self._action_application = ActionApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=self._runtime,
            runtime_context_provider=self._runtime_context,
            domain_id_provider=self._domain_id,
            resolved_domain_id=lambda: self._resolved_domain_id,
            action_context_provider=lambda: self,
            get_run_provider=lambda run_id, planner, backend: self.get_run(
                run_id, planner=planner, backend=backend
            ),
            memory_result_provider=self._memory_run,
        )
        self._decision_application = DecisionApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=self._runtime,
            run_provider=self.run,
            memory_run_provider=self._memory_run,
            resolved_domain_id=lambda: self._resolved_domain_id,
            configured_domain_id=lambda: self._configured_domain_id,
            legacy_domain_id=self._legacy_domain_id,
            reserve_action_receipt=self._reserve_action_receipt,
            complete_action_receipt=self._complete_action_receipt,
        )
        self._interaction_application = InteractionApplication(
            artifact_store=self._artifact_store,
            run_reader=lambda run_id, planner, backend: self.get_run(
                run_id, planner=planner, backend=backend
            ),
            runtime_selector=self._infer_run_runtime_selection,
            runtime_provider=self._runtime,
            normalize_workflow=self._normalize_workflow_payload,
            preview_provider=self.preview,
            run_provider=self.run,
            resolve_decision_provider=self.resolve_decision,
            cancel_provider=self.cancel,
            retry_provider=self.retry,
            reserve_receipt=self._reserve_interaction_receipt,
            complete_receipt=self._complete_interaction_receipt,
            capability_resolver=self._resolve_interaction_capability,
            request_facts_resolver=self._interaction_request_facts,
        )
        self._async_application = AsyncApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=self._runtime,
            memory_result_provider=self._memory_run,
            # Resolve the facade method at worker time.  Besides preserving
            # the compatibility seam, this keeps test/custom adapters that
            # patch ``AgentService.run`` observable to the worker.
            run_provider=lambda **kwargs: self.run(**kwargs),
            domain_id_provider=self._domain_id,
            resolved_domain_id=lambda: self._resolved_domain_id,
            configured_domain_id=lambda: self._configured_domain_id,
            normalize_workflow=self._normalize_workflow_payload,
            submission_runtime_context=self._submission_runtime_context,
            runtime_context_provider=self._runtime_context,
            process_is_alive=lambda pid: _process_is_alive(pid),
            submit_job=lambda function, payload: self._async_executor.submit(
                function, payload
            ),
            worker_count=self._async_worker_count,
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

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
        run_id: str = None,
        preview_fingerprint: str = None,
        preview_evidence_fingerprint: str = None,
        require_confirmation: bool = False,
        decision_id: str = None,
        decision_version: int = None,
        decision_ttl_seconds: float = 1800.0,
        _force_run_id: bool = False,
        _async_requested: bool = False,
        _resolved_request: str = None,
        _domain_routing_evidence: Dict[str, Any] = None,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        if _resolved_request is not None and (
            not isinstance(_resolved_request, str) or not _resolved_request.strip()
        ):
            raise ValueError("_resolved_request must be a non-empty string")
        workflow_context = self._normalize_workflow_payload(workflow, planner, backend)
        domain_id = self._domain_id(planner, backend)
        if _domain_routing_evidence is None and run_id is not None and _force_run_id:
            existing = (
                self._state.get_run(run_id, domain_id=domain_id)
                if self._state.persistent
                else self._runtime(planner, backend).get_run(run_id)
            )
            if existing is not None:
                restored_routing_evidence = getattr(
                    existing,
                    "domain_routing_evidence",
                    None,
                )
                if (
                    isinstance(restored_routing_evidence, Mapping)
                    and restored_routing_evidence.get("available") is True
                ):
                    _domain_routing_evidence = restored_routing_evidence
        routing_evidence = (
            normalize_domain_routing_evidence(
                _domain_routing_evidence,
                expected_domain_id=domain_id,
                strict=True,
            )
            if _domain_routing_evidence is not None
            else unavailable_domain_routing_evidence()
        )
        if preview_fingerprint is not None and (
            not isinstance(preview_fingerprint, str) or not preview_fingerprint.strip()
        ):
            raise ValueError("preview_fingerprint must be a non-empty string")
        if preview_evidence_fingerprint is not None and (
            not isinstance(preview_evidence_fingerprint, str)
            or not preview_evidence_fingerprint.strip()
        ):
            raise ValueError(
                "preview_evidence_fingerprint must be a non-empty string"
            )
        if run_id is not None and not _force_run_id:
            if self._state.persistent:
                existing_any = self._state.get_run(run_id)
                if (
                    existing_any is not None
                    and str(getattr(existing_any, "domain_id", "")) != domain_id
                ):
                    raise DomainSelectionError(
                        "run_id belongs to another domain: " + run_id,
                        code="run_domain_mismatch",
                    )
            existing = (
                self._state.get_run(run_id, domain_id=domain_id)
                if self._state.persistent
                else self._runtime(planner, backend).get_run(run_id)
            )
            if existing is not None:
                if routing_evidence_identity(
                    getattr(existing, "domain_routing_evidence", None)
                ) != routing_evidence_identity(routing_evidence):
                    raise DomainRoutingEvidenceError(
                        "run_id conflicts with domain routing identity",
                        code="domain_routing_evidence_run_conflict",
                    )
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
                    "expected_evidence_fingerprint": preview_evidence_fingerprint,
                    "require_confirmation": bool(require_confirmation),
                    "decision_id": decision_id,
                    "decision_version": decision_version,
                    "decision_ttl_seconds": decision_ttl_seconds,
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
                resolved_request_override=_resolved_request,
                domain_routing_evidence=routing_evidence,
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
        _resolved_request: str = None,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if _resolved_request is not None and (
            not isinstance(_resolved_request, str) or not _resolved_request.strip()
        ):
            raise ValueError("_resolved_request must be a non-empty string")
        workflow_context = self._normalize_workflow_payload(workflow, planner, backend)
        normalized_context = _normalize_spatial_context(spatial_context)
        cost = self._state.cost
        cost.acquire_concurrency()
        try:
            cost.check_budget(session_id)
            runtime = self._runtime(planner, backend)
            preview_kwargs = {
                "session_id": session_id,
                "timeout_seconds": timeout_seconds,
                "workflow": workflow_context,
            }
            if _resolved_request is not None:
                preview_kwargs["resolved_request_override"] = _resolved_request
            payload = runtime.preview(
                _contextualize_request(request, normalized_context),
                **preview_kwargs,
            )
        finally:
            cost.release_concurrency()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        plan_evidence = payload.get("plan_evidence")
        if isinstance(plan_evidence, dict) and isinstance(
            plan_evidence.get("evidence_binding"), dict
        ):
            payload["evidence_binding"] = dict(plan_evidence["evidence_binding"])
        cost.charge(session_id, _extract_tokens(payload.get("planner_metrics")))
        try:
            cost.check_run_cap(_extract_tokens(payload.get("planner_metrics")))
        except RunTokenCapExceeded as exc:
            payload["status"] = "FAILED"
            payload["error"] = str(exc)
            payload["error_category"] = "budget"
        payload["lifecycle"] = project_action_lifecycle(payload)
        return payload

    def get_decision(self, decision_id: str) -> Dict[str, Any]:
        """Read one decision through the canonical application seam."""
        return self._decision_application.get(decision_id)

    def resolve_decision(
        self,
        decision_id: str,
        choice: str,
        expected_version: int = None,
        planner: str = "rule",
        backend: str = "memory",
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Resolve one decision through the canonical application seam."""
        return self._decision_application.resolve(
            decision_id,
            choice,
            expected_version=expected_version,
            planner=planner,
            backend=backend,
            idempotency_key=idempotency_key,
        )

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
        resolved_request_override: str = None,
        domain_routing_evidence: Dict[str, Any] = None,
    ) -> Dict:
        return self._run_application.execute(
            request,
            session_id,
            planner,
            backend,
            normalized_context,
            runtime_kwargs=runtime_kwargs,
            workflow_context=workflow_context,
            export_artifact=export_artifact,
            export_geojson=export_geojson,
            geojson_max_features=geojson_max_features,
            async_requested=async_requested,
            resolved_request_override=resolved_request_override,
            domain_routing_evidence=domain_routing_evidence,
        )

    def run_async(self, **kwargs) -> Dict:
        return self._async_application.submit(**kwargs)

    def _finalize_async_job(self, payload: Dict[str, Any]) -> None:
        self._async_application.finalize_job(payload)

    def _recover_async_jobs(self) -> None:
        return self._async_application.recover()

    def get_async_observability(self, run_id: str) -> Dict[str, Any]:
        return self._async_application.get_observability(run_id)

    def _attach_async_observability(self, payload: Dict[str, Any], run_id: str) -> None:
        return self._async_application.attach_observability(payload, run_id)

    def _mark_memory_cancel_requested(self, run_id: str) -> None:
        return self._async_application.mark_cancel_requested(run_id)

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
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
        idempotency_key: str = None,
    ) -> Dict:
        """Retry a failed run with explicit replay or a fresh implicit attempt."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        receipt, reused = self._reserve_action_receipt(
            source_run_id=run_id,
            action="retry",
            payload={
                "export_artifact": bool(export_artifact),
                "export_geojson": bool(export_geojson),
                "geojson_max_features": int(geojson_max_features),
                "idempotency_key": idempotency_key,
            },
            planner=planner,
            backend=backend,
            auto_key=idempotency_key is not None,
        )
        if reused:
            return receipt
        try:
            response = self._retry_payload(
                run_id,
                planner=planner,
                backend=backend,
                export_artifact=export_artifact,
                export_geojson=export_geojson,
                geojson_max_features=geojson_max_features,
            )
        except Exception as exc:
            self._complete_action_receipt(
                receipt,
                {"run_id": run_id, "status": "FAILED", "error": str(exc)},
                status="FAILED",
                error_code="retry_failed",
                response_payload={
                    "run_id": run_id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
            raise
        action_status = "COMPLETED" if response.get("status") == "COMPLETED" else "FAILED"
        return self._complete_action_receipt(
            receipt,
            response,
            status=action_status,
            error_code=None if action_status == "COMPLETED" else "retry_failed",
            result_run_id=response.get("run_id") or run_id,
        )

    def _retry_payload(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
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
        result.evidence_registry = payload["result"].get("evidence_registry")
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

    def cancel(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        idempotency_key: str = None,
    ) -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        receipt, reused = self._reserve_action_receipt(
            source_run_id=run_id,
            action="cancel",
            payload={"idempotency_key": idempotency_key},
            planner=planner,
            backend=backend,
        )
        if reused:
            return receipt
        try:
            result = self._runtime(planner, backend).cancel(run_id)
            if not self._state.persistent:
                self._mark_memory_cancel_requested(run_id)
            response = {
                "run_id": run_id,
                "status": (
                    "CANCELLED"
                    if result.status == RunStatus.CANCELLED
                    else "CANCEL_REQUESTED"
                ),
                "current_status": result.status.value,
            }
        except Exception as exc:
            self._complete_action_receipt(
                receipt,
                {"run_id": run_id, "status": "FAILED", "error": str(exc)},
                status="FAILED",
                error_code="cancel_failed",
                response_payload={
                    "run_id": run_id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
            raise
        return self._complete_action_receipt(
            receipt,
            response,
            status="COMPLETED",
            result_run_id=run_id,
            response_payload=response,
        )

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

    def get_run_interaction(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Read a bounded next-action projection through the application seam."""
        return self._interaction_application.get(run_id, planner, backend)

    def _reserve_action_receipt(
        self,
        *,
        source_run_id: str,
        action: str,
        payload: Dict[str, Any],
        planner: str,
        backend: str,
        fingerprint_namespace: str = "",
        auto_key: bool = True,
    ) -> tuple[Dict[str, Any], bool]:
        return self._action_application.reserve_receipt(
            source_run_id=source_run_id,
            action=action,
            payload=payload,
            planner=planner,
            backend=backend,
            fingerprint_namespace=fingerprint_namespace,
            auto_key=auto_key,
        )

    def _reserve_interaction_receipt(
        self,
        *,
        source_run_id: str,
        action: str,
        payload: Dict[str, Any],
        planner: str,
        backend: str,
    ) -> tuple[Dict[str, Any], bool]:
        """Keep the legacy interaction seam while using generic receipts."""
        receipt, reused = self._reserve_action_receipt(
            source_run_id=source_run_id,
            action=action,
            payload=payload,
            planner=planner,
            backend=backend,
            fingerprint_namespace="run_interaction:",
        )
        if reused:
            receipt["interaction_receipt"] = project_legacy_interaction_receipt(
                receipt.get("action_receipt"), reused=True
            )
        return receipt, reused

    @staticmethod
    def _interaction_receipt_projection(
        receipt: Dict[str, Any], *, reused: bool
    ) -> Dict[str, Any]:
        return project_legacy_interaction_receipt(receipt, reused=reused)

    def _complete_interaction_receipt(
        self,
        receipt: Dict[str, Any],
        response: Optional[Dict[str, Any]],
        *,
        status: str,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._complete_action_receipt(
            receipt,
            response,
            status=status,
            error_code=error_code,
            include_legacy=True,
        )

    def _complete_action_receipt(
        self,
        receipt: Dict[str, Any],
        response: Optional[Dict[str, Any]],
        *,
        status: str,
        error_code: Optional[str] = None,
        result_run_id: Optional[str] = None,
        response_payload: Optional[Dict[str, Any]] = None,
        include_legacy: bool = False,
    ) -> Dict[str, Any]:
        return self._action_application.complete_receipt(
            receipt,
            response,
            status=status,
            error_code=error_code,
            result_run_id=result_run_id,
            response_payload=response_payload,
            include_legacy=include_legacy,
        )

    def apply_run_interaction(
        self,
        run_id: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Invoke one legacy or canonical command through the application seam."""
        return self._interaction_application.apply(
            run_id,
            action,
            payload,
            planner=planner,
            backend=backend,
        )

    def _resolve_interaction_capability(
        self,
        capability_id: str,
        *,
        interaction: Mapping[str, Any],
        request_facts: Any,
        planner: str,
        backend: str,
    ) -> Dict[str, Any]:
        """Resolve a selected Domain capability into canonical workflow data."""
        selected_runtime = self._runtime(planner, backend)
        resolver = getattr(
            getattr(selected_runtime, "_domain_pack", None),
            "resolve_capability_selection",
            None,
        )
        if not callable(resolver):
            raise ValueError("selected capability cannot be converted to a workflow")
        workflow_value = resolver(
            capability_id,
            request_facts=request_facts,
            selection=interaction.get("selection"),
        )
        if not isinstance(workflow_value, dict):
            raise ValueError(
                "selected capability has no executable workflow: " + capability_id
            )
        return dict(workflow_value)

    def _interaction_request_facts(
        self,
        current: Mapping[str, Any],
        *,
        planner: str,
        backend: str,
    ) -> Any:
        """Rebuild private Domain facts instead of reusing their public view.

        Public RequestFacts intentionally omit verbatim text and other
        potentially large values. Capability resolution may need those facts,
        so continuation re-enters the selected Domain Pack's extractor using
        the already-authorized stored request. Runtime stays domain-neutral.
        """

        selected_runtime = self._runtime(planner, backend)
        extractor = getattr(
            getattr(selected_runtime, "_domain_pack", None),
            "extract_request_facts",
            None,
        )
        request = str(
            current.get("resolved_request") or current.get("request") or ""
        ).strip()
        if callable(extractor) and request:
            try:
                return extractor(request)
            except (TypeError, ValueError):
                pass
        return current.get("request_facts")

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

    def get_run_evidence(self, run_id: str) -> Dict[str, Any]:
        """Return a safe, navigable evidence index for one run.

        This is intentionally smaller than a run artifact: callers receive
        the versioned registry and a basename-only artifact reference, never
        a host path or arbitrary file locator.
        """
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        domain_id = self._resolved_domain_id or self._configured_domain_id or "gis"
        artifact = (
            self._artifact_store.read_run(run_id, domain_id=domain_id)
            if self._artifact_store is not None
            else None
        )
        registry = normalize_evidence_registry(
            artifact.get("evidence_registry") if isinstance(artifact, dict) else None
        )
        artifact_ref = artifact.get("artifact_ref") if isinstance(artifact, dict) else None
        payload = None
        if not registry.get("available"):
            try:
                payload = self.get_run(run_id)
            except ValueError:
                payload = None
            envelope = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(envelope, dict):
                registry = normalize_evidence_registry(envelope.get("evidence_registry"))
                artifact_ref = artifact_ref or payload.get("artifact_ref")
        safe_ref = str(artifact_ref or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not registry.get("available") and not safe_ref:
            self._reject_cross_domain_run_id(run_id, domain_id)
            raise ValueError("run evidence not found: " + run_id)
        projection = project_evidence_projection(
            artifact if isinstance(artifact, dict) else (payload or {})
        )
        recovery = project_evidence_recovery(
            artifact if isinstance(artifact, dict) else (payload or {})
        )
        return {
            "schema_version": "spatial-agent.evidence-reference.v1",
            "run_id": run_id,
            "domain_id": domain_id,
            "artifact": {"available": bool(safe_ref), "ref": safe_ref or None},
            "evidence_registry": registry,
            "evidence_projection": projection,
            "evidence_recovery": recovery,
        }

    def list_session_runs(self, session_id: str, limit: int = 20) -> Dict:
        return self._session_application.list_runs(session_id, limit=limit)

    def list_sessions(self, limit: int = 50) -> Dict:
        return self._session_application.list_sessions(limit=limit)

    def create_session(self) -> Dict:
        return self._session_application.create_session()

    def clear_session(self, session_id: str) -> Dict:
        return self._session_application.clear_session(session_id)

    def delete_session(self, session_id: str) -> Dict:
        return self._session_application.delete_session(session_id)

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

    def workflow_contract(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the selected Domain's workflow catalog and validator inputs."""
        runtime = self._runtime(planner, backend)
        resolver = getattr(runtime, "workflow_contract", None)
        if not callable(resolver):
            return {
                "domain_id": self._domain_id(planner, backend),
                "catalog": {},
                "known_tools": [],
                "known_result_types": [],
            }
        value = resolver()
        return dict(value) if isinstance(value, Mapping) else {
            "domain_id": self._domain_id(planner, backend),
            "catalog": {},
            "known_tools": [],
            "known_result_types": [],
        }

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
        """Execute a declared Domain action through the canonical seam."""
        return self._action_application.execute(
            action_id,
            payload,
            planner=planner,
            backend=backend,
            idempotency_key=idempotency_key,
        )

    def get_action_execution(self, execution_id: str) -> Dict[str, Any]:
        """Recover one action result through the canonical application seam."""
        return self._action_application.get(execution_id)

    def list_action_executions(self, limit: int = 20) -> Dict[str, Any]:
        """List action history through the canonical application seam."""
        return self._action_application.list(limit)

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
        self._state.observability.close()

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
        return self._async_application.metrics()

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
                f"分析{admin_name}建设适宜性，坡度不超过{value:g}度，使用 DEM 和土地利用数据",
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

    def _normalize_workflow_payload(
        self,
        workflow: Dict[str, Any] | None,
        planner: str,
        backend: str,
    ) -> Dict[str, Any] | None:
        """Use the selected Domain Pack for explicit workflow normalization.

        The historical GIS normalizer remains only as a compatibility
        fallback for custom/legacy packs. Built-in Domains own their workflow
        schema, so HTTP, async and interaction entry points cannot silently
        import GIS templates for a non-GIS request.
        """
        if workflow is None:
            return None
        runtime = self._runtime(planner, backend)
        domain_pack = getattr(runtime, "_domain_pack", None)
        normalizer = getattr(domain_pack, "normalize_workflow", None)
        if callable(normalizer):
            value = normalizer(workflow)
            if not isinstance(value, dict):
                value = dict(value) if isinstance(value, Mapping) else None
            if value is None:
                raise ValueError("Domain workflow normalizer must return an object")
            return value
        return _normalize_workflow_payload(workflow)

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
            if other is not None and (
                getattr(other, "domain_id", None)
                or self._configured_domain_id
                or "gis"
            ) != domain_id:
                raise ValueError("run_id belongs to another domain: " + str(run_id))
        else:
            artifact = self._artifact_store.read_run(run_id)
            if artifact is not None and (
                artifact.get("domain_id")
                or self._configured_domain_id
                or "gis"
            ) != domain_id:
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
