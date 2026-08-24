import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.action_lifecycle import project_action_lifecycle
from agent.cost_governance import RunTokenCapExceeded, extract_tokens as _extract_tokens
from agent.errors import ToolError
from agent.execution_contract import build_execution_record
from agent.failure_contract import build_failure_evidence, failure_from_payload
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.domain_registry import DomainSelectionError, resolve_domain_id
from agent.domain_registry import domain_registry
from agent.domain_routing_evidence import (
    DomainRoutingEvidenceError,
    bind_domain_routing_evidence,
    normalize_domain_routing_evidence,
    routing_evidence_identity,
    unavailable_domain_routing_evidence,
)
from agent.recovery_action import (
    project_legacy_interaction_receipt,
)
from agent.scenario import BuildabilityComparisonScenario, ConstrainedBuildabilityComparisonScenario
from agent.service_state import ServiceState
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
    format_result as _format_result,
    normalize_spatial_context as _normalize_spatial_context,
    result_type as _result_type,
)
from agent.service_sessions import (
    dedupe_run_records as _dedupe_run_records,
    validate_session_id as _validate_session_id,
)
from agent.application.run import RunApplication
from agent.application.actions import ActionApplication
from agent.application.decisions import DecisionApplication
from agent.application.interactions import InteractionApplication
from agent.application.sessions import SessionApplication
from agent.application.async_runs import AsyncApplication
from agent.application.catalog import CatalogApplication
from agent.application.run_recovery import RunRecoveryApplication


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
        self._catalog_application = CatalogApplication(
            state=self._state,
            runtime_factory=self._runtime_factory,
            configured_domain_id=self._configured_domain_id,
            configured_domain_pack=self._configured_domain_pack,
            resolved_domain_id=self._resolved_domain_id,
            runtime_context_snapshot=lambda planner, backend, **kwargs: build_runtime_context_snapshot(
                planner, backend, **kwargs
            ),
        )
        self._run_recovery_application = RunRecoveryApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=self._runtime,
            domain_id_provider=self._domain_id,
            resolved_domain_id=lambda: self._resolved_domain_id,
            configured_domain_id=lambda: self._configured_domain_id,
            reserve_action_receipt=self._reserve_action_receipt,
            complete_action_receipt=self._complete_action_receipt,
            attach_async_observability=self._attach_async_observability,
            mark_memory_cancel_requested=self._mark_memory_cancel_requested,
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
        return self._run_recovery_application.memory_run(run_id)

    def _infer_run_runtime_selection(
        self, run_id: str, planner: str, backend: str
    ) -> tuple[str, str]:
        return self._run_recovery_application.infer_runtime_selection(
            run_id, planner, backend
        )

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
        return self._run_recovery_application.retry(
            run_id,
            planner=planner,
            backend=backend,
            export_artifact=export_artifact,
            export_geojson=export_geojson,
            geojson_max_features=geojson_max_features,
            idempotency_key=idempotency_key,
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
        return self._run_recovery_application._retry_payload(
            run_id,
            planner=planner,
            backend=backend,
            export_artifact=export_artifact,
            export_geojson=export_geojson,
            geojson_max_features=geojson_max_features,
        )

    def cancel(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        idempotency_key: str = None,
    ) -> Dict:
        return self._run_recovery_application.cancel(
            run_id,
            planner=planner,
            backend=backend,
            idempotency_key=idempotency_key,
        )

    def get_run(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        return self._run_recovery_application.get_run(
            run_id, planner=planner, backend=backend
        )

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
        return self._run_recovery_application.list_runs(limit=limit)

    def get_run_evidence(self, run_id: str) -> Dict[str, Any]:
        return self._run_recovery_application.get_run_evidence(run_id)

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
        return self._catalog_application.capabilities(planner, backend)

    def workflow_contract(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the selected Domain's workflow catalog and validator inputs."""
        return self._catalog_application.workflow_contract(planner, backend)

    def domains(self) -> Dict[str, Any]:
        """Return the bounded deployment Domain Registry catalog."""
        return self._catalog_application.domains()

    def actions(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the bounded actions declared by the selected Domain Pack."""
        return self._catalog_application.actions(planner, backend)

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
        return self._catalog_application.runtime_capabilities(
            max_files=max_files, planner=planner, backend=backend
        )

    def release_evidence(
        self,
        config_path: str = None,
        max_files: int = 10,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict[str, Any]:
        """Return release evidence from the selected Domain Pack."""
        return self._catalog_application.release_evidence(
            config_path=config_path,
            max_files=max_files,
            planner=planner,
            backend=backend,
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
        return self._catalog_application.register_tool(name, definition, handler)

    def list_dynamic_tools(self) -> Dict:
        return self._catalog_application.list_dynamic_tools()

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
        runtime = self._catalog_application.runtime(planner, backend)
        self._resolved_domain_id = self._catalog_application.resolved_domain_id()
        return runtime

    def _normalize_workflow_payload(
        self,
        workflow: Dict[str, Any] | None,
        planner: str,
        backend: str,
    ) -> Dict[str, Any] | None:
        return self._catalog_application.normalize_workflow(
            workflow, planner, backend
        )

    def _runtime_context(self, planner: str, backend: str) -> Optional[Dict[str, Any]]:
        return self._catalog_application.runtime_context(planner, backend)

    def _submission_runtime_context(
        self, planner: str, backend: str
    ) -> Optional[Dict[str, Any]]:
        return self._catalog_application.submission_runtime_context(planner, backend)

    def _domain_id(self, planner: str, backend: str) -> str:
        return self._catalog_application.domain_id(planner, backend)

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
