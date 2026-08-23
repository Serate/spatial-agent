"""Domain-neutral Harness for a sequence of canonical interactions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from agent.interaction_contract import project_interaction
from agent.recovery_action import normalize_action_receipt


INTERACTION_JOURNEY_SCHEMA_VERSION = "spatial-agent.interaction-journey.v1"
_MAX_EVENTS = 32


def capture_interaction_journey(entries: Iterable[Any]) -> dict[str, Any]:
    """Capture bounded public interaction semantics without request payloads."""

    events = []
    reasons = []
    root = None
    previous_revision = -1
    for index, source in enumerate(entries):
        if index >= _MAX_EVENTS:
            reasons.append("interaction_journey_truncated")
            break
        interaction = project_interaction(source)
        subject = interaction.get("subject")
        subject = subject if isinstance(subject, Mapping) else {}
        event_root = _reference(subject.get("root"))
        current = _reference(subject.get("current"))
        revision = subject.get("revision")
        revision = revision if isinstance(revision, int) and not isinstance(revision, bool) else 0
        if root is None:
            root = event_root
        elif event_root != root:
            reasons.append("interaction_root_drift")
        if revision < previous_revision:
            reasons.append("interaction_revision_regressed")
        previous_revision = max(previous_revision, revision)
        receipt = interaction.get("receipt")
        normalized_receipt = (
            normalize_action_receipt(receipt)
            if isinstance(receipt, Mapping)
            else None
        )
        events.append(
            {
                "index": index,
                "available": bool(interaction.get("available")),
                "subject": {
                    "root": event_root,
                    "current": current,
                    "revision": revision,
                },
                "kind": str(interaction.get("kind") or "unavailable")[:64],
                "state": str(interaction.get("state") or "unavailable")[:48],
                "status": str(interaction.get("status") or "UNKNOWN")[:32],
                "action_ids": [
                    str(item.get("id") or "")[:48]
                    for item in interaction.get("actions") or ()
                    if isinstance(item, Mapping) and item.get("id")
                ][:12],
                "receipt": _receipt_core(normalized_receipt),
            }
        )
        if not interaction.get("available"):
            reasons.append("interaction_unavailable")
    return {
        "schema_version": INTERACTION_JOURNEY_SCHEMA_VERSION,
        "valid": not reasons,
        "reason_codes": list(dict.fromkeys(reasons)),
        "root": root or {"kind": "unknown", "id": "unknown"},
        "event_count": len(events),
        "events": events,
    }


def compare_interaction_entries(entries: Iterable[Any]) -> list[str]:
    """Compare equivalent transport/artifact/restart interaction projections."""

    values = [_equivalent_core(project_interaction(item)) for item in entries]
    if len(values) < 2:
        return []
    reference = values[0]
    differences = []
    for index, candidate in enumerate(values[1:], start=1):
        _compare(reference, candidate, f"entry[{index}]", differences)
    return differences


def _equivalent_core(interaction: Mapping[str, Any]) -> dict[str, Any]:
    receipt = interaction.get("receipt")
    normalized_receipt = (
        normalize_action_receipt(receipt)
        if isinstance(receipt, Mapping)
        else None
    )
    return {
        "schema_version": interaction.get("schema_version"),
        "available": bool(interaction.get("available")),
        "subject": interaction.get("subject"),
        "kind": interaction.get("kind"),
        "state": interaction.get("state"),
        "phase": interaction.get("phase"),
        "status": interaction.get("status"),
        "reason_code": interaction.get("reason_code"),
        "action_ids": [
            item.get("id")
            for item in interaction.get("actions") or ()
            if isinstance(item, Mapping)
        ],
        "blocked_actions": list(interaction.get("blocked_actions") or ()),
        "receipt": _receipt_core(normalized_receipt),
        "lineage": interaction.get("lineage"),
    }


def _receipt_core(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "status": value.get("status"),
        "action_id": value.get("action_id"),
        "subject": value.get("subject"),
        "result_ref": value.get("result_ref"),
        "idempotency_key": value.get("idempotency_key"),
        "input_fingerprint": value.get("input_fingerprint"),
    }


def _reference(value: Any) -> dict[str, str]:
    item = value if isinstance(value, Mapping) else {}
    return {
        "kind": str(item.get("kind") or "unknown")[:32],
        "id": str(item.get("id") or "unknown")[:160],
    }


def _compare(reference: Any, candidate: Any, path: str, differences: list[str]) -> None:
    if isinstance(reference, Mapping) and isinstance(candidate, Mapping):
        keys = sorted(set(reference) | set(candidate))
        for key in keys:
            _compare(reference.get(key), candidate.get(key), path + "." + str(key), differences)
        return
    if isinstance(reference, list) and isinstance(candidate, list):
        if reference != candidate:
            differences.append(path)
        return
    if reference != candidate:
        differences.append(path)


__all__ = [
    "INTERACTION_JOURNEY_SCHEMA_VERSION",
    "capture_interaction_journey",
    "compare_interaction_entries",
]
