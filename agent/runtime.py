import uuid
import inspect
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

from .errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .agent_settings import open_agent_defaults
from .capability_catalog import (
    CAPABILITY_CONTEXT_SCHEMA_VERSION,
    capability_context_summary,
)
from .capability_routing import CAPABILITY_DISCOVERY_SCHEMA_VERSION
from .capability_discovery import enrich_discovery_context
from .context_engineering import ContextBuilder, ContextPacket
from .conversation_turn import build_conversation_turn, resolve_turn_mode
from .domain_contract import (
    DOMAIN_DISCOVERY_SCHEMA_VERSION,
    DomainPack,
    answer_composer as resolve_answer_composer,
    default_permissions,
    default_domain_pack,
    discovery_context,
    extract_request_facts,
    result_registry as resolve_result_registry,
    execute_domain_action,
    clarification_details as resolve_clarification_details,
    evidence_action_guidance as resolve_evidence_action_guidance,
    preflight_tool as run_domain_preflight,
    plan_policy as resolve_plan_policy,
    select_workflow as resolve_workflow_selection,
    request_understanding_guidance,
    selected_capability_ids,
    workflow_context,
    workflow_seam_summary,
)
from .decision_lifecycle import DecisionLifecycleError, DecisionRequest, DecisionStore
from .action_lifecycle import project_action_lifecycle
from agent.evidence.contract import project_capability_catalog_evidence
from .failure_contract import build_failure_evidence
from .answer_generation import fallback_answer_generation_evidence
from .memory import FactMemory
from .models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from .plan_repair import PlanRepairEngine, PlanRepairInput
from .observability import ObservabilityEmitter
from .run_events import new_run_event
from .plan_identity import build_plan_identity
from agent.evidence.revalidation import (
    build_evidence_binding,
    build_evidence_revalidation_gate,
)
from .plan_quality import diagnose_plan, project_plan_quality_evidence
from .plan_policy import build_plan_policy_evidence
from .planner_selection import build_planner_selection_evidence
from .planner_context import (
    PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
    project_planner_sections,
)
from .workflow_selection import (
    build_workflow_selection_evidence,
    normalize_workflow_selection_evidence,
)
from .planner import Planner
from .replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from .request_model import RequestFacts
from .runtime_context import build_runtime_context
from .tools import ToolRegistry
from .runtime_core import projection as _runtime_projection
from .runtime_core.projection import (
    append_execution_degradation_notice as _append_execution_degradation_notice,
)
from .runtime_core import planning as _runtime_planning
from .runtime_core import execution as _runtime_execution
from .runtime_core.execution_policy import ExecutionPolicyResolver, build_execution_policy
from .runtime_core.capabilities import RuntimeCapabilitySurface
from .runtime_core.control import RunControl
from .runtime_core.decision_resume import RuntimeDecisionResume
from .runtime_core.planning_surface import RuntimePlanningSurface
from .runtime_core.preview import RuntimePreviewSurface
from .runtime_core.plan_evidence import (
    build_plan_evidence as _build_plan_evidence_canonical,
    planner_source as _planner_source,
    safe_small_mapping as _safe_small_mapping,
)
from .runtime_core.recovery import RuntimeRecoverySurface
from .runtime_core.run_lifecycle import RuntimeRunLifecycle
from .runtime_state import (
    InMemoryConversationStore,
    InMemoryStateStore,
    PendingClarification,
)
from .tooling import InMemoryToolApprovalStore, rehydrate_approved_tools


