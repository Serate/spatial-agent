"""Domain-neutral migration and recovery projection for public evidence.

This module is deliberately read-only.  It gives every result surface the
same bounded interpretation of an evidence registry's compatibility state;
actual artifact rewrites remain owned by the persistence adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .evidence_projection import project_evidence_projection


EVIDENCE_RECOVERY_SCHEMA_VERSION = "spatial-agent.evidence-recovery.v1"


def project_evidence_recovery(value: Any) -> dict[str, Any]:
    """Project migration state into a safe lifecycle and allowed actions."""

    projection = project_evidence_projection(value)
    migration = projection.get("migration")
    migration = migration if isinstance(migration, Mapping) else {}
    completeness = projection.get("evidence_registry_completeness")
    completeness = completeness if isinstance(completeness, Mapping) else {}
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
        action = str(migration.get("action") or "reject_until_explicit_migration")[:96]
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
    }


__all__ = [
    "EVIDENCE_RECOVERY_SCHEMA_VERSION",
    "project_evidence_recovery",
]
