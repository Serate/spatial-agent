"""Shared, bounded projection for result evidence and compatibility status.

The Runtime owns the result envelope; this module provides one read-only seam
for artifact viewers, async polling, and evaluation adapters.  It never
invents selection evidence.  Historical registries are reported as
``legacy_incomplete`` so callers can offer migration/rebuild without marking
missing evidence as current.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.action_lifecycle import project_action_lifecycle
from agent.result_completeness import (
    build_result_completeness,
    normalize_result_completeness,
)
from agent.evidence.registry import (
    EVIDENCE_REGISTRY_SCHEMA_VERSION,
    normalize_evidence_registry,
    project_evidence_registry_completeness,
)
from agent.planner_selection import normalize_planner_selection_evidence
from agent.capability_selection import normalize_capability_selection_evidence
from agent.recovery_action import normalize_action_receipt
from agent.workflow_selection import normalize_workflow_selection_evidence


EVIDENCE_PROJECTION_SCHEMA_VERSION = "spatial-agent.evidence-projection.v1"
EVIDENCE_MIGRATION_SCHEMA_VERSION = "spatial-agent.evidence-migration.v1"
EVIDENCE_RECOVERY_SCHEMA_VERSION = "spatial-agent.evidence-recovery.v1"


def project_evidence_projection(
    value: Any,
) -> dict[str, Any]:
    """Project shared evidence without exposing arbitrary nested payloads."""

    # result_contract owns the canonical bounded replan-event normalizer. Keep
    # this import lazy because result_contract also imports evidence recovery,
    # which imports this projection module.
    from result_contract import build_replanning_evidence

    payload = value if isinstance(value, Mapping) else {}
    envelope = payload.get("result")
    envelope = envelope if isinstance(envelope, Mapping) else payload
    planning = envelope.get("planning")
    if not isinstance(planning, Mapping):
        planning = payload.get("plan_evidence")
    planning = planning if isinstance(planning, Mapping) else {}

    raw_registry = envelope.get("evidence_registry")
    if raw_registry is None:
        raw_registry = payload.get("evidence_registry")
    registry = normalize_evidence_registry(raw_registry)
    completeness = project_evidence_registry_completeness(raw_registry)
    workflow = normalize_workflow_selection_evidence(
        planning.get("workflow_selection")
    )
    planner = normalize_planner_selection_evidence(
        planning.get("planner_selection")
    )
    capability_selection = normalize_capability_selection_evidence(
        planning.get("capability_selection")
    )
    migration = _migration_projection(raw_registry, completeness)
    lifecycle = _stable_lifecycle_projection(payload)
    result_completeness = (
        normalize_result_completeness(envelope.get("completeness"))
        if isinstance(envelope.get("completeness"), Mapping)
        else build_result_completeness(
            envelope,
            status=envelope.get("status") or payload.get("status"),
        )
    )
    replanning = build_replanning_evidence(_replanning_events(payload, envelope))
    replan_events = replanning.get("events")
    if isinstance(replan_events, list):
        # Timestamps belong to the detailed run record, not the stable
        # cross-entry evidence projection used by replay and comparison.
        replanning["events"] = [
            {
                key: item
                for key, item in event.items()
                if key != "occurred_at"
            }
            if isinstance(event, Mapping)
            else event
            for event in replan_events[:32]
        ]
    receipt = _stable_action_receipt(
        envelope.get("action_receipt")
        or envelope.get("interaction_receipt")
        or payload.get("action_receipt")
        or payload.get("interaction_receipt")
    )
    result = {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
        "available": bool(registry.get("available") or planning),
        "lifecycle": lifecycle,
        "completeness": result_completeness,
        "replanning": replanning,
        "evidence_registry": registry,
        "evidence_registry_completeness": completeness,
        "migration": migration,
        "selection": {
            "capability_selection": capability_selection,
            "workflow_selection": workflow,
            "planner_selection": planner,
        },
    }
    if receipt is not None:
        result["action_receipt"] = receipt
        if isinstance(receipt.get("transition_evidence"), Mapping):
            result["transition_evidence"] = dict(receipt["transition_evidence"])
    return result


def _stable_lifecycle_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep lifecycle semantics while omitting transport-specific identities.

    Artifact evidence and async result evidence are compared across entries.
    Run/action subject IDs belong to the executable interaction envelope, not
    to this shared evidence projection; retaining them would create false
    sync/async drift for otherwise identical lifecycle states.
    """
    lifecycle = project_action_lifecycle(payload)
    lifecycle.pop("subject_id", None)
    actions = lifecycle.get("actions")
    if isinstance(actions, list):
        lifecycle["actions"] = [
            {key: value for key, value in item.items() if key != "subject_id"}
            if isinstance(item, Mapping)
            else item
            for item in actions
        ]
    return lifecycle


