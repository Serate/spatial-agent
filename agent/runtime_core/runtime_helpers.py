"""Bounded runtime helper functions for AgentRuntime.

Split out of ``runtime_engine`` so these small, pure helper functions live
behind a stable seam and the engine class stays focused on orchestration.
Re-exported by ``runtime_engine`` for compatibility.
"""

import uuid
import inspect
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

from agent.errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from agent.agent_settings import open_agent_defaults
from agent.capability_catalog import (
    CAPABILITY_CONTEXT_SCHEMA_VERSION,
    capability_context_summary,
)
from agent.capability_routing import CAPABILITY_DISCOVERY_SCHEMA_VERSION
from agent.capability_discovery import enrich_discovery_context
from agent.context_engineering import ContextBuilder, ContextPacket
from agent.conversation_turn import build_conversation_turn, resolve_turn_mode
from agent.domain_contract import (
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
from agent.decision_lifecycle import DecisionLifecycleError, DecisionRequest, DecisionStore
from agent.action_lifecycle import project_action_lifecycle
from agent.evidence.contract import project_capability_catalog_evidence
from agent.failure_contract import build_failure_evidence
from agent.error_taxonomy import classify_exception
from agent.answer_generation import fallback_answer_generation_evidence
from agent.answer_quality import assess_answer
from agent.result_completeness import build_result_completeness
from agent.memory import FactMemory
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.plan_repair import PlanRepairEngine, PlanRepairInput
from agent.observability import ObservabilityEmitter
from agent.run_events import new_run_event
from agent.plan_identity import build_plan_identity
from agent.evidence.revalidation import (
    build_evidence_binding,
    build_evidence_revalidation_gate,
)
from agent.plan_quality import diagnose_plan, project_plan_quality_evidence
from agent.plan_policy import build_plan_policy_evidence
from agent.planner_selection import build_planner_selection_evidence
from agent.capability_selection import build_capability_selection_evidence
from agent.planner_context import (
    PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION,
    project_planner_sections,
)
from agent.workflow_selection import (
    build_workflow_selection_evidence,
    normalize_workflow_selection_evidence,
)
from agent.planner import Planner
from agent.replanning import (
    ReplanningPolicy,
    build_replan_event,
    failure_category,
    merge_replanned_plan,
    rule_replan_plan,
)
from agent.request_model import RequestFacts
from agent.runtime_context import build_runtime_context
from agent.tools import ToolRegistry
from agent.runtime_core import projection as _runtime_projection
from agent.runtime_core.projection import (
    append_execution_degradation_notice as _append_execution_degradation_notice,
)
from agent.runtime_core import planning as _runtime_planning
from agent.runtime_core import execution as _runtime_execution
from agent.runtime_core.execution_policy import ExecutionPolicyResolver, build_execution_policy
from agent.runtime_core.capabilities import RuntimeCapabilitySurface
from agent.runtime_core.control import RunControl
from agent.runtime_core.decision_resume import RuntimeDecisionResume
from agent.runtime_core.tool_approval_resume import RuntimeToolApprovalResume
from agent.runtime_core.planning_surface import RuntimePlanningSurface
from agent.runtime_core.preview import RuntimePreviewSurface
from agent.runtime_core.plan_evidence import (
    build_plan_evidence as _build_plan_evidence_canonical,
    planner_source as _planner_source,
    safe_small_mapping as _safe_small_mapping,
)
from agent.runtime_core.recovery import RuntimeRecoverySurface
from agent.runtime_core.run_lifecycle import RuntimeRunLifecycle
from agent.runtime_state import (
    InMemoryConversationStore,
    InMemoryStateStore,
    PendingClarification,
)
from agent.tooling import InMemoryToolApprovalStore, rehydrate_approved_tools



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
    classification = classify_exception(
        exc,
        phase=phase,
        status=result.status.value,
        source="runtime",
    )
    category = (
        getattr(exc, "category", None)
        or (failed_step.error_category if failed_step else None)
        or classification["category"]
        or _run_error_category(result)
    )
    code = (
        getattr(exc, "code", None)
        or (failed_step.error_code if failed_step else None)
        or classification["code"]
    )
    retryable = getattr(exc, "retryable", None)
    if retryable is None and failed_step is not None:
        retryable = failed_step.retryable
    if retryable is None:
        retryable = classification["retryable"]
    result.error_category = str(category)[:64] if category else None
    result.error_code = str(code)[:96] if code else None
    result.failure = build_failure_evidence(
        status=result.status.value,
        category=result.error_category,
        code=result.error_code,
        phase=phase or classification["phase"],
        retryable=retryable,
    )
    # Keep the legacy top-level fields aligned with the canonical evidence.
    result.error_category = result.failure["category"]
    result.error_code = result.failure["code"]


def _run_error_category(result: AgentRunResult) -> Optional[str]:
    return _runtime_projection.run_error_category(result)


def _invoke_answer_generator(
    method: Callable[..., Any],
    result: AgentRunResult,
    *,
    on_delta: Any = None,
    budget: Any = None,
    progress: Any = None,
    on_progress: Any = None,
) -> Any:
    """Keep legacy answer generators compatible with runtime controls."""

    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD
        for item in parameters.values()
    )
    kwargs: dict[str, Any] = {}
    for name, value in (
        ("on_delta", on_delta),
        ("budget", budget),
        ("progress", progress),
        ("on_progress", on_progress),
    ):
        if value is not None and (accepts_kwargs or name in parameters):
            kwargs[name] = value
    return method(result, **kwargs)


def _public_tool_result(tool: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Strip private adapter handoffs before any generic Result boundary."""

    del tool
    if not isinstance(value, Mapping):
        return {}
    return {key: item for key, item in value.items() if str(key) != "_model_context"}
