"""Private context holder and bounded recovery choices for run lifecycle.

Split out of ``run_lifecycle`` so the data holder and pure recovery mapping live
behind a small, stable seam.  Re-exported by ``run_lifecycle`` for compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Set

from ..models import AgentRunResult, RunStatus, TaskPlan
from ..errors import ClarificationNeeded, RequestRejected, RunCancelled, RunTimedOut, ToolError
from .run_budget import RunBudget
from .progress import ProgressCoordinator



@dataclass
class _LifecycleContext:
    """Private state shared by the stages of one synchronous run.

    This is intentionally not part of the persisted/public contract.  It
    prevents each stage from receiving a growing list of loosely related
    arguments while keeping state ownership with the Runtime adapter.
    """

    request: str
    session_id: str
    timeout_seconds: Optional[float]
    run_id: Optional[str]
    workflow: Optional[Mapping[str, Any]]
    validated_plan: Optional[TaskPlan]
    expected_plan_fingerprint: Optional[str]
    expected_evidence_fingerprint: Optional[str]
    require_confirmation: bool
    decision_evidence: Optional[Dict[str, Any]]
    decision_id: Optional[str]
    decision_version: Optional[int]
    decision_input: Optional[Mapping[str, Any]]
    decision_ttl_seconds: Optional[float]
    resolved_request_override: Optional[str]
    deadline: Optional[float] = None
    pending: Any = None
    turn_advice: Mapping[str, Any] = field(default_factory=dict)
    resolved_request: str = ""
    request_facts: Any = None
    resolved_run_id: str = ""
    result: Optional[AgentRunResult] = None
    context_packet: Any = None
    candidate_plan: Optional[TaskPlan] = None
    repair_event: Optional[Dict[str, Any]] = None
    decision_result: Optional[AgentRunResult] = None
    completed: Set[str] = field(default_factory=set)
    completed_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    replan_count: int = 0
    budget: Optional[RunBudget] = None
    progress: Optional[ProgressCoordinator] = None


def _recovery_actions(result: AgentRunResult) -> tuple[str, ...]:
    """Return bounded recovery choices for lifecycle event consumers."""

    status = result.status
    failure = result.failure if isinstance(result.failure, Mapping) else {}
    if status == RunStatus.NEEDS_CLARIFICATION:
        return ("clarify", "cancel")
    if status == RunStatus.TIMED_OUT:
        return ("retry", "recover", "cancel")
    if status == RunStatus.FAILED and failure.get("retryable") is True:
        return ("retry", "recover", "cancel")
    return ()


def _start_phase(
    context: _LifecycleContext,
    phase: str,
    *,
    status: str,
    message: str,
) -> None:
    """Start budget/heartbeat tracking without duplicating lifecycle events."""

    budget = context.budget
    if budget is not None and budget.state() == "exhausted":
        return
    progress = context.progress
    if progress is not None:
        progress.start_phase(
            phase,
            status=status,
            message=message,
            emit_event=False,
        )
    elif budget is not None:
        budget.start_phase(phase)

def _event_phase(context: _LifecycleContext) -> str:
    phase = str(
        context.budget.phase if context.budget is not None else ""
    ).strip().lower()
    return phase if phase in {"resolve", "clarify", "plan", "validate", "execute", "answer", "evidence"} else (
        "execute" if context.candidate_plan is not None else "plan"
    )

def _result(context: _LifecycleContext) -> AgentRunResult:
    if context.result is None:
        raise RuntimeError("lifecycle result has not been initialized")
    return context.result

def _annotate_control_error(
    context: _LifecycleContext, exc: Exception
) -> None:
    """Add stable phase metadata when the cooperative control raised first."""

    if isinstance(exc, RunCancelled):
        if not getattr(exc, "code", None):
            exc.code = "run_cancelled"
        return
    if not isinstance(exc, RunTimedOut):
        return
    phase = str(
        getattr(exc, "phase", None)
        or (context.budget.phase if context.budget is not None else "")
        or "run"
    ).strip().lower()
    if not getattr(exc, "code", None):
        exc.code = {
            "plan": "planner_timeout",
            "validate": "planner_timeout",
            "execute": "execution_timeout",
            "answer": "answer_timeout",
        }.get(phase, "run_timeout")
    exc.phase = phase
    if getattr(exc, "retryable", None) is None:
        exc.retryable = phase in {"plan", "validate", "execute", "answer"}
    if context.budget is not None and not getattr(exc, "budget", None):
        exc.budget = context.budget.receipt()
