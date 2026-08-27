"""Bounded, domain-neutral data readiness projections.

Readiness is planning evidence, not execution authorization.  This module
keeps the useful shape of a data source (coverage, time, CRS, resolution and
alignment) consistent across discovery and planner envelopes without exposing
private paths or provider payloads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


DATA_READINESS_SCHEMA_VERSION = "spatial-agent.data-readiness.v1"
_MAX_TEXT = 256
_MAX_ITEMS = 16
_MAX_DOMAINS = 8
_PUBLIC_FIELDS = (
    "status",
    "reason_code",
    "availability_reason",
    "coverage",
    "time_range",
    "crs",
    "resolution",
    "alignment",
    "source_id",
    "source_url",
    "quality",
    "observed_at",
    "version",
)
_PRIVATE_KEY_PARTS = (
    "path",
    "file",
    "token",
    "secret",
    "password",
    "api_key",
    "prompt",
    "response",
)


def project_data_readiness(value: Any) -> dict[str, Any]:
    """Return a bounded readiness object safe for planner and evidence use."""

    source = value if isinstance(value, Mapping) else {"status": value}
    result: dict[str, Any] = {
        "schema_version": DATA_READINESS_SCHEMA_VERSION,
        "status": _text(source.get("status") or source.get("state")) or "unknown",
    }
    for key in _PUBLIC_FIELDS:
        if key == "status" or source.get(key) is None:
            continue
        if key == "alignment":
            result[key] = _alignment(source.get(key))
        else:
            result[key] = _safe(source.get(key), depth=0)
    domains = source.get("domains")
    if isinstance(domains, Mapping):
        projected_domains: dict[str, dict[str, Any]] = {}
        for domain_id, raw in list(domains.items())[:_MAX_DOMAINS]:
            domain_key = _text(domain_id, 64)
            if domain_key:
                projected_domains[domain_key] = project_data_readiness(raw)
        if projected_domains:
            result["domains"] = projected_domains
    return result


def _alignment(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": _text(value) or "unknown"}
    result: dict[str, Any] = {
        "status": _text(value.get("status") or value.get("state")) or "unknown"
    }
    for key in (
        "reason",
        "reason_code",
        "method",
        "reference",
        "metadata_only",
        "pixels_read",
        "overlapping_pairs",
    ):
        if value.get(key) is not None:
            result[key] = _safe(value.get(key), depth=0)
    return result


def _safe(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_TEXT]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            key_text = _text(key, 64)
            if not key_text or any(part in key_text.lower() for part in _PRIVATE_KEY_PARTS):
                continue
            result[key_text] = _safe(item, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe(item, depth=depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return _text(value)


def _text(value: Any, limit: int = _MAX_TEXT) -> str:
    return str(value).strip()[:limit] if value is not None else ""


__all__ = ["DATA_READINESS_SCHEMA_VERSION", "project_data_readiness"]
