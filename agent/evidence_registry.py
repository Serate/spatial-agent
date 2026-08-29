"""Compatibility facade for the canonical evidence registry."""

from agent.evidence.registry import *  # noqa: F401,F403

__all__ = [
    "EVIDENCE_COMPLETENESS_SCHEMA_VERSION",
    "EVIDENCE_REGISTRY_SCHEMA_VERSION",
    "REPLANNING_SCHEMA_VERSION",
    "build_evidence_registry",
    "normalize_evidence_registry",
    "project_evidence_registry_completeness",
]