class AgentRuntime:
    """The orchestration seam for planning, validation, execution, and tracing."""

    def __init__(
        self,
        planner: Planner,
        registry: ToolRegistry,
        state_store: Optional[InMemoryStateStore] = None,
        conversation_store: Optional[InMemoryConversationStore] = None,
        answer_composer: Optional[Any] = None,
        answer_generator: Optional[Any] = None,
        proposal_validator: Optional[Any] = None,
        context_builder: Optional[ContextBuilder] = None,
        max_steps: int = 12,
        max_retries: int = 2,
        replan_policy: Optional[ReplanningPolicy] = None,
        plan_repair_engine: Optional[PlanRepairEngine] = None,
        decision_store: Optional[DecisionStore] = None,
        approval_store: Optional[Any] = None,
        memory: Optional[FactMemory] = None,
        observability: Optional[ObservabilityEmitter] = None,
        backend_name: str = "unknown",
        planner_name: str = "unknown",
        domain_pack: Optional[DomainPack] = None,
        allowed_permissions: Optional[Iterable[str]] = None,
        approved_tools: Optional[Iterable[str]] = None,
        require_dependency_evidence: bool = False,
        event_sink: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self._planner = planner
        self._registry = registry
        self._state_store = state_store or InMemoryStateStore()
        self._conversation_store = conversation_store or InMemoryConversationStore()
        self._backend_name = backend_name
        self._planner_name = str(planner_name or "unknown")[:32]
        self._domain_pack = domain_pack or default_domain_pack()
        self._result_registry = resolve_result_registry(self._domain_pack)
        execution_defaults = open_agent_defaults()
        self._agent_settings = dict(execution_defaults)
        self._answer_composer = answer_composer or resolve_answer_composer(self._domain_pack)
        self._answer_generator = answer_generator
        self._proposal_validator = proposal_validator
        self._context_builder = context_builder or ContextBuilder()
        self._max_steps = max_steps
        self._max_retries = max_retries
        self._replan_policy = replan_policy or ReplanningPolicy()
        self._decision_store = decision_store
        self._approval_store = approval_store or InMemoryToolApprovalStore()
        self._approval_rehydration = self._restore_approved_tools()
        self._execution_policy_resolver = ExecutionPolicyResolver(
            known_tools=self._registry.names,
            max_actions=max(
                1,
                min(
                    128,
                    int(max_steps),
                    int(execution_defaults["react_max_actions"]),
                ),
            ),
            max_turns=int(execution_defaults["react_max_turns"]),
            network_enabled=bool(execution_defaults["web_search_enabled"]),
            tool_proposals_enabled=bool(execution_defaults["tool_proposals_enabled"]),
            # Older custom Domain Packs use result labels that are not in the
            # default GIS registry. Their own plan_policy/result contract is
            # still enforced; the global registry check remains opt-in until
            # those packs publish a complete result registry.
            enforce_known_result_profiles=False,
        )
        approval_guard = getattr(self._registry, "set_approval_guard", None)
        if callable(approval_guard):
            approval_guard(self._approval_gate)
        self._plan_repair_engine = plan_repair_engine or PlanRepairEngine(
            self._planner,
            self._replan_policy,
            available_tools=lambda: list(self._registry.names),
            validate_plan=self._validate_plan_for_execution,
            control_check=self._check_control,
        )
        self._memory = memory
        self._observability = observability
        self._event_sink = event_sink
        # The selected Domain Pack owns its default grant. Callers can still
        # narrow or replace it explicitly for a deployment.
        self._allowed_permissions = {
            str(item) for item in (
                allowed_permissions
                if allowed_permissions is not None
                else default_permissions(self._domain_pack)
            ) if str(item)
        }
        self._approved_tools = {
            str(item) for item in (approved_tools or []) if str(item)
        }
        self._require_dependency_evidence = bool(require_dependency_evidence)
        self._capability_surface = RuntimeCapabilitySurface(
            domain_pack=self._domain_pack,
            backend_name=self._backend_name,
            registry=self._registry,
            domain_id=lambda: self.domain_id,
            runtime_context=self.runtime_context,
        )
        self._control = RunControl(self._state_store)
        self._planning_surface = RuntimePlanningSurface(
            planner=self._planner,
            registry=self._registry,
            domain_pack=self._domain_pack,
            backend_name=self._backend_name,
            context_builder=self._context_builder,
            conversation_store=self._conversation_store,
            memory=self._memory,
            max_steps=self._max_steps,
            plan_repair_engine=self._plan_repair_engine,
            replan_policy=self._replan_policy,
            domain_id=lambda: self.domain_id,
            capability_context_evidence=self._capability_surface.context_evidence,
            control_check=self._check_control,
            execution_policy_resolver=self._execution_policy_resolver,
        )
        self._run_lifecycle = RuntimeRunLifecycle(self)
        self._decision_resume = RuntimeDecisionResume(self)
        self._recovery = RuntimeRecoverySurface(self)
        self._preview = RuntimePreviewSurface(self)
        self._run_span_ids: Dict[str, str] = {}

    def approval_rehydration(self) -> Dict[str, Any]:
        """Return safe evidence for approved binding restoration."""
        return dict(self._approval_rehydration)

    def _restore_approved_tools(self) -> Dict[str, Any]:
        """Restore approved records before planning sees the Registry names."""
        listing = getattr(self._approval_store, "list", None)
        records = []
        if callable(listing):
            try:
                records = listing(domain_id=self.domain_id, limit=64, status="approved")
            except Exception:
                records = []
        factory = getattr(self._proposal_validator, "handler_for", None)
        return rehydrate_approved_tools(
            registry=self._registry,
            records=records,
            handler_factory=factory,
            domain_id=self.domain_id,
        )

    @property
    def domain_id(self) -> str:
        """Return the selected Domain Pack identity for service boundaries."""
        return str(getattr(self._domain_pack, "domain_id", "unknown"))[:80]

    def runtime_context(self) -> Dict[str, Any]:
        """Return the immutable configuration evidence for this Runtime."""
        return build_runtime_context(
            domain_id=self.domain_id,
            planner=self._planner_name,
            backend=self._backend_name,
            tool_provider=self._registry.provider_info(),
            permissions=self._allowed_permissions,
            approved_tools=self._approved_tools,
            require_dependency_evidence=self._require_dependency_evidence,
        )

    def result_registry(self):
        """Return the result metadata registry selected by this Domain Pack."""
        return self._result_registry

    def domain_actions(self) -> Dict[str, Any]:
        """Return the selected Domain Pack's bounded action catalog."""
        return self._capability_surface.domain_actions()

    def execute_domain_action(
        self,
        action_id: str,
        payload: Mapping[str, Any],
        *,
        context: Any = None,
    ) -> Any:
        """Execute a declared action through the Domain Pack seam."""
        return execute_domain_action(
            self._domain_pack,
            action_id,
            payload,
            context=context,
        )

    def capability_catalog(self) -> Mapping[str, Any]:
        """Return the selected Domain Pack's bounded capability catalog."""
        return self._capability_surface.capability_catalog()

    def workflow_template_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Return the selected Domain's declarative workflow catalog."""
        return self._capability_surface.workflow_template_catalog()

    def workflow_contract(self) -> Dict[str, Any]:
        """Return bounded catalog and validator allowlists for HTTP seams."""
        return self._capability_surface.workflow_contract()

    def execution_contract(self) -> Dict[str, Any]:
        """Return metadata for domain-neutral Composite readiness checks."""
        return self._capability_surface.execution_contract()

    def extract_request_facts(self, request: str) -> Any:
        """Expose the selected Domain's bounded RequestFacts seam."""
        return extract_request_facts(self._domain_pack, str(request or ""))

    def discover(self, request: str, request_facts: Any) -> Any:
        """Expose Domain-owned capability discovery to open Composite planning."""
        method = getattr(self._domain_pack, "discover", None)
        if not callable(method):
            return {
                "domain_id": self.domain_id,
                "reason_code": "discover_not_declared",
            }
        return method(str(request or ""), request_facts)

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Expose Domain-owned workflow selection without Runtime policy."""
        return resolve_workflow_selection(
            self._domain_pack,
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
    ) -> Mapping[str, Any] | None:
        """Resolve a selected capability into Domain-owned workflow data."""

        return self._capability_surface.resolve_capability_selection(
            capability_id,
            request_facts=request_facts,
            selection=selection,
        )

    def runtime_capabilities(self, *, max_files: int = 10) -> Dict[str, Any]:
        """Return generic provider evidence plus optional domain evidence."""
        return self._capability_surface.runtime_capabilities(max_files=max_files)

    def release_evidence(
        self,
        *,
        config_path: Optional[str] = None,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        """Return release evidence through the selected Domain Pack.

        Release/data publication policy is deliberately outside this Module's
        implementation. The Domain Pack owns the provider; the Runtime only
        validates the bounded request and returns its JSON-safe projection.
        """
        return self._capability_surface.release_evidence(
            config_path=config_path,
            max_files=max_files,
        )

    def run(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        run_id: Optional[str] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        validated_plan: Optional[TaskPlan] = None,
        expected_plan_fingerprint: Optional[str] = None,
        expected_evidence_fingerprint: Optional[str] = None,
        require_confirmation: bool = False,
        decision_evidence: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
        decision_version: Optional[int] = None,
        decision_input: Optional[Mapping[str, Any]] = None,
        decision_ttl_seconds: Optional[float] = 1800.0,
        resolved_request_override: Optional[str] = None,
    ) -> AgentRunResult:
        return self._run_lifecycle.run(
            request=request,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
            workflow=workflow,
            validated_plan=validated_plan,
            expected_plan_fingerprint=expected_plan_fingerprint,
            expected_evidence_fingerprint=expected_evidence_fingerprint,
            require_confirmation=require_confirmation,
            decision_evidence=decision_evidence,
            decision_id=decision_id,
            decision_version=decision_version,
            decision_input=decision_input,
            decision_ttl_seconds=decision_ttl_seconds,
            resolved_request_override=resolved_request_override,
        )
    def _resume_decision(
        self,
        result: AgentRunResult,
        *,
        decision_id: str,
        decision_version: Optional[int],
        timeout_seconds: Optional[float],
    ) -> AgentRunResult:
        return self._decision_resume.resume(
            result,
            decision_id=decision_id,
            decision_version=decision_version,
            timeout_seconds=timeout_seconds,
        )
    def preview(
        self,
        request: str,
        session_id: str = "default",
        timeout_seconds: Optional[float] = None,
        workflow: Optional[Mapping[str, Any]] = None,
        resolved_request_override: Optional[str] = None,
        component_fact_handoff: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._preview.preview(
            request=request,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            workflow=workflow,
            resolved_request_override=resolved_request_override,
            component_fact_handoff=component_fact_handoff,
        )
    def clear_session(self, session_id: str) -> None:
        """Clear runtime-only clarification state for a conversation."""
        self._conversation_store.clear_pending(session_id)

    def get_run(self, run_id: str) -> Optional[AgentRunResult]:
        return self._state_store.get(run_id)

    def cancel(self, run_id: str) -> AgentRunResult:
        return self._recovery.cancel(run_id)

    def retry_failed(self, run_id: str) -> AgentRunResult:
        return self._recovery.retry_failed(run_id)
    def export_result(self, result_ref: str, max_features: int = 100) -> Dict:
        return self._registry.export_result(result_ref, max_features=max_features)

    def _execution_policy_evidence(
        self,
        plan: TaskPlan,
        workflow: Optional[Mapping[str, Any]] = None,
        *,
        requires_confirmation: bool = False,
        policy_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project the resolved policy plus legacy Registry governance evidence."""
        policy = self._planning_surface.resolve_execution_policy(
            plan,
            workflow,
            requires_confirmation=requires_confirmation,
            policy_mode=policy_mode,
        )
        tools = []
        seen = set()
        for step in plan.steps:
            if step.tool in seen:
                continue
            seen.add(step.tool)
            tools.append(self._registry.governance_for(step.tool))
        policy = dict(policy)
        # Keep the M94/M110 evidence fields so existing result, artifact and
        # acceptance consumers remain readable while the core policy now
        # carries the actual execution mode and bounded allowlists.
        policy.update(
            {
                "provider_id": self._registry.provider_info().get("id", "unknown"),
                "dependency_evidence_required": self._require_dependency_evidence,
                "allowed_permission_count": len(self._allowed_permissions),
                "wildcard_permission": "*" in self._allowed_permissions,
                "approved_tool_count": len(self._approved_tools),
                "tools": tools[:32],
            }
        )
        return policy

    @staticmethod
    def _unavailable_execution_policy(reason_code: str) -> Dict[str, Any]:
        """Return a safe policy projection when no executable plan exists."""

        return build_execution_policy(
            mode="react",
            state="unavailable",
            source="runtime",
            reason_code=str(reason_code or "execution_policy_unavailable")[:96],
        )

    def _plan_policy_evidence(
        self,
        plan: Optional[TaskPlan],
        workflow: Optional[Mapping[str, Any]],
        *,
        policy_mode: Optional[str] = None,
        state: str = "accepted",
        reason_code: Optional[str] = None,
        repair_lineage: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Project Domain policy metadata through one generic Runtime seam."""
        if policy_mode == "open_react" and workflow is None:
            domain_policy = {
                "schema_version": "spatial-agent.plan-policy.v1",
                "available": True,
                "domain_id": self.domain_id,
                "policy_id": "runtime.open_react",
                "source": "open_react",
                "selected_by": "runtime",
                "allowed_tools": [
                    step.tool for step in plan.steps
                ] if isinstance(plan, TaskPlan) else [],
                "result_types": [
                    str(plan.output.get("type") or "")
                ] if isinstance(plan, TaskPlan) and isinstance(plan.output, Mapping) else [],
            }
        else:
            domain_policy = resolve_plan_policy(
                self._domain_pack,
                plan,
                workflow=workflow,
            )
        return build_plan_policy_evidence(
            plan,
            domain_policy=domain_policy,
            workflow=workflow,
            domain_id=self.domain_id,
            state=state,
            reason_code=reason_code,
            repair_lineage=tuple(repair_lineage or ()),
        )

    def _failure_plan_evidence(
        self,
        *,
        plan: Optional[TaskPlan],
        workflow: Optional[Mapping[str, Any]],
        state: str,
        reason_code: str,
        context_packet: Optional[ContextPacket] = None,
        repair_lineage: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create planning evidence even when no executable plan survived."""
        selection = None
        if context_packet is not None:
            sections = (
                context_packet.source_payload or context_packet.payload or {}
            ).get("sections", {})
            if isinstance(sections, Mapping):
                selection = sections.get("workflow_selection")
        return {
            "available": False,
            "planner_kind": type(self._planner).__name__,
            "source": _planner_source(type(self._planner).__name__, workflow),
            "domain_id": self.domain_id,
            "step_count": len(plan.steps) if isinstance(plan, TaskPlan) else 0,
            "tool_names": [step.tool for step in plan.steps]
            if isinstance(plan, TaskPlan)
            else [],
            "plan_policy": self._plan_policy_evidence(
                plan,
                workflow,
                state=state,
                reason_code=reason_code,
                repair_lineage=repair_lineage,
            ),
            "execution_policy": self._unavailable_execution_policy(reason_code),
            "workflow_selection": normalize_workflow_selection_evidence(selection),
            "planner_selection": build_planner_selection_evidence(
                plan,
                selection,
                planner_kind=type(self._planner).__name__,
            ),
        }

    def _build_context_packet(
        self,
        request: str,
        resolved_request: str,
        session_id: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        request_facts: Optional[RequestFacts] = None,
    ) -> ContextPacket:
        return self._planning_surface.build_context_packet(
            request,
            resolved_request,
            session_id,
            workflow,
            request_facts=request_facts,
        )

    def _capability_context_evidence(self) -> Mapping[str, Any]:
        return self._capability_surface.context_evidence()

    def _resolve_request(
        self,
        request: str,
        session_id: str,
        *,
        pending: Optional[PendingClarification] = None,
        turn_advice: Optional[Mapping[str, Any]] = None,
    ) -> str:
        return self._planning_surface.resolve_request(
            request,
            session_id,
            pending=pending,
            turn_advice=turn_advice,
        )

    def _require_workflow_selection(
        self,
        context_packet: ContextPacket,
        workflow: Optional[Mapping[str, Any]],
    ) -> None:
        """Stop before planning when a Domain declares an ambiguous choice.

        Candidate discovery is descriptive by default. A Domain Pack may
        explicitly mark the projection as ``ambiguous`` when lexical or
        policy routing cannot safely choose one capability. The public
        Runtime owns the lifecycle transition, while the Domain remains the
        owner of candidate semantics. An explicit workflow is already a
        user decision and therefore bypasses this gate.
        """
        return self._planning_surface.require_workflow_selection(context_packet, workflow)

    def _planner_metrics(self) -> Optional[Dict]:
        metrics = getattr(self._planner, "metrics", None)
        return metrics() if callable(metrics) else None

    def _compose_answer(self, result: AgentRunResult, *, on_delta=None) -> str:
        """Generate a natural-language answer with a deterministic fallback.

        The Domain Composer remains responsible for the trusted fallback.  A
        model may rewrite only the bounded facts assembled by the answer
        generator; it never replaces tool execution or evidence ownership.
        """

        fallback = self._answer_composer.compose(result)
        generator = self._answer_generator
        generate = getattr(generator, "generate", None) if generator is not None else None
        if not callable(generate):
            result.answer_generation_evidence = fallback_answer_generation_evidence(
                "answer_generation_disabled"
            )
            return _append_execution_degradation_notice(result, fallback)
        try:
            stream_generate = getattr(generator, "generate_stream", None)
            if callable(on_delta) and callable(stream_generate):
                generated = stream_generate(result, on_delta=on_delta)
            else:
                generated = generate(result)
            answer = getattr(generated, "answer", None)
            evidence = getattr(generated, "evidence", None)
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("answer generator returned an empty answer")
            result.answer_generation_evidence = (
                dict(evidence) if isinstance(evidence, Mapping) else
                fallback_answer_generation_evidence("answer_generation_evidence_missing")
            )
            return _append_execution_degradation_notice(result, answer.strip())
        except Exception:
            failure_evidence = getattr(generator, "failure_evidence", None)
            if callable(failure_evidence):
                result.answer_generation_evidence = failure_evidence(
                    "answer_generation_failed"
                )
            else:
                result.answer_generation_evidence = fallback_answer_generation_evidence(
                    "answer_generation_failed"
                )
            return _append_execution_degradation_notice(result, fallback)

    def _validate_or_repair_plan(
        self,
        plan: TaskPlan,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        deadline: Optional[float],
        result: Optional[AgentRunResult] = None,
        run_id: Optional[str] = None,
        context_packet: Optional[ContextPacket] = None,
    ) -> tuple[TaskPlan, Optional[Dict[str, Any]]]:
        replacement, event = self._planning_surface.validate_or_repair(
            plan,
            request,
            workflow,
            deadline=deadline,
            run_id=run_id,
            context_packet=context_packet,
        )
        if result is not None and event is not None:
            result.replan_events.append(event)
        return replacement, event

    def _validate_plan_for_execution(
        self, plan: TaskPlan, workflow: Optional[Mapping[str, Any]]
    ) -> None:
        return self._planning_surface.validate_plan_for_execution(plan, workflow)

    def _try_plan_repair(
        self,
        request: str,
        plan: TaskPlan,
        workflow: Optional[Mapping[str, Any]],
        exc: Exception,
        deadline: Optional[float],
        run_id: Optional[str],
        context_packet: Optional[ContextPacket],
    ) -> tuple[Optional[TaskPlan], Optional[Dict[str, Any]]]:
        del exc
        return self._planning_surface.validate_or_repair(
            plan,
            request,
            workflow,
            deadline=deadline,
            run_id=run_id,
            context_packet=context_packet,
        )

    def _plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        context_packet: ContextPacket,
    ) -> TaskPlan:
        return self._planning_surface.plan(request, workflow, context_packet)

    def _validate_plan(self, plan: TaskPlan) -> None:
        return self._planning_surface.validate_plan(plan)

    def _execute_step(
        self,
        run_id: str,
        deadline: Optional[float],
        step_run: StepRun,
        step: PlanStep,
        completed: Set[str],
        completed_results: Dict[str, Dict[str, Any]],
    ) -> None:
        hooks = _runtime_execution.StepExecutionHooks(
            registry=self._registry,
            max_retries=self._max_retries,
            preflight=self._enforce_preflight_policy,
            control_check=self._check_control,
            emit_step=self._emit_step_event,
            now=_utc_now,
        )
        return _runtime_execution.execute_step(
            hooks,
            run_id,
            deadline,
            step_run,
            step,
            completed,
            completed_results,
        )

    def _try_replan(
        self,
        result: AgentRunResult,
        request: str,
        index: int,
        step_run: StepRun,
        step: PlanStep,
        exc: Exception,
        completed: Set[str],
        completed_results: Dict[str, Dict[str, Any]],
        replan_count: int,
        deadline: Optional[float],
    ) -> bool:
        del exc
        outcome = self._planning_surface.try_replan(
            original=result.plan,
            existing_steps=result.steps,
            request=request,
            workflow=result.workflow,
            step=step,
            step_run=step_run,
            completed=completed,
            completed_results=completed_results,
            replan_count=replan_count,
            deadline=deadline,
        )
        if outcome is None:
            return False
        result.plan = outcome.plan
        result.steps = outcome.steps
        result.replan_events.append(outcome.event)
        if isinstance(result.plan_evidence, dict):
            result.plan_evidence["plan_quality"] = project_plan_quality_evidence(
                outcome.quality_after
            )
            result.plan_evidence["plan_policy"] = self._plan_policy_evidence(
                outcome.plan,
                result.workflow,
                state="accepted",
                reason_code="execution_replan_accepted",
                repair_lineage=result.replan_events,
            )
            result.plan_evidence["execution_policy"] = self._execution_policy_evidence(
                outcome.plan,
                result.workflow,
            )
            result.plan_evidence["plan_identity"] = build_plan_identity(
                outcome.plan,
                request=result.request,
                resolved_request=result.resolved_request or result.request,
                workflow=result.workflow,
                planner_kind=type(self._planner).__name__,
            )
        return True

    def _tool_for_step(self, plan: TaskPlan, step_id: str) -> Optional[str]:
        return self._planning_surface._tool_for_step(plan, step_id)

    def _enforce_preflight_policy(
        self,
        tool: str,
        arguments: Dict[str, Any],
        completed_results: Dict[str, Dict[str, Any]],
    ) -> None:
        governance = self._registry.governance_for(tool)
        required_permissions = governance.get("permissions") or []
        missing_permissions = [
            permission
            for permission in required_permissions
            if permission not in self._allowed_permissions
            and "*" not in self._allowed_permissions
        ]
        if missing_permissions:
            raise ToolError(
                "工具权限门控阻止 {}：缺少 {}".format(
                    tool, ", ".join(missing_permissions)
                ),
                category="policy",
                code="permission_denied",
                retryable=False,
            )
        if governance.get("requires_approval") and tool not in self._approved_tools:
            raise ToolError(
                "工具审批门控阻止 {}：该工具需要显式审批".format(tool),
                category="policy",
                code="approval_required",
                retryable=False,
            )

        run_domain_preflight(
            self._domain_pack,
            tool,
            arguments,
            completed_results,
            required_datasets=self._registry.data_dependencies(tool, arguments),
            require_dependency_evidence=self._require_dependency_evidence,
        )

    def _approval_gate(self, definition: Mapping[str, Any]) -> None:
        """Fail closed when a dynamically published tool lost approval."""
        approval_id = str(definition.get("approval_id") or "").strip()
        if not approval_id:
            return
        getter = getattr(self._approval_store, "get", None)
        record = getter(approval_id, domain_id=self.domain_id) if callable(getter) else None
        if record is None or getattr(record, "status", None) != "approved":
            raise ToolError(
                "工具审批已失效，禁止执行",
                category="policy",
                code="approval_required",
                retryable=False,
            )
        expected_version = int(definition.get("approval_version") or 0)
        expected_fingerprint = str(definition.get("approval_fingerprint") or "")
        if expected_version != int(getattr(record, "version", 0)) or expected_fingerprint != str(
            getattr(record, "receipt_fingerprint", "")
        ):
            raise ToolError(
                "工具审批版本或指纹已漂移，禁止执行",
                category="policy",
                code="approval_version_mismatch",
                retryable=False,
            )

    def _remember(self, result: AgentRunResult) -> None:
        """Persist one bounded memory fact for a completed run."""
        if self._memory is not None:
            self._memory.remember(result)

    def _emit_run_event(self, result: AgentRunResult) -> None:
        if self._observability is None:
            return
        span_id = self._run_span_ids.get(result.run_id)
        run_category = _run_error_category(result)
        attributes = {
            "session_id": result.session_id,
            "result_type": _result_type_for_observability(result),
            "error_category": run_category,
            "error_code": (result.failure or {}).get("code") or result.error_code,
            "failure_phase": (result.failure or {}).get("phase"),
            "failure_retryable": (result.failure or {}).get("retryable"),
            "replan_count": len(result.replan_events),
            "memory_fact_count": len(self._memory.recall(session_id=result.session_id or "default"))
            if self._memory is not None
            else 0,
        }
        attributes = {key: value for key, value in attributes.items() if value is not None}
        self._observability.emit_run(
            run_id=result.run_id,
            session_id=result.session_id,
            name="{}:{}".format(type(self._planner).__name__, _result_type_for_observability(result)),
            status=result.status.value,
            duration_ms=_run_duration_ms(result),
            attributes=attributes,
            span_id=span_id,
        )
        if span_id:
            self._run_span_ids.pop(result.run_id, None)

    def _emit_progress_event(
        self,
        run_id: str,
        *,
        phase: str,
        kind: str,
        status: str,
        message: str,
        data: Optional[Mapping[str, Any]] = None,
        terminal: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Append one safe realtime event without changing run semantics."""
        event = new_run_event(
            run_id=run_id,
            phase=phase,
            kind=kind,
            status=status,
            message=message,
            data=data,
            terminal=terminal,
        )
        sink = self._event_sink
        if not callable(sink):
            sink = getattr(self._state_store, "append_run_event", None)
        if not callable(sink):
            return None
        try:
            return sink(event)
        except Exception:
            # Realtime delivery must never make a valid Agent run fail. The
            # durable result and existing observability remain authoritative.
            return None

    def _emit_step_event(
        self,
        run_id: str,
        step_run: StepRun,
    ) -> None:
        if self._observability is None:
            return
        parent_span_id = self._run_span_ids.get(run_id)
        attributes = {
            "attempts": step_run.attempts,
            "error_category": step_run.error_category or failure_category(step_run.error),
            "error_code": step_run.error_code,
        }
        attributes = {key: value for key, value in attributes.items() if value is not None}
        self._observability.emit_step(
            run_id=run_id,
            parent_span_id=parent_span_id,
            name=step_run.tool,
            status=step_run.status,
            duration_ms=step_run.latency_ms,
            attributes=attributes,
        )

    def _check_control(self, run_id: str, deadline: Optional[float]) -> None:
        return self._control.check(run_id, deadline)

    def _block_remaining_steps(
        self, steps, start_index: int, failed_step_id: str, reason: str
    ) -> None:
        return _runtime_execution.block_remaining_steps(
            steps,
            start_index,
            failed_step_id,
            reason,
        )

def _plan_to_dict(plan: TaskPlan) -> Dict[str, Any]:
    return _runtime_projection.plan_to_dict(plan)


def _plan_dag(plan: TaskPlan) -> Dict[str, Any]:
    return _runtime_projection.plan_dag(plan)


def _compact_workflow_templates_for_context(
    templates: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _runtime_projection.compact_workflow_templates(templates, selection)


def _build_plan_evidence(
    plan: TaskPlan,
    workflow: Optional[Mapping[str, Any]],
    context_packet: ContextPacket,
    *,
    planner_kind: str,
) -> Dict[str, Any]:
    """Compatibility facade for the canonical plan evidence projection."""
    return _build_plan_evidence_canonical(
        plan,
        workflow,
        context_packet,
        planner_kind=planner_kind,
    )
def _replan_context(feedback: Mapping[str, Any]) -> Dict[str, Any]:
    return _runtime_projection.replan_context(feedback)


def _utc_now() -> str:
    return _runtime_projection.utc_now()


def _capability_evidence_cache_ttl() -> float:
    return _runtime_projection.capability_evidence_cache_ttl()


def _resolve_result_references(value: Any, results: Dict[str, Dict[str, Any]]) -> Any:
    return _runtime_projection.resolve_result_references(value, results)


def _result_type_for_observability(result: AgentRunResult) -> str:
    return _runtime_projection.result_type_for_observability(result)


def _run_duration_ms(result: AgentRunResult) -> Optional[float]:
    return _runtime_projection.run_duration_ms(result)


def _record_run_failure(
    result: AgentRunResult,
    exc: Exception,
    *,
    phase: Optional[str] = None,
) -> None:
    """Promote the final failure classification to the run-level contract."""
    failed_steps = [
        step
        for step in reversed(result.steps)
        if step.status == "FAILED" or step.error
    ]
    failed_step = failed_steps[0] if failed_steps else None
    category = (
        getattr(exc, "category", None)
        or (failed_step.error_category if failed_step else None)
        or _run_error_category(result)
    )
    code = getattr(exc, "code", None) or (failed_step.error_code if failed_step else None)
    retryable = getattr(exc, "retryable", None)
    if retryable is None and failed_step is not None:
        retryable = failed_step.retryable
    result.error_category = str(category)[:64] if category else None
    result.error_code = str(code)[:96] if code else None
    result.failure = build_failure_evidence(
        status=result.status.value,
        category=result.error_category,
        code=result.error_code,
        phase=phase,
        retryable=retryable,
    )
    # Keep the legacy top-level fields aligned with the canonical evidence.
    result.error_category = result.failure["category"]
    result.error_code = result.failure["code"]


def _run_error_category(result: AgentRunResult) -> Optional[str]:
    return _runtime_projection.run_error_category(result)
