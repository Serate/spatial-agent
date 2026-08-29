"""Compatibility facade for the canonical evidence contract."""

from agent.evidence.contract import *  # noqa: F401,F403

__all__ = [
    "DOMAIN_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_CATALOG_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_EVIDENCE_STATUSES",
    "EVIDENCE_KINDS",
    "EvidenceProvider",
    "attach_evidence_contract",
    "build_capability_evidence",
    "project_capability_catalog_evidence",
    "normalize_capability_evidence",
]
