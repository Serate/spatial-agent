"""Runtime planning and replanning surface.

This module owns the planning-side coordination that used to live in the
Runtime orchestrator: request/context preparation, planner invocation,
workflow validation, bounded plan repair, and execution-time replanning.
It deliberately returns small data objects and leaves run persistence,
evidence projection, and step dispatch to the Runtime's other seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

from ..capability_catalog import capability_context_summary
from ..capability_discovery import enrich_discovery_context
from ..context_engineering import ContextBuilder, ContextPacket
from ..conversation_turn import resolve_turn_mode
from ..domain_contract import (
    DomainPack,
    discovery_context,
    evidence_action_guidance as resolve_evidence_action_guidance,
    extract_request_facts,
    plan_policy as resolve_plan_policy,
    request_understanding_guidance,
    select_workflow as resolve_workflow_selection,
    selected_capability_ids,
    workflow_context,
    workflow_seam_summary,
)
from ..evidence_contract import project_capability_catalog_evidence
from ..errors import ClarificationNeeded, ToolError
from ..models import PlanStep, StepRun, TaskPlan
from ..plan_repair import PlanRepairEngine, PlanRepairInput
from ..plan_quality import diagnose_plan, project_plan_quality_evidence
from ..replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from ..request_model import RequestFacts
from ..workflow_selection import build_workflow_selection_evidence
from ..planner_context import (
    PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
    project_planner_sections,
)
from .execution_policy import ExecutionPolicyResolver
from .planning import invoke_planner, require_workflow_selection, validate_plan
from .projection import compact_workflow_templates, replan_context


@dataclass(frozen=True)
class ReplanOutcome:
    """Bounded mutation data returned after an accepted execution replan."""

    plan: TaskPlan
    steps: List[StepRun]
    new_step_ids: List[str]
    event: Dict[str, Any]
    quality_before: Mapping[str, Any]
    quality_after: Mapping[str, Any]


class RuntimePlanningSurface:
    """Deep planning module behind the Runtime planning interface."""

    def __init__(
        self,
        *,
        planner: Any,
        registry: Any,
        domain_pack: DomainPack,
        backend_name: str,
        context_builder: Optional[ContextBuilder],
        conversation_store: Any,
        memory: Any,
        max_steps: int,
        plan_repair_engine: PlanRepairEngine,
        replan_policy: ReplanningPolicy,
        domain_id: Callable[[], str],
        capability_context_evidence: Callable[[], Mapping[str, Any]],
        control_check: Callable[[str, Optional[float]], None],
        execution_policy_resolver: Optional[ExecutionPolicyResolver] = None,
    ) -> None:
        self._planner = planner
        self._registry = registry
        self._domain_pack = domain_pack
        self._backend_name = str(backend_name or "unknown")[:80]
        self._context_builder = context_builder or ContextBuilder()
        self._conversation_store = conversation_store
        self._memory = memory
        self._max_steps = max_steps
        self._plan_repair_engine = plan_repair_engine
        self._replan_policy = replan_policy
        self._domain_id = domain_id
        self._capability_context_evidence = capability_context_evidence
        self._control_check = control_check
        self._execution_policy_resolver = execution_policy_resolver or ExecutionPolicyResolver(
            known_tools=self._registry.names,
            enforce_known_result_profiles=False,
            max_actions=max(1, min(128, int(max_steps))),
        )

    def build_context_packet(
        self,
        request: str,
        resolved_request: str,
        session_id: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        request_facts: Optional[RequestFacts] = None,
    ) -> ContextPacket:
        """Build the bounded planner context from Domain-owned catalog data."""
        memory_reader = getattr(self._memory, "context_section", None)
        memory_section = memory_reader(session_id) if callable(memory_reader) else None
        spatial_request = request_facts or extract_request_facts(
            self._domain_pack, resolved_request
        )
        discovery = self._domain_pack.discover(resolved_request, spatial_request)
        discovery_payload = discovery_context(
            discovery,
            domain_id=str(getattr(self._domain_pack, "domain_id", "unknown")),
        )
        understanding_payload = request_understanding_guidance(self._domain_pack)
        catalog = self._domain_pack.capability_catalog(environment=self._backend_name)
        catalog = project_capability_catalog_evidence(
            catalog,
            runtime_evidence=self._capability_context_evidence(),
        )
        discovery_payload = enrich_discovery_context(
            discovery_payload,
            spatial_request,
            catalog,
            max_suggestions=4,
        )
        domain_selection = resolve_workflow_selection(
            self._domain_pack,
            discovery_payload,
            spatial_request,
            workflow=workflow,
        )
        workflow_selection = build_workflow_selection_evidence(
            discovery=discovery_payload,
            domain_selection=domain_selection,
            workflow=workflow,
            capability_catalog=catalog,
            domain_seams=workflow_seam_summary(self._domain_pack),
            request_facts=spatial_request,
            domain_id=self._domain_id(),
        )
        guidance = resolve_evidence_action_guidance(
            self._domain_pack,
            workflow_selection,
            request_facts=spatial_request,
        )
        workflow_selection = build_workflow_selection_evidence(
            discovery=discovery_payload,
            domain_selection=domain_selection,
            workflow=workflow,
            capability_catalog=catalog,
            domain_seams=workflow_seam_summary(self._domain_pack),
            request_facts=spatial_request,
            domain_id=self._domain_id(),
            evidence_action_guidance=guidance,
        )
        templates = compact_workflow_templates(
            workflow_context(self._domain_pack),
            workflow_selection,
        )
        capability_catalog = capability_context_summary(
            catalog=catalog,
            tool_definitions=self._registry.definition_summary(),
            tool_provider=self._registry.provider_info(),
            tool_provider_health=self._registry.provider_health(),
            tool_governance=self._registry.governance_summary(max_tools=4),
            selected_capability_ids=selected_capability_ids(discovery)[:1],
            max_capabilities=1,
            max_tools=12,
        )
        planner_sections = project_planner_sections(
            capability_discovery=discovery_payload,
            capability_catalog=capability_catalog,
            workflow_selection=workflow_selection,
            workflow_templates=templates,
        )
        return self._context_builder.build(
            request=request,
            resolved_request=resolved_request,
            session_id=session_id,
            workflow=workflow,
            available_tools=self._registry.names,
            planner_kind=type(self._planner).__name__,
            spatial_request=spatial_request.as_context_dict(),
            request_understanding=understanding_payload,
            capability_discovery=discovery_payload,
            capability_catalog=capability_catalog,
            workflow_selection=workflow_selection,
            memory_section=memory_section,
            workflow_templates=templates,
            planner_section_overrides=planner_sections,
            planner_projection_schema_version=PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
        )

    def resolve_request(
        self,
        request: str,
        session_id: str,
        *,
        pending: Any = None,
        turn_advice: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Resolve clarification/follow-up context without Domain policy."""
        pending = pending or self._conversation_store.get_pending(session_id)
        advice = turn_advice or resolve_turn_mode(
            self._domain_pack,
            request,
            pending_request=pending.request if pending is not None else None,
            pending_error=pending.error if pending is not None else None,
        )
        mode = str(advice.get("mode") or "unknown") if isinstance(advice, Mapping) else "unknown"
        if pending is not None and mode in {"clarification_reply", "follow_up", "decision_reply"}:
            return request.strip() + " " + pending.request.strip()
        if pending is not None:
            self._conversation_store.clear_pending(session_id)
        previous = self._conversation_store.get_last_request(session_id)
        follow_up = ("继续", "刚才", "上面", "这个结果", "该结果", "改成", "调整为", "换成")
        if previous and any(term in request for term in follow_up):
            return request.strip() + "。基于上一轮请求：" + previous.strip()
        return request

    def require_workflow_selection(
        self,
        context_packet: ContextPacket,
        workflow: Optional[Mapping[str, Any]],
    ) -> None:
        return require_workflow_selection(context_packet, workflow)

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        context_packet: ContextPacket,
    ) -> TaskPlan:
        return invoke_planner(self._planner, request, workflow, context_packet)

    def validate_plan_for_execution(
        self,
        plan: TaskPlan,
        workflow: Optional[Mapping[str, Any]],
        *,
        policy_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        open_react = policy_mode == "open_react" and workflow is None
        if workflow is not None:
            validator = getattr(self._domain_pack, "validate_workflow_plan", None)
            if callable(validator):
                validator(plan, workflow)
        # Legacy ``validate_plan`` implementations are template/blueprint
        # gates. They must not turn an automatically inferred workflow into
        # the capability boundary of an open ReAct request. Domain Packs can
        # still expose non-template safety rules through the explicit seam.
        validator_name = (
            "validate_open_react_plan" if open_react else "validate_plan"
        )
        validator = getattr(self._domain_pack, validator_name, None)
        if callable(validator):
            validator(plan)
        if plan.output.get("type") != "direct_answer":
            validate_plan(plan, self._registry.names, self._max_steps)
        policy = self.resolve_execution_policy(
            plan,
            workflow,
            policy_mode=policy_mode,
        )
        return self._execution_policy_resolver.validate_plan(plan, policy)

    def resolve_execution_policy(
        self,
        plan: TaskPlan,
        workflow: Optional[Mapping[str, Any]],
        *,
        requires_confirmation: bool = False,
        policy_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve one policy through the shared Domain-neutral resolver."""

        open_react = policy_mode == "open_react" and workflow is None
        domain_policy = (
            {}
            if open_react
            else resolve_plan_policy(
                self._domain_pack,
                plan,
                workflow=workflow,
            )
        )
        requested_mode = getattr(self._planner, "execution_policy_mode", None)
        return self._execution_policy_resolver.resolve(
            plan,
            workflow=workflow,
            domain_policy=domain_policy,
            requested_mode=requested_mode,
            requires_confirmation=requires_confirmation,
            open_react=open_react,
        )

    def validate_plan(self, plan: TaskPlan) -> None:
        """Keep the historical generic validation seam available."""
        return validate_plan(plan, self._registry.names, self._max_steps)

    def validate_or_repair(
        self,
        plan: TaskPlan,
        request: str,
        workflow: Optional[Mapping[str, Any]],
        *,
        deadline: Optional[float],
        run_id: Optional[str],
        context_packet: Optional[ContextPacket],
    ) -> tuple[TaskPlan, Optional[Dict[str, Any]]]:
        """Validate a candidate and perform at most one bounded repair."""
        try:
            self.validate_plan_for_execution(plan, workflow)
            return plan, None
        except Exception as exc:
            capability_context = self._repair_context(context_packet)
            outcome = self._plan_repair_engine.repair(
                PlanRepairInput(
                    request=request,
                    candidate=plan,
                    workflow=workflow,
                    validation_error=str(exc),
                    run_id=run_id,
                    deadline=deadline,
                    capability_context=capability_context,
                )
            )
            if outcome.plan is None or outcome.event is None:
                raise
            return outcome.plan, outcome.event

    def try_replan(
        self,
        *,
        original: TaskPlan,
        existing_steps: List[StepRun],
        request: str,
        workflow: Optional[Mapping[str, Any]],
        step: PlanStep,
        step_run: StepRun,
        completed: Set[str],
        completed_results: Dict[str, Dict[str, Any]],
        replan_count: int,
        deadline: Optional[float],
    ) -> Optional[ReplanOutcome]:
        """Build, validate and merge one bounded execution replan."""
        if not self._replan_policy.should_replan(
            replan_count=replan_count,
            step_status=step_run.status,
            step_error=str(step_run.error or ""),
        ):
            return None
        completed_steps = [
            {"id": step_id, "tool": self._tool_for_step(original, step_id)}
            for step_id in completed
        ]
        failed_payload = {
            "id": step.id,
            "tool": step.tool,
            "args": dict(step.args),
            "error_category": step_run.error_category or failure_category(str(step_run.error or "")),
        }
        quality_before = diagnose_plan(original, workflow_context(self._domain_pack))
        feedback = self._replan_policy.feedback_payload(
            request=request,
            completed_steps=completed_steps,
            failed_step=failed_payload,
            remaining_tools=self._registry.names,
            output_type=(original.output or {}).get("type"),
            plan_quality=quality_before,
        )
        started = perf_counter()
        try:
            if getattr(self._planner, "capability_rules", None) is not None:
                replacement = rule_replan_plan(failed_payload, completed_results)
            else:
                replacement = self._planner.plan(request, context=replan_context(feedback))
            merged = merge_replanned_plan(original, replacement, failed_step_id=step.id)
            self.validate_plan_for_execution(merged, workflow)
            quality_after = diagnose_plan(merged, workflow_context(self._domain_pack))
            if quality_after.get("available") and not quality_after.get("passed"):
                raise ToolError("replanned workflow blueprint mismatch")
            old_by_id = {item.id: item for item in existing_steps}
            rebuilt: List[StepRun] = []
            new_step_ids: List[str] = []
            for item in merged.steps:
                previous = old_by_id.get(item.id)
                if previous is not None:
                    rebuilt.append(previous)
                else:
                    rebuilt.append(StepRun(item.id, item.tool, item.args, list(item.depends_on)))
                    new_step_ids.append(item.id)
            event = build_replan_event(
                failed_step_id=step.id,
                failed_tool=step.tool,
                failure_category=step_run.error_category or failure_category(str(step_run.error or "")),
                new_step_ids=new_step_ids,
                latency_ms=(perf_counter() - started) * 1000,
                plan_quality_before=quality_before,
                plan_quality_after=quality_after,
            )
            return ReplanOutcome(
                plan=merged,
                steps=rebuilt,
                new_step_ids=new_step_ids,
                event=event,
                quality_before=quality_before,
                quality_after=quality_after,
            )
        except Exception:
            return None

    @staticmethod
    def _repair_context(context_packet: Optional[ContextPacket]) -> Dict[str, Any]:
        if context_packet is None:
            return {}
        source_payload = context_packet.source_payload or context_packet.payload
        sections = source_payload.get("sections", {})
        if not isinstance(sections, Mapping):
            return {}
        return {
            key: sections[key]
            for key in (
                "available_tools",
                "capability_discovery",
                "capability_catalog",
                "workflow_templates",
            )
            if key in sections
        }

    @staticmethod
    def _tool_for_step(plan: TaskPlan, step_id: str) -> Optional[str]:
        for item in plan.steps:
            if item.id == step_id:
                return item.tool
        return None
