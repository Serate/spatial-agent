import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Mapping, Optional

from agent.artifact_store import ArtifactStore
from agent.errors import ToolError
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES
from agent.runtime_factory import build_runtime, build_runtime_context_snapshot
from agent.domain_registry import DomainSelectionError, resolve_domain_id
from agent.recovery_action import (
    project_legacy_interaction_receipt,
)
from agent.service_state import ServiceState

from agent.service_async import (
    async_worker_count as _async_worker_count,
    process_is_alive as _process_is_alive,  # legacy patch/import seam
)
from agent.service_format import (
    exported_geometry_evidence as _exported_geometry_evidence,
    normalize_spatial_context as _normalize_spatial_context,
    tag_geometry_features as _tag_geometry_features,
)
from agent.service_sessions import (
    dedupe_run_records as _dedupe_run_records,
    validate_session_id as _validate_session_id,
)
from agent.application.run import RunApplication
from agent.application.submission import SubmissionApplication
from agent.application.actions import ActionApplication
from agent.application.decisions import DecisionApplication
from agent.application.interactions import InteractionApplication
from agent.application.sessions import SessionApplication
from agent.application.async_runs import AsyncApplication
from agent.application.catalog import (
    CatalogApplication,
    _bind_domain_id,
    _bind_domain_pack,
)
from agent.application.comparisons import ComparisonApplication
from agent.application.inspection import InspectionApplication
from agent.application.run_recovery import RunRecoveryApplication


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
        self._comparison_application = ComparisonApplication(
            run_provider=lambda **kwargs: self.run(**kwargs),
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
        self._submission_application = SubmissionApplication(
            state=self._state,
            runtime_provider=self._runtime,
            workflow_normalizer=self._normalize_workflow_payload,
            domain_id_provider=self._domain_id,
            execute_run=self._run_application.execute,
            attach_async_observability=self._attach_async_observability,
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
        self._inspection_application = InspectionApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            domain_id=lambda: self._resolved_domain_id,
            worker_count=self._async_worker_count,
            async_metrics=self._memory_async_metrics,
        )

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
        validated_plan: Any = None,
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
        return self._submission_application.run(
            request=request,
            session_id=session_id,
            planner=planner,
            backend=backend,
            export_artifact=export_artifact,
            export_geojson=export_geojson,
            geojson_max_features=geojson_max_features,
            timeout_seconds=timeout_seconds,
            spatial_context=spatial_context,
            workflow=workflow,
            validated_plan=validated_plan,
            run_id=run_id,
            preview_fingerprint=preview_fingerprint,
            preview_evidence_fingerprint=preview_evidence_fingerprint,
            require_confirmation=require_confirmation,
            decision_id=decision_id,
            decision_version=decision_version,
            decision_ttl_seconds=decision_ttl_seconds,
            _force_run_id=_force_run_id,
            _async_requested=_async_requested,
            _resolved_request=_resolved_request,
            _domain_routing_evidence=_domain_routing_evidence,
        )

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
        component_fact_handoff: Dict[str, Any] = None,
    ) -> Dict:
        return self._submission_application.preview(
            request=request,
            session_id=session_id,
            planner=planner,
            backend=backend,
            timeout_seconds=timeout_seconds,
            spatial_context=spatial_context,
            workflow=workflow,
            _resolved_request=_resolved_request,
            component_fact_handoff=component_fact_handoff,
        )

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
        return self._inspection_application.metrics()

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

    def execution_contract(
        self,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Dict[str, Any]:
        """Return the structural ToolRegistry/Result Registry contract."""
        runtime = self._runtime(planner, backend)
        resolver = getattr(runtime, "execution_contract", None)
        if not callable(resolver):
            return {}
        value = resolver()
        return dict(value) if isinstance(value, Mapping) else {}

    def extract_request_facts(
        self,
        request: str,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Any:
        """Expose the selected Domain's RequestFacts seam to Composite planning."""
        return self._runtime(planner, backend).extract_request_facts(request)

    def discover(
        self,
        request: str,
        request_facts: Any,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Any:
        """Expose Domain-owned capability discovery through the Service boundary."""
        return self._runtime(planner, backend).discover(request, request_facts)

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Dict[str, Any] = None,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Mapping[str, Any]:
        """Expose Domain-owned workflow selection through the Service boundary."""
        return self._runtime(planner, backend).select_workflow(
            discovery,
            request_facts,
            workflow=workflow,
        )

    def resolve_capability_selection(
        self,
        capability_id: str,
        *,
        request_facts: Any = None,
        selection: Mapping[str, Any] | None = None,
        planner: str = "rule",
        backend: str = "memory",
    ) -> Mapping[str, Any] | None:
        """Resolve a selected capability through the public Service seam."""

        return self._runtime(planner, backend).resolve_capability_selection(
            capability_id,
            request_facts=request_facts,
            selection=selection,
        )

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
        return self._inspection_application.list_memory(
            session_id=session_id,
            query=query,
            limit=limit,
            global_scope=global_scope,
        )

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
        return self._comparison_application.compare_buildability(
            admin_name=admin_name,
            thresholds=thresholds,
            planner=planner,
            backend=backend,
            spatial_context=spatial_context,
        )

    def compare_buildability_regions(
        self,
        admin_names,
        threshold: float = 20,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict:
        return self._comparison_application.compare_buildability_regions(
            admin_names=admin_names,
            threshold=threshold,
            planner=planner,
            backend=backend,
        )

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
        return self._comparison_application.compare_constrained_buildability(
            admin_name=admin_name,
            road_distances=road_distances,
            slope_limit_degrees=slope_limit_degrees,
            planner=planner,
            backend=backend,
            spatial_context=spatial_context,
        )
