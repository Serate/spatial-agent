"""Domain-neutral action and receipt projection seam.

The Runtime has several callers that need to describe a next action without
owning its execution: lifecycle, selection, decision, and evidence recovery.
This module keeps that shared vocabulary small.  Persistence adapters may
store richer records, but public result/artifact/HTTP/Console surfaces use
these bounded projections.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Iterable

RECOVERY_ACTION_SCHEMA_VERSION = "spatial-agent.recovery-action.v1"
ACTION_RECEIPT_SCHEMA_VERSION = "spatial-agent.action-receipt.v1"

ACTION_RECEIPT_STATES = frozenset({"IN_PROGRESS", "COMPLETED", "FAILED"})

ACTION_IDS = frozenset(
    {
        "approve",
        "reject",
        "clarify",
        "repair",
        "retry",
        "recover",
        "cancel",
        "confirm",
        "select_capability",
        "select_workflow",
        "provide_facts",
        "preview",
        "rebuild_from_result",
        "start_new_run",
    }
)

_RECEIPT_ACTIONS = frozenset(
    {
        "confirm",
        "reject",
        "retry",
        "recover",
        "cancel",
        "select_capability",
        "select_workflow",
        "provide_facts",
        "preview",
        "rebuild_from_result",
        "start_new_run",
    }
)
_MAX_TEXT = 160
_MAX_ACTIONS = 12


def normalize_action_id(value: Any, *, allowed: Iterable[str] | None = None) -> str:
    """Normalize one action ID and reject values outside a supplied set."""

    action = str(value or "").strip().lower()[:_MAX_TEXT]
    if not action:
        return ""
    allowed_values = set(allowed) if allowed is not None else ACTION_IDS
    return action if action in allowed_values else ""


def normalize_action_ids(
    values: Any, *, allowed: Iterable[str] | None = None
) -> list[str]:
    """Return deterministic, bounded, duplicate-free action IDs."""

    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set, frozenset)):
        return []
    result: list[str] = []
    for value in values:
        action = normalize_action_id(value, allowed=allowed)
        if action and action not in result:
            result.append(action)
        if len(result) >= _MAX_ACTIONS:
            break
    return result


def project_available_actions(
    actions: Any,
    *,
    subject_id: str | None = None,
) -> list[dict[str, Any]]:
    """Project allowed IDs into a transport-neutral action catalogue."""

    normalized = normalize_action_ids(actions)
    result = []
    for action in normalized:
        item: dict[str, Any] = {
            "schema_version": RECOVERY_ACTION_SCHEMA_VERSION,
            "id": action,
            "kind": _action_kind(action),
            "state": "available",
            "requires_receipt": action in _RECEIPT_ACTIONS,
            "idempotency_required": action in _RECEIPT_ACTIONS,
        }
        if subject_id:
            item["subject_id"] = str(subject_id)[:_MAX_TEXT]
        result.append(item)
    return result


def action_input_fingerprint(action_id: Any, payload: Any) -> str:
    """Create a stable, non-reversible fingerprint for an action input."""

    encoded = json.dumps(
        {"action_id": str(action_id), "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def project_action_receipt(
    receipt: Mapping[str, Any] | None,
    *,
    reused: bool = False,
) -> dict[str, Any]:
    """Project a stored interaction/recovery record into one receipt shape."""

    value = receipt if isinstance(receipt, Mapping) else {}
    action_id = normalize_action_id(value.get("action_id") or value.get("action"))
    status = str(value.get("status") or "UNKNOWN").strip().upper()[:32]
    if status not in ACTION_RECEIPT_STATES:
        status = "FAILED" if status not in {"UNKNOWN", ""} else "IN_PROGRESS"
    subject = value.get("subject") if isinstance(value.get("subject"), Mapping) else {}
    result_ref = value.get("result_ref") if isinstance(value.get("result_ref"), Mapping) else {}
    source_id = str(
        value.get("source_run_id") or value.get("run_id") or subject.get("id") or ""
    )[:_MAX_TEXT]
    result_id = str(
        value.get("result_run_id") or result_ref.get("id") or ""
    )[:_MAX_TEXT] or None
    result: dict[str, Any] = {
        "schema_version": ACTION_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "action_id": action_id or "unknown",
        "action_kind": _action_kind(action_id),
        "subject": {"kind": "run", "id": source_id} if source_id else None,
        "result_ref": {"kind": "run", "id": result_id} if result_id else None,
        "idempotency_key": str(value.get("idempotency_key") or "")[:128],
        "input_fingerprint": str(value.get("input_fingerprint") or "")[:160],
        "reused": bool(reused),
    }
    error_code = str(value.get("error_code") or "")[:96]
    if error_code:
        result["error_code"] = error_code
    # Import lazily: action_identity reads Evidence Projection, whose
    # lifecycle registry imports this module for the action allowlist.
    from .action_identity import normalize_action_receipt_identity_linkage

    linkage = normalize_action_receipt_identity_linkage(value.get("identity_linkage"))
    if linkage is not None:
        result["identity_linkage"] = linkage
    if "preconditions" in value:
        # Keep this import lazy with the other lifecycle/evidence projection
        # dependency.  Old receipts omit the field and remain readable.
        from .action_precondition import normalize_action_preconditions

        result["preconditions"] = normalize_action_preconditions(
            value.get("preconditions")
        )
    return result


def project_legacy_interaction_receipt(
    receipt: Mapping[str, Any] | None,
    *,
    reused: bool = False,
) -> dict[str, Any]:
    """Keep the M169 field shape while deriving it from the shared seam."""

    value = project_action_receipt(receipt, reused=reused)
    subject = value.get("subject") if isinstance(value.get("subject"), Mapping) else {}
    result_ref = value.get("result_ref") if isinstance(value.get("result_ref"), Mapping) else {}
    return {
        "schema_version": "spatial-agent.interaction-receipt.v1",
        "status": value["status"],
        "action": value["action_id"],
        "source_run_id": str(subject.get("id") or "")[:_MAX_TEXT],
        "result_run_id": str(result_ref.get("id") or "")[:_MAX_TEXT] or None,
        "idempotency_key": value["idempotency_key"],
        "reused": value["reused"],
    }


def normalize_action_receipt(value: Any) -> dict[str, Any]:
    """Normalize a current or legacy receipt without exposing arbitrary data."""

    if not isinstance(value, Mapping):
        return {
            "schema_version": ACTION_RECEIPT_SCHEMA_VERSION,
            "status": "FAILED",
            "action_id": "unknown",
            "action_kind": "unknown",
            "subject": None,
            "result_ref": None,
            "idempotency_key": "",
            "input_fingerprint": "",
            "reused": False,
            "error_code": "action_receipt_unavailable",
        }
    return project_action_receipt(value, reused=value.get("reused") is True)


def _action_kind(action_id: str) -> str:
    if action_id in {"select_capability", "select_workflow", "provide_facts", "preview"}:
        return "interaction"
    if action_id in {"approve", "confirm", "reject", "clarify", "repair"}:
        return "decision"
    if action_id in {"rebuild_from_result", "start_new_run"}:
        return "evidence_recovery"
    if action_id in {"retry", "recover", "cancel"}:
        return "lifecycle"
    return "unknown"


__all__ = [
    "ACTION_IDS",
    "ACTION_RECEIPT_SCHEMA_VERSION",
    "ACTION_RECEIPT_STATES",
    "RECOVERY_ACTION_SCHEMA_VERSION",
    "action_input_fingerprint",
    "normalize_action_id",
    "normalize_action_ids",
    "normalize_action_receipt",
    "project_action_receipt",
    "project_available_actions",
    "project_legacy_interaction_receipt",
]
