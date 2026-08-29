"""Compatibility facade for canonical evidence revalidation."""

from agent.evidence.revalidation import *  # noqa: F401,F403

__all__ = [
    "EVIDENCE_BINDING_SCHEMA_VERSION",
    "EVIDENCE_REVALIDATION_SCHEMA_VERSION",
    "build_evidence_binding",
    "build_evidence_revalidation",
    "build_evidence_revalidation_gate",
    "normalize_evidence_binding",
    "normalize_evidence_revalidation",
    "project_evidence_revalidation",
]
