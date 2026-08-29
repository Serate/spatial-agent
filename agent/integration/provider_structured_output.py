"""Provider-neutral structured-output capability profile."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION = "spatial-agent.provider-structured-output.v1"
SUPPORTED_WIRE_APIS = frozenset({"responses", "chat_completions"})
SUPPORTED_STRUCTURED_MODES = frozenset({"json_schema", "json_object", "unavailable"})
SUPPORTED_PROFILE_SOURCES = frozenset({"config", "probe", "default"})
_SAFE_METRIC_STATUSES = frozenset({"in_progress", "success", "error"})
_SAFE_METRIC_ERROR_TYPES = frozenset(
    {"http_error", "url_error", "timeout", "response_json_error", "response_shape_error"}
)
_SAFE_REASON_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


class StructuredOutputProfileError(ValueError):
    """A provider structured-output profile is invalid or unsupported."""

    def __init__(self, message: str, *, code: str = "structured_output_profile_invalid") -> None:
        self.code = str(code or "structured_output_profile_invalid")[:96]
        super().__init__(str(message)[:320])


def build_structured_output_profile(
    *,
    wire_api: Any,
    structured_mode: Any = None,
    source: Any = "config",
    reason_code: Any = "configured",
) -> dict[str, Any]:
    """Build the bounded wire capability fact used by the client/evidence."""

    normalized_wire = str(wire_api or "").strip().lower()
    if normalized_wire not in SUPPORTED_WIRE_APIS:
        raise StructuredOutputProfileError(
            "wire api is unsupported", code="structured_wire_api_invalid"
        )
    normalized_mode = str(structured_mode or "json_schema").strip().lower()
    if normalized_mode not in SUPPORTED_STRUCTURED_MODES:
        raise StructuredOutputProfileError(
            "structured output mode is unsupported",
            code="structured_mode_invalid",
        )
    normalized_source = str(source or "default").strip().lower()
    if normalized_source not in SUPPORTED_PROFILE_SOURCES:
        raise StructuredOutputProfileError(
            "structured output profile source is unsupported",
            code="structured_profile_source_invalid",
        )
    normalized_reason = str(reason_code or "configured").strip().lower()
    if not _SAFE_REASON_CODE.fullmatch(normalized_reason):
        raise StructuredOutputProfileError(
            "structured output profile reason is invalid",
            code="structured_profile_reason_invalid",
        )
    return {
        "schema_version": STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION,
        "wire_api": normalized_wire,
        "structured_mode": normalized_mode,
        "schema_enforced": normalized_mode == "json_schema",
        "source": normalized_source,
        "reason_code": normalized_reason,
    }


def project_structured_output_profile(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Safely project a profile for metrics/evidence without arbitrary fields."""

    if not isinstance(value, Mapping):
        return {
            "schema_version": STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION,
            "wire_api": "unknown",
            "structured_mode": "unavailable",
            "schema_enforced": False,
            "source": "unknown",
            "reason_code": "profile_missing",
        }
    try:
        profile = build_structured_output_profile(
            wire_api=value.get("wire_api"),
            structured_mode=value.get("structured_mode"),
            source=value.get("source"),
            reason_code=value.get("reason_code"),
        )
    except StructuredOutputProfileError:
        return {
            "schema_version": STRUCTURED_OUTPUT_PROFILE_SCHEMA_VERSION,
            "wire_api": "unknown",
            "structured_mode": "unavailable",
            "schema_enforced": False,
            "source": "invalid",
            "reason_code": "profile_invalid",
        }
    return profile


def project_structured_output_evidence(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Project provider metrics into a small, secret-free planning evidence block."""

    if not isinstance(value, Mapping) or "structured_mode" not in value:
        return None
    result = project_structured_output_profile(value)
    status = value.get("status")
    if status in _SAFE_METRIC_STATUSES:
        result["status"] = status
    error_type = value.get("error_type")
    if error_type in _SAFE_METRIC_ERROR_TYPES:
        result["error_type"] = error_type
    for key in ("attempts", "retries", "response_status"):
        item = value.get(key)
        if isinstance(item, bool):
            continue
        try:
            result[key] = max(0, min(999, int(item)))
        except (TypeError, ValueError):
            continue
    return result


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
