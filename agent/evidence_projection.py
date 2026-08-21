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

from .evidence_registry import (
    EVIDENCE_REGISTRY_SCHEMA_VERSION,
    normalize_evidence_registry,
    project_evidence_registry_completeness,
)
from .planner_selection import normalize_planner_selection_evidence
from .workflow_selection import normalize_workflow_selection_evidence


EVIDENCE_PROJECTION_SCHEMA_VERSION = "spatial-agent.evidence-projection.v1"
EVIDENCE_MIGRATION_SCHEMA_VERSION = "spatial-agent.evidence-migration.v1"


def project_evidence_projection(
    value: Any,
) -> dict[str, Any]:
    """Project shared evidence without exposing arbitrary nested payloads."""

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
    migration = _migration_projection(raw_registry, completeness)
    return {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
        "available": bool(registry.get("available") or planning),
        "evidence_registry": registry,
        "evidence_registry_completeness": completeness,
        "migration": migration,
        "selection": {
            "workflow_selection": workflow,
            "planner_selection": planner,
        },
    }


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


__all__ = [
    "EVIDENCE_MIGRATION_SCHEMA_VERSION",
    "EVIDENCE_PROJECTION_SCHEMA_VERSION",
    "project_evidence_projection",
]
