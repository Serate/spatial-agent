"""Domain-neutral result data-shape profiles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable

from agent.contract_versions import DATA_PROFILE_SCHEMA_VERSION


SUPPORTED_DATA_KINDS = (
    "unknown",
    "text",
    "vector",
    "raster",
    "metrics",
    "timeseries",
    "document_evidence",
    "composite",
)
MAX_DATA_KINDS = 8


class DataProfileError(ValueError):
    """A result data profile cannot be safely interpreted."""


def normalize_data_kinds(value: Any, *, allow_empty: bool = False) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise DataProfileError("data_profile.kinds must be a list")
    normalized = []
    for item in values[:MAX_DATA_KINDS]:
        kind = str(item or "").strip()
        if not kind:
            continue
        if kind not in SUPPORTED_DATA_KINDS:
            raise DataProfileError("unsupported result data kind")
        if kind not in normalized:
            normalized.append(kind)
    if not normalized and not allow_empty:
        raise DataProfileError("data_profile.kinds must not be empty")
    return normalized


def build_data_profile(kinds: Iterable[str] | None) -> dict[str, Any]:
    normalized = normalize_data_kinds(list(kinds or ("unknown",)))
    return {
        "schema_version": DATA_PROFILE_SCHEMA_VERSION,
        "primary": normalized[0],
        "kinds": normalized,
    }


def normalize_data_profile(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    if value is None:
        if allow_legacy:
            return build_data_profile(("unknown",))
        raise DataProfileError("data_profile is required")
    if not isinstance(value, Mapping):
        raise DataProfileError("data_profile must be an object")
    version = value.get("schema_version")
    if version in (None, ""):
        if not allow_legacy:
            raise DataProfileError("data_profile.schema_version is required")
    elif str(version) != DATA_PROFILE_SCHEMA_VERSION:
        raise DataProfileError("unknown data profile schema version")
    kinds = normalize_data_kinds(value.get("kinds"), allow_empty=False)
    primary = str(value.get("primary") or kinds[0]).strip()
    if primary not in kinds:
        raise DataProfileError("data_profile.primary must be listed in kinds")
    return {
        "schema_version": DATA_PROFILE_SCHEMA_VERSION,
        "primary": primary,
        "kinds": kinds,
    }


__all__ = [
    "SUPPORTED_DATA_KINDS",
    "MAX_DATA_KINDS",
    "DataProfileError",
    "normalize_data_kinds",
    "build_data_profile",
    "normalize_data_profile",
]
