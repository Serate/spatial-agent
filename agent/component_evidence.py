"""Compatibility facade for canonical component evidence."""

from agent.evidence.component import *  # noqa: F401,F403

__all__ = [
    "WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION",
    "normalize_component_evidence",
    "normalize_workflow_component_evidence",
    "project_workflow_component_evidence",
]
