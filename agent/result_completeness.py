"""Domain-neutral completion projection for run results.

The lifecycle status answers whether a Run is terminal.  This contract adds
the more useful user-facing distinction between a complete result, a useful
partial result, a blocked result and a result waiting for a decision.  It is a
bounded projection only: it never copies raw errors, tool arguments or model
responses.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RESULT_COMPLETENESS_SCHEMA_VERSION = "spatial-agent.result-completeness.v1"
RESULT_COMPLETENESS_STATES = frozenset(
    {"complete", "partial", "blocked", "waiting_decision", "pending"}
)
_MAX_TEXT = 96


def build_result_completeness(
    payload: Mapping[str, Any] | None = None,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    """Build a safe completion summary from a Run or Result payload."""

    value = payload if isinstance(payload, Mapping) else {}
    existing = value.get("completeness")
    if (
        isinstance(existing, Mapping)
        and existing.get("schema_version") == RESULT_COMPLETENESS_SCHEMA_VERSION
    ):
        return normalize_result_completeness(existing)
    lifecycle_status = _text(status or value.get("status"), 32).upper()
    react = value.get("react_evidence")
    react = react if isinstance(react, Mapping) else {}
    composite = value.get("composite") or value.get("_composite")
    composite = composite if isinstance(composite, Mapping) else {}
    composite_state = _text(composite.get("state"), 32).lower()
    react_state = _text(react.get("state"), 32)
    failure = value.get("failure")
    failure = failure if isinstance(failure, Mapping) else {}
    steps = value.get("steps")
    steps = steps if isinstance(steps, (list, tuple)) else []
    plan = value.get("plan")
    plan = plan if isinstance(plan, Mapping) else {}
    planned_steps = plan.get("steps")
    planned_steps = planned_steps if isinstance(planned_steps, (list, tuple)) else []
    react_turns = react.get("turns")
    react_turns = react_turns if isinstance(react_turns, (list, tuple)) else []

    completed_steps = 0
    failed_steps = 0
    blocked_steps = 0
    for step in steps[:128]:
        if not isinstance(step, Mapping):
            continue
        step_status = _text(step.get("status"), 32).upper()
        if step_status in {"COMPLETED", "SUCCESS"}:
            completed_steps += 1
        elif step_status in {"FAILED", "ERROR"}:
            failed_steps += 1
        elif step_status == "BLOCKED":
            blocked_steps += 1

    blocked_turns = 0
    for turn in react_turns[:128]:
        if not isinstance(turn, Mapping):
            continue
        if _text(turn.get("validation_state"), 32).upper() == "BLOCKED":
            blocked_turns += 1

    reason_code = _text(
        react.get("reason_code")
        or composite.get("reason_code")
        or (
            composite.get("evidence", {}).get("reason_code")
            if isinstance(composite.get("evidence"), Mapping)
            else None
        )
        or failure.get("code")
        or value.get("error_code")
        or value.get("reason_code"),
        _MAX_TEXT,
    ) or None
    if composite_state == "partial" or react_state == "partial":
        state = "partial"
    elif composite_state in {"blocked", "failed"} or react_state in {
        "blocked",
        "clarification",
        "rejected",
    }:
        state = "blocked"
    elif composite_state == "pending":
        state = "pending"
    elif react_state == "awaiting_approval" or lifecycle_status == "WAITING_FOR_DECISION":
        state = "waiting_decision"
    elif lifecycle_status in {"PLANNING", "EXECUTING", "CREATED"}:
        state = "pending"
    elif lifecycle_status == "COMPLETED":
        state = (
            "partial"
            if failed_steps or blocked_steps
            else "blocked"
            if failure or value.get("error") or value.get("error_code")
            else "complete"
        )
    else:
        state = "blocked"

    if state == "complete":
        reason_code = None
    elif not reason_code:
        reason_code = {
            "partial": "incomplete_actions",
            "blocked": "run_blocked",
            "waiting_decision": "decision_required",
            "pending": "run_in_progress",
        }.get(state, "result_unavailable")

    attempted_actions = _bounded_int(react.get("action_count"), 0, 128)
    if attempted_actions is None:
        attempted_actions = min(len(steps), 128)
    completed_actions = min(completed_steps, 128)
    blocked_actions = min(max(blocked_steps + failed_steps, blocked_turns), 128)
    if state in {"partial", "blocked"} and blocked_actions == 0:
        blocked_actions = 1
    planned_action_count = len(planned_steps) or len(steps)
    if state in {"partial", "blocked"}:
        planned_action_count = max(planned_action_count, completed_actions + blocked_actions)

    retryable = failure.get("retryable")
    if not isinstance(retryable, bool):
        retryable = state == "partial"
    uncertainty = {
        "complete": None,
        "partial": "未执行动作的结果未知，当前结论只覆盖已完成证据。",
        "blocked": "未形成可执行的完整结果。",
        "waiting_decision": "需要用户确认后才能继续。",
        "pending": "分析仍在进行中。",
    }[state]
    return {
        "schema_version": RESULT_COMPLETENESS_SCHEMA_VERSION,
        "state": state,
        "planned_action_count": min(planned_action_count, 128),
        "attempted_action_count": attempted_actions,
        "completed_action_count": completed_actions,
        "blocked_action_count": blocked_actions,
        "stop_reason": reason_code,
        "retryable": bool(retryable),
        "uncertainty": uncertainty,
    }


def normalize_result_completeness(value: Any) -> dict[str, Any]:
    """Normalize a persisted completion projection without widening it."""

    if not isinstance(value, Mapping):
        return build_result_completeness({}, status="UNKNOWN")
    state = _text(value.get("state"), 32)
    if state not in RESULT_COMPLETENESS_STATES:
        return build_result_completeness({}, status="UNKNOWN")
    return {
        "schema_version": RESULT_COMPLETENESS_SCHEMA_VERSION,
        "state": state,
        "planned_action_count": _bounded_int(value.get("planned_action_count"), 0, 128) or 0,
        "attempted_action_count": _bounded_int(value.get("attempted_action_count"), 0, 128) or 0,
        "completed_action_count": _bounded_int(value.get("completed_action_count"), 0, 128) or 0,
        "blocked_action_count": _bounded_int(value.get("blocked_action_count"), 0, 128) or 0,
        "stop_reason": _text(value.get("stop_reason"), _MAX_TEXT) or None,
        "retryable": bool(value.get("retryable")),
        "uncertainty": _text(value.get("uncertainty"), 240) or None,
    }


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


__all__ = [
    "RESULT_COMPLETENESS_SCHEMA_VERSION",
    "RESULT_COMPLETENESS_STATES",
    "build_result_completeness",
    "normalize_result_completeness",
]
