"""Domain-neutral planning helpers behind the Runtime planning seam."""

from __future__ import annotations

import inspect
from typing import Any, Mapping, Optional

from agent.context_engineering import ContextPacket
from agent.errors import ClarificationNeeded, ToolError
from agent.models import PlanStep, TaskPlan
from agent.workflow_selection import normalize_workflow_selection_evidence


def invoke_planner(
    planner: Any,
    request: str,
    workflow: Optional[Mapping[str, Any]],
    context_packet: ContextPacket,
    *,
    budget: Any = None,
    progress: Any = None,
    on_progress: Any = None,
) -> TaskPlan:
    """Call old and context-aware Planner implementations through one seam."""
    method = planner.plan
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )
    accepts_context = "context" in parameters or accepts_kwargs
    kwargs = {}
    if workflow is not None:
        kwargs["workflow"] = workflow
    if accepts_context:
        kwargs["context"] = context_packet.payload
    for name, value in (
        ("budget", budget),
        ("progress", progress),
        ("on_progress", on_progress),
    ):
        if value is not None and (accepts_kwargs or name in parameters):
            kwargs[name] = value
    return method(request, **kwargs)


def validate_plan(
    plan: TaskPlan,
    known_tools: Any,
    max_steps: int,
) -> None:
    """Validate generic executable-plan invariants without Domain policy."""
    if len(plan.steps) == 0:
        raise ClarificationNeeded("planner did not produce executable steps")
    if len(plan.steps) > max_steps:
        raise ToolError("Plan exceeds the maximum step limit.")
    known_tool_names = set(known_tools)
    known = {step.id for step in plan.steps}
    positions = {step.id: index for index, step in enumerate(plan.steps)}
    for index, step in enumerate(plan.steps):
        if step.tool not in known_tool_names:
            raise ToolError("Plan selected an unregistered tool: " + step.tool)
        missing = [dependency for dependency in step.depends_on if dependency not in known]
        if missing:
            raise ToolError("Plan has unknown dependencies: " + ", ".join(missing))
        future = [dependency for dependency in step.depends_on if positions[dependency] >= index]
        if future:
            raise ToolError(
                "Plan dependency must refer to an earlier step: " + ", ".join(future)
            )


def require_workflow_selection(
    context_packet: ContextPacket,
    workflow: Optional[Mapping[str, Any]],
) -> None:
    """Turn an ambiguous Domain selection projection into a Runtime clarification."""
    if isinstance(workflow, Mapping) and workflow.get("template_id"):
        return
    sections = (context_packet.source_payload or context_packet.payload or {}).get(
        "sections", {}
    )
    selection = normalize_workflow_selection_evidence(
        sections.get("workflow_selection") if isinstance(sections, Mapping) else None
    )
    selection_state = selection.get("state")
    if selection_state == "clarification" and selection.get("missing_fields"):
        missing_fields = [
            item
            for item in (selection.get("missing_fields") or [])[:16]
            if isinstance(item, Mapping)
        ]
        raise ClarificationNeeded(
            "当前能力还缺少必要输入事实，请补充后继续。",
            {
                "schema_version": "spatial-agent.clarification.v1",
                "state": "capability_facts_required",
                "missing_fields": missing_fields,
                "next_actions": ["补充必要输入事实", "选择其他能力"],
            },
        )
    if selection_state != "ambiguous":
        return
    candidates = [
        str(item)[:96]
        for item in (selection.get("candidate_ids") or [])
        if str(item).strip()
    ][:16]
    if not candidates:
        raise ClarificationNeeded(
            "当前能力选择存在歧义，请补充任务目标。",
            {
                "schema_version": "spatial-agent.clarification.v1",
                "state": "ambiguous_capability",
                "next_actions": ["补充任务目标或分析对象"],
            },
        )
    raise ClarificationNeeded(
        "检测到多个候选能力，请选择后继续。",
        {
            "schema_version": "spatial-agent.clarification.v1",
            "state": "ambiguous_capability",
            "candidate_capabilities": candidates,
            "next_actions": ["选择一个候选能力", "或补充更明确的任务条件"],
        },
    )
