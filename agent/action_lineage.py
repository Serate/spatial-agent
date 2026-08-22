"""Bounded, domain-neutral lineage for consecutive lifecycle actions.

The Runtime lifecycle remains the only state machine.  This module only
projects the already persisted Action Receipts so a recovered result can
explain which actions led to it without copying private inputs or transport
identifiers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ACTION_LINEAGE_SCHEMA_VERSION = "spatial-agent.action-lineage.v1"
_EVENT_SCHEMA_VERSION = "spatial-agent.action-lineage-event.v1"
_MAX_EVENTS = 16
_MAX_TEXT = 96


def project_action_lineage(value: Any) -> dict[str, Any]:
    """Normalize a list of receipts or lineage events into one safe shape."""
    if isinstance(value, Mapping):
        if value.get("schema_version") != ACTION_LINEAGE_SCHEMA_VERSION:
            return _unavailable("action_lineage_unknown_schema")
        raw_events = value.get("events")
    else:
        raw_events = value
    if not isinstance(raw_events, list):
        return _unavailable("action_lineage_missing")
    events = []
    for item in raw_events[:_MAX_EVENTS]:
        event = _event(item)
        if event:
            events.append(event)
    return {
        "schema_version": ACTION_LINEAGE_SCHEMA_VERSION,
        "available": bool(events),
        "event_count": len(events),
        "events": events,
    }


def normalize_action_lineage(value: Any) -> dict[str, Any]:
    """Read a persisted lineage; unknown versions become unavailable."""
    return project_action_lineage(value)


def append_action_lineage(previous: Any, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Append one completed receipt while retaining only bounded history."""
    existing = project_action_lineage(previous)
    events = list(existing.get("events") or []) if existing.get("available") else []
    current = _event(receipt)
    if current:
        events.append(current)
    return project_action_lineage(events[-_MAX_EVENTS:])


def _event(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    from .action_identity import normalize_action_receipt_identity_linkage
    from .action_effect import normalize_action_effect
    from .action_precondition import normalize_action_preconditions

    if isinstance(value.get("action_linkage"), Mapping):
        linkage = value["action_linkage"]
        action_id = _text(linkage.get("action_id"))
        action_kind = _text(linkage.get("action_kind"))
        status = _text(linkage.get("status")) or "UNKNOWN"
        subject_kind = _text(linkage.get("subject_kind")) or None
        result_kind = _text(linkage.get("result_kind")) or None
        identity = normalize_action_receipt_identity_linkage(
            linkage.get("identity_linkage")
        ) or {
            "schema_version": "spatial-agent.action-receipt-linkage.v1",
            "available": False,
        }
        preconditions = normalize_action_preconditions(linkage.get("preconditions"))
        effect = normalize_action_effect(linkage.get("effect"))
    else:
        from .recovery_action import normalize_action_receipt

        receipt = normalize_action_receipt(value)
        action_id = _text(receipt.get("action_id"))
        action_kind = _text(receipt.get("action_kind"))
        status = _text(receipt.get("status")) or "UNKNOWN"
        subject = receipt.get("subject") if isinstance(receipt.get("subject"), Mapping) else {}
        result_ref = receipt.get("result_ref") if isinstance(receipt.get("result_ref"), Mapping) else {}
        subject_kind = _text(subject.get("kind")) or None
        result_kind = _text(result_ref.get("kind")) or None
        identity = normalize_action_receipt_identity_linkage(
            receipt.get("identity_linkage")
        ) or {
            "schema_version": "spatial-agent.action-receipt-linkage.v1",
            "available": False,
        }
        preconditions = normalize_action_preconditions(receipt.get("preconditions"))
        effect = normalize_action_effect(receipt.get("effect"))
    if not action_id:
        return None
    return {
        "schema_version": _EVENT_SCHEMA_VERSION,
        "action_id": action_id,
        "action_kind": action_kind or "unknown",
        "status": status,
        "subject_kind": subject_kind,
        "result_kind": result_kind,
        "identity_linkage": identity,
        "preconditions": preconditions,
        "effect": effect,
    }


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": ACTION_LINEAGE_SCHEMA_VERSION,
        "available": False,
        "event_count": 0,
        "events": [],
        "reason_code": _text(reason_code),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = [
    "ACTION_LINEAGE_SCHEMA_VERSION",
    "append_action_lineage",
    "normalize_action_lineage",
    "project_action_lineage",
]
