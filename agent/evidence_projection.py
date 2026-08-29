"""Compatibility facade for the canonical evidence projection."""

from agent.evidence.projection import *  # noqa: F401,F403

__all__ = [
    "EVIDENCE_MIGRATION_SCHEMA_VERSION",
    "EVIDENCE_PROJECTION_SCHEMA_VERSION",
    "EVIDENCE_RECOVERY_SCHEMA_VERSION",
    "project_evidence_projection",
    "project_evidence_recovery",
]
