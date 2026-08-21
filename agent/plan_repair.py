"""Capability-guided planning repair behind one small Runtime seam.

The Runtime owns when a candidate plan is invalid and how the final result is
persisted.  This module owns the bounded repair attempt itself: policy,
capability feedback, planner invocation, strict re-validation and lineage.
Keeping those rules here prevents each entry point or planner adapter from
inventing a different repair protocol.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Optional, Protocol

from .models import TaskPlan
from .replanning import ReplanningPolicy, build_replan_event, failure_category


class PlanRepairPlanner(Protocol):
    """The minimal Planner interface required by the repair seam."""

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        ...


@dataclass(frozen=True)
class PlanRepairInput:
    """Bounded input supplied by Runtime for one planning repair attempt."""

    request: str
    candidate: TaskPlan
    workflow: Optional[Mapping[str, Any]]
    validation_error: str
    run_id: Optional[str] = None
    deadline: Optional[float] = None
    capability_context: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class PlanRepairOutcome:
    """A repair result that never exposes raw provider or exception content."""

    plan: Optional[TaskPlan]
    event: Optional[dict[str, Any]]
    status: str
    reason_code: str

    @property
    def repaired(self) -> bool:
        return self.plan is not None and self.event is not None and self.status == "repaired"


class PlanRepairEngine:
    """Deep module for one capability-guided, budgeted planning repair."""

    def __init__(
        self,
        planner: PlanRepairPlanner,
        policy: ReplanningPolicy,
        *,
        available_tools: Callable[[], list[str]],
        validate_plan: Callable[[TaskPlan, Optional[Mapping[str, Any]]], None],
        control_check: Callable[[str, Optional[float]], None],
    ) -> None:
        self._planner = planner
        self._policy = policy
        self._available_tools = available_tools
        self._validate_plan = validate_plan
        self._control_check = control_check

    def repair(self, request: PlanRepairInput) -> PlanRepairOutcome:
        """Attempt one repair and return a stable outcome, never raw errors."""

        if getattr(self._planner, "capability_rules", None) is not None:
            return PlanRepairOutcome(None, None, "not_applicable", "rule_planner")
        if not self._policy.should_repair(
            repair_count=0,
            validation_error=request.validation_error,
        ):
            return PlanRepairOutcome(None, None, "rejected", "repair_budget_exhausted")

        self._control_check(request.run_id or "plan-repair", request.deadline)
        failed_step = {
            "id": "plan-validation",
            "tool": "planner",
            "args": {},
            "error_category": failure_category(request.validation_error),
        }
        feedback = self._policy.feedback_payload(
            request=request.request,
            completed_steps=[],
            failed_step=failed_step,
            remaining_tools=list(self._available_tools())[:128],
            output_type=(request.candidate.output or {}).get("type"),
            validation_error=request.validation_error,
        )
        started = perf_counter()
        try:
            replacement = self._call_planner(request, feedback)
            self._validate_plan(replacement, request.workflow)
        except Exception:
            return PlanRepairOutcome(None, None, "failed", "replacement_invalid")

        event = build_replan_event(
            failed_step_id="plan-validation",
            failed_tool="planner",
            failure_category=failure_category(request.validation_error),
            new_step_ids=[step.id for step in replacement.steps][:24],
            latency_ms=(perf_counter() - started) * 1000,
            phase="planning",
        )
        return PlanRepairOutcome(replacement, event, "repaired", "ok")

    def _call_planner(
        self,
        request: PlanRepairInput,
        feedback: Mapping[str, Any],
    ) -> TaskPlan:
        method = self._planner.plan
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            item.kind == inspect.Parameter.VAR_KEYWORD
            for item in parameters.values()
        )
        kwargs: dict[str, Any] = {}
        if request.workflow is not None and (
            "workflow" in parameters or accepts_kwargs
        ):
            kwargs["workflow"] = request.workflow
        if "context" in parameters or accepts_kwargs:
            context = {
                "stage": "replan",
                "feedback": dict(feedback),
                "capability_context": _bounded_capability_context(
                    request.capability_context
                ),
            }
            kwargs["context"] = context
        return method(request.request, **kwargs)


def _bounded_capability_context(value: Any) -> dict[str, Any]:
    """Keep only planner-useful capability sections and bounded values."""

    source = value if isinstance(value, Mapping) else {}
    result: dict[str, Any] = {}
    allowed = (
        "available_tools",
        "capability_discovery",
        "capability_catalog",
        "workflow_templates",
    )
    for key in allowed:
        item = source.get(key)
        if item is None:
            continue
        result[key] = _bound_json(item)
    return result


def _bound_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _bound_json(item, depth=depth + 1)
            for key, item in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple)):
        return [_bound_json(item, depth=depth + 1) for item in list(value)[:64]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:320]
    return str(value)[:320]


__all__ = [
    "PlanRepairEngine",
    "PlanRepairInput",
    "PlanRepairOutcome",
]
