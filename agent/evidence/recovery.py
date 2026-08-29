"""Compatibility facade for the canonical evidence projection seam.

The recovery projection now lives beside the evidence projection so all
consumers use one deep, read-only contract. Keep this import path for
artifact readers and historical integrations.
"""

from agent.evidence.projection import (
    EVIDENCE_RECOVERY_SCHEMA_VERSION,
    project_evidence_recovery,
)

__all__ = [
    "EVIDENCE_RECOVERY_SCHEMA_VERSION",
    "project_evidence_recovery",
]
