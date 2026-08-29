"""Compatibility facade for the canonical structured-output provider seam."""

from agent.integration.provider_structured_output import (
    STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION,
    SUPPORTED_STRUCTURED_MODES,
    SUPPORTED_PROFILE_SOURCES,
    SUPPORTED_WIRE_APIS,
    StructuredOutputProfileError,
    build_structured_output_profile,
    project_structured_output_evidence,
    project_structured_output_profile,
)

__all__ = [
    "STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION",
    "SUPPORTED_STRUCTURED_MODES",
    "SUPPORTED_PROFILE_SOURCES",
    "SUPPORTED_WIRE_APIS",
    "StructuredOutputProfileError",
    "build_structured_output_profile",
    "project_structured_output_evidence",
    "project_structured_output_profile",
]
