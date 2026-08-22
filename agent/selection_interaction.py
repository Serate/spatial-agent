"""Domain-neutral interaction projection for workflow selection.

Workflow selection evidence explains what the Runtime selected.  This module
adds the small public projection that explains what a caller can do next:
choose among candidates, provide missing facts, confirm a plan, or recover a
run.  It owns no transport, persistence, Planner, or Domain policy.  Result,
async, artifact, and Console adapters consume the same bounded projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_lifecycle import project_action_lifecycle
from .recovery_action import normalize_action_ids, project_available_actions
from .workflow_selection import normalize_workflow_selection_evidence


SELECTION_INTERACTION_SCHEMA_VERSION = "spatial-agent.selection-interaction.v1"
SELECTION_INTERACTION_STATES = frozenset(
    {
        "candidate_selection",
        "facts_required",
        "confirmation_required",
        "recoverable",
        "processing",
        "completed",
        "unavailable",
    }
)
SELECTION_INTERACTION_ACTIONS = frozenset(
    {
        "select_capability",
        "select_workflow",
        "provide_facts",
        "preview",
        "confirm",
        "reject",
        "retry",
        "recover",
        "cancel",
    }
)

_MAX_ITEMS = 16
_MAX_TEXT = 128


def build_selection_interaction(
    *,
    selection: Any = None,
    clarification: Any = None,
    decision: Any = None,
    lifecycle: Any = None,
    status: str | None = None,
    subject_id: str | None = None,
) -> dict[str, Any]:
    """Build a bounded next-action projection from existing evidence.

    Precedence follows the lifecycle: clarification/facts first, then user
    confirmation, then recoverable failure, then active/completed status.  A
    malformed or future selection schema becomes ``unavailable`` rather than
    producing an action that a transport cannot safely execute.
    """

    normalized_selection = normalize_workflow_selection_evidence(selection)
    decision_map = _mapping(decision)
    lifecycle_map = (
        dict(lifecycle)
        if isinstance(lifecycle, Mapping)
        else project_action_lifecycle({"status": status})
    )
    status_value = _text(status or lifecycle_map.get("status")).upper()
    clarification_map = _mapping(clarification)
    missing = _missing_fields(normalized_selection.get("missing_fields"))
    if not missing:
        missing = _missing_fields(
            clarification_map.get("missing")
            or clarification_map.get("missing_fields")
        )
    selection_state = _text(normalized_selection.get("state"))

    if missing:
        state = "facts_required"
        reason = "selection_requires_facts"
        actions = ("provide_facts", "select_workflow", "cancel")
    elif status_value == "NEEDS_CLARIFICATION" or selection_state == "ambiguous":
        state = "candidate_selection"
        reason = "selection_requires_user_choice"
        actions = ("select_capability", "select_workflow", "cancel")
    elif status_value == "WAITING_FOR_DECISION" or _text(decision_map.get("status")) in {
        "PENDING",
        "WAITING_FOR_DECISION",
    }:
        state = "confirmation_required"
        reason = "plan_confirmation_required"
        actions = ("confirm", "reject", "cancel")
    elif lifecycle_map.get("state") == "recoverable":
        state = "recoverable"
        reason = "recovery_available"
        actions = ("retry", "recover", "cancel")
    elif status_value in {"PLANNING", "CREATED", "EXECUTING", "RUNNING", "QUEUED"}:
        state = "processing"
        reason = "run_in_progress"
        actions = ("cancel",)
    elif status_value == "COMPLETED" or lifecycle_map.get("state") == "completed":
        state = "completed"
        reason = "run_completed"
        actions = ()
    elif selection_state == "selected":
        state = "processing"
        reason = "workflow_selected"
        actions = ("preview", "cancel")
    else:
        state = "unavailable"
        reason = "selection_interaction_unavailable"
        actions = ()

    result: dict[str, Any] = {
        "schema_version": SELECTION_INTERACTION_SCHEMA_VERSION,
        "available": state != "unavailable",
        "state": state if state in SELECTION_INTERACTION_STATES else "unavailable",
        "reason_code": reason[:_MAX_TEXT],
        "status": status_value or "UNKNOWN",
        "allowed_actions": normalize_action_ids(
            actions, allowed=SELECTION_INTERACTION_ACTIONS
        ),
        "selection": normalized_selection,
        "missing_fields": missing,
        "lifecycle": _lifecycle_summary(lifecycle_map),
    }
    if subject_id:
        result["subject_id"] = _text(subject_id)
    result["actions"] = project_available_actions(
        result["allowed_actions"], subject_id=subject_id
    )
    decision_summary = _decision_summary(decision_map)
    if decision_summary:
        result["decision"] = decision_summary
    return result


def normalize_selection_interaction(value: Any) -> dict[str, Any]:
    """Normalize current and future persisted interaction evidence safely."""

    if not isinstance(value, Mapping):
        return build_selection_interaction(status="UNKNOWN")
    if value.get("schema_version") != SELECTION_INTERACTION_SCHEMA_VERSION:
        return build_selection_interaction(
            status="UNKNOWN",
            subject_id=_text(value.get("subject_id")) or None,
        )
    return build_selection_interaction(
        selection=value.get("selection"),
        clarification={"missing_fields": value.get("missing_fields")},
        decision=value.get("decision"),
        lifecycle=value.get("lifecycle"),
        status=_text(value.get("status")) or "UNKNOWN",
        subject_id=_text(value.get("subject_id")) or None,
    )


def _missing_fields(value: Any) -> list[dict[str, str]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    for item in values[:_MAX_ITEMS]:
        if isinstance(item, Mapping):
            field_id = _text(item.get("id"))
            label = _text(item.get("label"))
            kind = _text(item.get("kind")) or "fact"
            if field_id and label:
                result.append({"id": field_id, "label": label, "kind": kind})
        else:
            text = _text(item)
            if text:
                result.append({"id": text, "label": text, "kind": "fact"})
    return result


def _decision_summary(value: Mapping[str, Any]) -> dict[str, Any] | None:
    decision_id = _text(value.get("decision_id"))
    if not decision_id:
        return None
    result: dict[str, Any] = {
        "decision_id": decision_id,
        "status": _text(value.get("status")) or "UNKNOWN",
        "version": value.get("version") if isinstance(value.get("version"), int) else None,
        "options": [_text(item) for item in (value.get("options") or [])[:8] if _text(item)],
    }
    return result


def _lifecycle_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": _text(value.get("schema_version")),
        "state": _text(value.get("state")) or "failed",
        "phase": _text(value.get("phase")) or "unknown",
        "allowed_actions": normalize_action_ids(
            value.get("allowed_actions"),
            allowed={"approve", "reject", "clarify", "repair", "retry", "recover", "cancel"},
        ),
    }
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = [
    "SELECTION_INTERACTION_ACTIONS",
    "SELECTION_INTERACTION_SCHEMA_VERSION",
    "SELECTION_INTERACTION_STATES",
    "build_selection_interaction",
    "normalize_selection_interaction",
]