def _replanning_events(payload: Mapping[str, Any], envelope: Mapping[str, Any]) -> Any:
    """Read current and result-envelope repair events without raw errors."""
    events = payload.get("replan_events")
    if isinstance(events, list):
        return events
    nested = envelope.get("replanning")
    if isinstance(nested, Mapping) and isinstance(nested.get("events"), list):
        return nested["events"]
    return []


def _stable_action_receipt(value: Any) -> dict[str, Any] | None:
    """Keep action semantics while omitting run-specific identity fields."""
    if not isinstance(value, Mapping):
        return None
    receipt = normalize_action_receipt(value)
    for key in (
        "subject",
        "result_ref",
        "idempotency_key",
        "input_fingerprint",
        "identity_linkage",
        "transition_identity",
    ):
        receipt.pop(key, None)
    return receipt


def _migration_projection(
    raw_registry: Any,
    completeness: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe compatibility without silently rewriting historical data."""

    if not isinstance(raw_registry, Mapping):
        return {
            "schema_version": EVIDENCE_MIGRATION_SCHEMA_VERSION,
            "state": "unavailable",
            "reason_code": "evidence_registry_missing",
            "migratable": False,
            "action": "rebuild_from_result",
        }
    raw_schema = _text(raw_registry.get("schema_version"))
    if raw_schema != EVIDENCE_REGISTRY_SCHEMA_VERSION:
        return {
            "schema_version": EVIDENCE_MIGRATION_SCHEMA_VERSION,
            "state": "unknown_schema",
            "source_schema_version": raw_schema or None,
            "reason_code": "evidence_registry_unknown_schema",
            "migratable": False,
            "action": "reject_until_explicit_migration",
        }
    if completeness.get("passed"):
        state = "current"
        reason = "evidence_registry_current"
        migratable = False
        action = "none"
    elif completeness.get("missing_entry_ids"):
        state = "legacy_incomplete"
        reason = "evidence_registry_requires_rebuild"
        migratable = True
        action = "rebuild_from_result"
    else:
        state = "incomplete"
        reason = "evidence_registry_incomplete"
        migratable = False
        action = "repair_or_reject"
    return {
        "schema_version": EVIDENCE_MIGRATION_SCHEMA_VERSION,
        "state": state,
        "source_schema_version": raw_schema,
        "reason_code": reason,
        "migratable": migratable,
        "action": action,
    }


def _text(value: Any, fallback: str = "", limit: int = 96) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:limit]


def project_evidence_recovery(value: Any) -> dict[str, Any]:
    """Project evidence migration state into one bounded recovery contract.

    Recovery is a read-only interpretation of the canonical evidence
    projection. Keeping it here means artifact, async and HTTP consumers do
    not have to learn a second module seam for the same evidence lifecycle.
    """
    projection = project_evidence_projection(value)
    migration = projection.get("migration")
    migration = migration if isinstance(migration, Mapping) else {}
    completeness = projection.get("evidence_registry_completeness")
    completeness = completeness if isinstance(completeness, Mapping) else {}
    result_completeness = projection.get("completeness")
    result_completeness = (
        result_completeness if isinstance(result_completeness, Mapping) else {}
    )
    migration_state = str(migration.get("state") or "unavailable")[:32]
    if migration_state == "current" and completeness.get("passed") is True:
        state = "ready"
        action = "none"
        allowed_actions: list[str] = []
    elif migration_state == "legacy_incomplete" and migration.get("migratable"):
        state = "recoverable"
        action = "rebuild_from_result"
        allowed_actions = ["rebuild_from_result"]
    elif migration_state == "unavailable":
        state = "unavailable"
        action = "start_new_run"
        allowed_actions = ["start_new_run"]
    else:
        state = "blocked"
        action = str(
            migration.get("action") or "reject_until_explicit_migration"
        )[:96]
        allowed_actions = [action]
    return {
        "schema_version": EVIDENCE_RECOVERY_SCHEMA_VERSION,
        "state": state,
        "reason_code": str(
            migration.get("reason_code") or "evidence_recovery_unavailable"
        )[:96],
        "action": action,
        "allowed_actions": allowed_actions[:4],
        "migratable": bool(migration.get("migratable")),
        "migration": dict(migration),
        "evidence_registry_completeness": dict(completeness),
        "completeness": dict(result_completeness),
    }


__all__ = [
    "EVIDENCE_MIGRATION_SCHEMA_VERSION",
    "EVIDENCE_PROJECTION_SCHEMA_VERSION",
    "EVIDENCE_RECOVERY_SCHEMA_VERSION",
    "project_evidence_projection",
    "project_evidence_recovery",
]
