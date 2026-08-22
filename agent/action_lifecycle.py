"""Domain-neutral projection for the externally visible run lifecycle.

``DecisionLifecycle`` owns durable user decisions.  This module owns the
read-only projection that explains what a caller can do with a run or Domain
Action at the current boundary.  It deliberately has no I/O, planner, domain,
or transport dependency: result, artifact, async, and Console adapters all
consume the same bounded projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .recovery_action import normalize_action_ids, project_available_actions
from .action_precondition import is_action_allowed


ACTION_LIFECYCLE_SCHEMA_VERSION = "spatial-agent.action-lifecycle.v1"

LIFECYCLE_STATES = frozenset(
    {
        "planning",
        "executing",
        "awaiting_confirmation",
        "clarification_required",
        "repairable",
        "recoverable",
        "completed",
        "rejected",
        "cancelled",
        "failed",
    }
)

LIFECYCLE_ACTIONS = frozenset(
    {"approve", "reject", "clarify", "repair", "retry", "recover", "cancel"}
)

_MAX_ACTIONS = 8
_MAX_REASON = 96
_MAX_ID = 160


def project_action_lifecycle(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a stable, bounded action lifecycle projection.

    The input may be a run payload, an action payload, or a result envelope.
    Top-level run status wins over nested status because it is the authoritative
    persistence boundary.  Unknown/missing status is represented as ``failed``
    with an explicit reason instead of being mistaken for success.
    """

    value = payload if isinstance(payload, Mapping) else {}
    result = value.get("result") if isinstance(value.get("result"), Mapping) else {}
    status = _status(value, result)
    decision = _mapping(value.get("decision_evidence")) or _mapping(
        value.get("decision")
    ) or _mapping(result.get("decision"))
    clarification = _mapping(value.get("clarification")) or _mapping(
        result.get("clarification")
    )
    failure = _mapping(value.get("failure")) or _mapping(result.get("failure"))
    async_observation = _mapping(value.get("async_observability"))

    retry_count = _bounded_count(value.get("retry_count"), 0)
    recovery_count = _bounded_count(
        value.get("recovery_count"),
        _bounded_count(async_observation.get("recovery_count"), 0),
    )
    replan_events = _events(value, result)
    repair_count = len(replan_events)
    retryable = _retryable(value, result, failure)

    state, phase, actions, reason = _state_for(
        status=status,
        decision=decision,
        clarification=clarification,
        failure=failure,
        retryable=retryable,
        explicit_repairable=value.get("repairable"),
    )
    blocked_actions = [
        action for action in actions
        if not is_action_allowed(value, action)
    ]
    if blocked_actions:
        actions = tuple(
            action for action in actions if action not in blocked_actions
        )
        reason = "action_preconditions_blocked"
    subject_id = value.get("run_id") or value.get("action_execution_id")
    result_value = {
        "schema_version": ACTION_LIFECYCLE_SCHEMA_VERSION,
        "state": state,
        "phase": phase,
        "status": status or "UNKNOWN",
        "allowed_actions": list(actions[:_MAX_ACTIONS]),
        "actions": project_available_actions(actions, subject_id=subject_id),
        "reason_code": reason[:_MAX_REASON],
        "attempt": min(10000, retry_count + 1),
        "lineage": {
            "retry_count": retry_count,
            "repair_count": min(1000, repair_count),
            "recovery_count": recovery_count,
            "decision": _decision_state(decision),
            "recovered": recovery_count > 0,
        },
    }
    if subject_id:
        result_value["subject_id"] = str(subject_id)[:_MAX_ID]
    if blocked_actions:
        result_value["blocked_actions"] = list(blocked_actions[:_MAX_ACTIONS])
    if decision.get("decision_id"):
        result_value["decision_id"] = str(decision["decision_id"])[:_MAX_ID]
    return result_value


def _state_for(
    *,
    status: str,
    decision: Mapping[str, Any],
    clarification: Mapping[str, Any],
    failure: Mapping[str, Any],
    retryable: bool,
    explicit_repairable: Any,
) -> tuple[str, str, tuple[str, ...], str]:
    if status == "WAITING_FOR_DECISION":
        return "awaiting_confirmation", "planning", _decision_actions(decision), "awaiting_confirmation"
    if status == "NEEDS_CLARIFICATION":
        return "clarification_required", "planning", ("clarify", "cancel"), "clarification_required"
    if status in {"CREATED", "PLANNING", "QUEUED"}:
        return "planning", "planning", ("cancel",), "planning_in_progress"
    if status in {"EXECUTING", "RUNNING", "CANCEL_REQUESTED"}:
        return "executing", "execution", ("cancel",), "execution_in_progress"
    if status == "COMPLETED":
        return "completed", "execution", (), "completed"
    if status == "REJECTED":
        return "rejected", "control", (), "rejected"
    if status == "CANCELLED":
        return "cancelled", "control", (), "cancelled"
    if status in {"FAILED", "TIMED_OUT"}:
        if _truthy(explicit_repairable) or failure.get("category") == "planning_repairable":
            return "repairable", "planning", ("repair", "reject", "cancel"), "plan_repair_available"
        if retryable or status == "TIMED_OUT":
            return "recoverable", "execution", ("retry", "recover", "cancel"), "recovery_available"
        return "failed", "execution", (), _failure_reason(failure)
    return "failed", "planning", (), "run_status_unknown"


def _decision_actions(decision: Mapping[str, Any]) -> tuple[str, ...]:
    raw = decision.get("allowed_actions")
    actions = _safe_actions(raw)
    if actions:
        return actions
    return ("approve", "reject", "cancel")


def _retryable(
    payload: Mapping[str, Any], result: Mapping[str, Any], failure: Mapping[str, Any]
) -> bool:
    if "retryable" in failure:
        return failure.get("retryable") is True
    if payload.get("retryable") is True or result.get("retryable") is True:
        return True
    steps = payload.get("steps")
    if not isinstance(steps, list):
        steps = result.get("steps")
    return any(
        isinstance(step, Mapping) and step.get("retryable") is True
        for step in (steps if isinstance(steps, list) else [])
    )


def _failure_reason(failure: Mapping[str, Any]) -> str:
    category = str(failure.get("category") or "execution")[:48]
    return "failed_" + _token(category)


def _status(value: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    raw = value.get("status") or result.get("status")
    return str(raw or "").strip().upper()[:32]


def _events(value: Mapping[str, Any], result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = value.get("replan_events")
    if not isinstance(raw, list):
        replanning = _mapping(value.get("replanning")) or _mapping(result.get("replanning"))
        raw = replanning.get("events") if isinstance(replanning.get("events"), list) else []
    return [item for item in raw[:1000] if isinstance(item, Mapping)]


def _decision_state(decision: Mapping[str, Any]) -> str | None:
    state = decision.get("state")
    return str(state)[:64] if state else None


def _safe_actions(raw: Any) -> tuple[str, ...]:
    return tuple(normalize_action_ids(raw, allowed=LIFECYCLE_ACTIONS))


def _token(value: Any) -> str:
    return str(value or "").strip().lower()[:_MAX_REASON]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bounded_count(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(0, min(10000, number))


def _truthy(value: Any) -> bool:
    return value is True


__all__ = [
    "ACTION_LIFECYCLE_SCHEMA_VERSION",
    "LIFECYCLE_ACTIONS",
    "LIFECYCLE_STATES",
    "project_action_lifecycle",
]
