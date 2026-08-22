"""Bounded revalidation status derived from a transition evidence projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .transition_evidence import (
    TRANSITION_EVIDENCE_SCHEMA_VERSION,
    normalize_transition_evidence,
)


EVIDENCE_REVALIDATION_SCHEMA_VERSION = "spatial-agent.evidence-revalidation.v1"
_FIELDS = ("readiness", "coverage", "alignment", "provenance")
_STATES = frozenset({"current", "changed", "degraded", "blocked", "unavailable"})
_MAX_TEXT = 96


def build_evidence_revalidation(value: Any) -> dict[str, Any]:
    """Summarize whether a source/result evidence transition needs action."""

    transition = normalize_transition_evidence(value)
    if transition is None:
        return _unavailable("transition_evidence_missing")
    source_fields = transition.get("source", {}).get("fields", {})
    result_fields = transition.get("result", {}).get("fields", {})
    field_states = []
    blocked = False
    degraded = False
    changed = bool(transition.get("changes"))
    for field in _FIELDS:
        if field not in source_fields and field not in result_fields:
            continue
        state = _field_state(result_fields.get(field))
        blocked = blocked or state == "blocked"
        degraded = degraded or state == "degraded"
        field_states.append({
            "field": field,
            "state": state,
            "changed": any(
                item.get("field") == field
                for item in (transition.get("changes") or [])
                if isinstance(item, Mapping)
            ),
        })
    if blocked:
        state = "blocked"
        reason_code = "result_evidence_blocked"
        next_actions = ["repair", "preview", "cancel"]
    elif degraded:
        state = "degraded"
        reason_code = "result_evidence_degraded"
        next_actions = ["preview", "repair", "cancel"]
    elif changed:
        state = "changed"
        reason_code = "result_evidence_changed"
        next_actions = ["preview"]
    else:
        state = "current"
        reason_code = "result_evidence_current"
        next_actions = []
    return {
        "schema_version": EVIDENCE_REVALIDATION_SCHEMA_VERSION,
        "transition_schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": True,
        "state": state,
        "reason_code": reason_code,
        "field_count": len(field_states),
        "fields": field_states,
        "next_actions": next_actions,
    }


def normalize_evidence_revalidation(value: Any) -> dict[str, Any] | None:
    """Normalize persisted revalidation without interpreting future schemas."""

    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != EVIDENCE_REVALIDATION_SCHEMA_VERSION:
        return None
    state = str(value.get("state") or "unavailable")
    if state not in _STATES:
        state = "unavailable"
    fields = []
    raw_fields = value.get("fields")
    if isinstance(raw_fields, list):
        for item in raw_fields[: len(_FIELDS)]:
            if not isinstance(item, Mapping):
                continue
            field = str(item.get("field") or "")
            if field not in _FIELDS:
                continue
            field_state = _field_state_name(item.get("state"))
            fields.append({
                "field": field,
                "state": field_state,
                "changed": bool(item.get("changed")),
            })
    actions = [
        str(item)[:_MAX_TEXT]
        for item in (value.get("next_actions") or [])[:8]
        if str(item).strip()
    ]
    return {
        "schema_version": EVIDENCE_REVALIDATION_SCHEMA_VERSION,
        "transition_schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "state": state,
        "reason_code": str(value.get("reason_code") or "evidence_revalidation_unknown")[:_MAX_TEXT],
        "field_count": len(fields),
        "fields": fields,
        "next_actions": actions,
    }


def project_evidence_revalidation(value: Any) -> dict[str, Any]:
    """Project revalidation from a result/receipt-shaped payload."""

    payload = value if isinstance(value, Mapping) else {}
    receipt = payload.get("action_receipt")
    if not isinstance(receipt, Mapping):
        result = payload.get("result")
        receipt = result.get("action_receipt") if isinstance(result, Mapping) else None
    if isinstance(receipt, Mapping):
        normalized = normalize_evidence_revalidation(
            receipt.get("evidence_revalidation")
        )
        if normalized is not None:
            return normalized
        return build_evidence_revalidation(receipt.get("transition_evidence"))
    return _unavailable("action_receipt_missing")


def _field_state(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "unavailable"
    states = {_state_from_observation(item) for item in value}
    for state in ("blocked", "degraded", "current"):
        if state in states:
            return state
    return "unavailable" if states == {"unavailable"} else "current"


def _state_from_observation(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "unavailable"
    raw = value.get("status") or value.get("state") or value.get("value")
    text = str(raw or "").strip().lower()
    if text in {"blocked", "unavailable", "missing", "not_ready", "failed", "rejected"}:
        return "blocked"
    if text in {"degraded", "warning", "recoverable", "legacy_incomplete"}:
        return "degraded"
    if text in {"ready", "available", "aligned", "verified", "current", "complete", "passed"}:
        return "current"
    return "unavailable"


def _field_state_name(value: Any) -> str:
    text = str(value or "unavailable").strip().lower()
    return text if text in {"current", "degraded", "blocked", "unavailable"} else "unavailable"


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_REVALIDATION_SCHEMA_VERSION,
        "transition_schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": False,
        "state": "unavailable",
        "reason_code": reason_code[:_MAX_TEXT],
        "field_count": 0,
        "fields": [],
        "next_actions": ["provide_facts", "cancel"],
    }


__all__ = [
    "EVIDENCE_REVALIDATION_SCHEMA_VERSION",
    "build_evidence_revalidation",
    "normalize_evidence_revalidation",
    "project_evidence_revalidation",
]
