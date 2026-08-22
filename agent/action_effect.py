"""Domain-neutral effect projection for one lifecycle action."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ACTION_EFFECT_SCHEMA_VERSION = "spatial-agent.action-effect.v1"
_STATES = frozenset({"completed", "failed", "pending", "unknown"})
_IMPACTS = frozenset({"result_attached", "state_changed", "no_change", "none", "unknown"})
_MAX_TEXT = 96
_MAX_ACTIONS = 8


def project_action_effect(
    value: Any,
    *,
    action: str | None = None,
) -> dict[str, Any]:
    """Build one bounded effect projection without reading Domain data."""
    payload = value if isinstance(value, Mapping) else {}
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    receipt = payload.get("action_receipt")
    if not isinstance(receipt, Mapping):
        receipt = result.get("action_receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    action_id = _text(action or receipt.get("action_id") or receipt.get("action"))

    candidates = [
        receipt.get("effect"),
        payload.get("action_effect"),
        result.get("action_effect"),
    ]
    for candidate in candidates:
        if isinstance(candidate, Mapping) and "schema_version" in candidate:
            normalized = normalize_action_effect(candidate)
            if action_id:
                normalized["action_id"] = action_id
            return normalized

    receipt_status = _status(receipt.get("status"))
    status = receipt_status or _status(payload.get("status")) or _status(result.get("status"))
    state = _state(status)
    result_ref = receipt.get("result_ref")
    result_available = bool(
        isinstance(result_ref, Mapping) and result_ref.get("id")
    ) or bool(receipt.get("result_run_id")) or bool(result)
    source_status = _status(
        payload.get("source_status") or payload.get("previous_status")
    )
    target_status = _status(
        payload.get("target_status")
        or payload.get("current_status")
        or result.get("status")
        or payload.get("status")
    )
    if state == "failed":
        impact = "none"
        reason = "action_failed"
    elif state == "pending":
        impact = "unknown"
        reason = "action_in_progress"
    elif result_available:
        impact = "state_changed" if source_status and target_status and source_status != target_status else "result_attached"
        reason = "action_result_attached"
    elif state == "completed":
        impact = "state_changed" if source_status and target_status and source_status != target_status else "no_change"
        reason = "action_completed_without_result"
    else:
        impact = "unknown"
        reason = "action_effect_unknown"

    lifecycle = payload.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        lifecycle = result.get("lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
    next_actions = [
        _text(item)
        for item in lifecycle.get("allowed_actions", [])[:_MAX_ACTIONS]
        if _text(item)
    ] if isinstance(lifecycle.get("allowed_actions"), list) else []
    return {
        "schema_version": ACTION_EFFECT_SCHEMA_VERSION,
        "available": bool(action_id or status),
        "action_id": action_id or None,
        "state": state,
        "impact": impact,
        "receipt_status": receipt_status or None,
        "source_status": source_status or None,
        "target_status": target_status or None,
        "result_available": result_available,
        "next_actions": next_actions,
        "reason_code": reason,
    }


def normalize_action_effect(value: Any) -> dict[str, Any]:
    """Normalize a persisted effect and safely degrade unknown versions."""
    if not isinstance(value, Mapping):
        return _unavailable("action_effect_missing")
    if value.get("schema_version") != ACTION_EFFECT_SCHEMA_VERSION:
        return _unavailable("action_effect_unknown_schema")
    state = _text(value.get("state"))
    if state not in _STATES:
        state = "unknown"
    impact = _text(value.get("impact"))
    if impact not in _IMPACTS:
        impact = "unknown"
    actions = value.get("next_actions")
    actions = [
        _text(item) for item in actions[:_MAX_ACTIONS] if _text(item)
    ] if isinstance(actions, list) else []
    return {
        "schema_version": ACTION_EFFECT_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "action_id": _text(value.get("action_id")) or None,
        "state": state,
        "impact": impact,
        "receipt_status": _text(value.get("receipt_status")) or None,
        "source_status": _text(value.get("source_status")) or None,
        "target_status": _text(value.get("target_status")) or None,
        "result_available": bool(value.get("result_available")),
        "next_actions": actions,
        "reason_code": _text(value.get("reason_code")) or "action_effect_unknown",
    }


def _state(status: str) -> str:
    if status in {"COMPLETED", "CANCELLED", "REJECTED"}:
        return "completed"
    if status in {"FAILED", "TIMED_OUT"}:
        return "failed"
    if status in {"IN_PROGRESS", "QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
        return "pending"
    return "unknown"


def _status(value: Any) -> str:
    return str(value or "").strip().upper()[:32]


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": ACTION_EFFECT_SCHEMA_VERSION,
        "available": False,
        "action_id": None,
        "state": "unknown",
        "impact": "unknown",
        "receipt_status": None,
        "source_status": None,
        "target_status": None,
        "result_available": False,
        "next_actions": [],
        "reason_code": _text(reason_code),
    }


__all__ = [
    "ACTION_EFFECT_SCHEMA_VERSION",
    "normalize_action_effect",
    "project_action_effect",
]
