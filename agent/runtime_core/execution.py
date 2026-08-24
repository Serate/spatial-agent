"""Tool execution seam for the domain-neutral Runtime.

The module owns retry and step-state mechanics.  Authorization/preflight,
cooperative control, and observability remain injected hooks so the execution
mechanism cannot acquire Domain or transport policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Dict, Set

from agent.errors import RunTimedOut, ToolError
from agent.models import PlanStep, StepRun
from agent.replanning import failure_category

from .projection import resolve_result_references


@dataclass(frozen=True)
class StepExecutionHooks:
    registry: Any
    max_retries: int
    preflight: Callable[[str, Dict[str, Any], Dict[str, Dict[str, Any]]], None]
    control_check: Callable[[str, Any], None]
    emit_step: Callable[[str, StepRun], None]
    now: Callable[[], str]


def execute_step(
    hooks: StepExecutionHooks,
    run_id: str,
    deadline: Any,
    step_run: StepRun,
    step: PlanStep,
    completed: Set[str],
    completed_results: Dict[str, Dict[str, Any]],
) -> None:
    """Dispatch one validated step with bounded retries and lifecycle events."""
    missing = [dependency for dependency in step.depends_on if dependency not in completed]
    if missing:
        raise ToolError("Step dependencies are not complete: " + ", ".join(missing))
    resolved_args = resolve_result_references(step.args, completed_results)
    step_run.governance = hooks.registry.governance_for(step.tool)
    try:
        hooks.preflight(step.tool, resolved_args, completed_results)
    except ToolError as exc:
        step_run.status = "FAILED"
        step_run.error = str(exc)
        step_run.error_category = getattr(exc, "category", None) or "tool_gate"
        step_run.error_code = getattr(exc, "code", None)
        step_run.retryable = getattr(exc, "retryable", None)
        step_run.finished_at = hooks.now()
        hooks.emit_step(run_id, step_run)
        raise
    hooks.control_check(run_id, deadline)
    step_run.args = resolved_args
    step_run.status = "RUNNING"
    step_run.started_at = hooks.now()
    started = perf_counter()
    for attempt in range(1, hooks.max_retries + 2):
        hooks.control_check(run_id, deadline)
        step_run.attempts = attempt
        try:
            tool_timeout = hooks.registry.timeout_seconds(step.tool)
            if deadline is not None:
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    raise RunTimedOut("run exceeded timeout_seconds")
                if tool_timeout is not None:
                    tool_timeout = min(float(tool_timeout), remaining)
            step_run.result = hooks.registry.invoke(
                step.tool,
                resolved_args,
                timeout_seconds=tool_timeout,
            )
            step_run.status = "COMPLETED"
            step_run.finished_at = hooks.now()
            step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
            hooks.emit_step(run_id, step_run)
            return
        except ToolError as exc:
            step_run.error = str(exc)
            step_run.error_category = getattr(exc, "category", None) or failure_category(str(exc))
            step_run.error_code = getattr(exc, "code", None)
            step_run.retryable = getattr(exc, "retryable", None)
            if exc.retryable is False or attempt > hooks.max_retries:
                step_run.status = "FAILED"
                step_run.finished_at = hooks.now()
                step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
                hooks.emit_step(run_id, step_run)
                raise
    step_run.status = "FAILED"
    step_run.finished_at = hooks.now()
    step_run.latency_ms = round((perf_counter() - started) * 1000, 3)
    hooks.emit_step(run_id, step_run)


def block_remaining_steps(
    steps: list[StepRun],
    start_index: int,
    failed_step_id: str,
    reason: str,
) -> None:
    """Mark not-yet-started steps as blocked after a terminal failure."""
    for step in steps[start_index:]:
        if step.status == "PENDING":
            step.status = "BLOCKED"
            step.error = "blocked by failed step {}: {}".format(
                failed_step_id,
                reason,
            )
