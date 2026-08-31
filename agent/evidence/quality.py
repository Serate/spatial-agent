"""Auditable freshness and completeness quality for evidence sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from agent.evidence.identity import (
    SOURCE_IDENTITY_SCHEMA_VERSION,
    build_source_identity,
    normalize_source_identity,
    normalize_source_status,
)


SOURCE_QUALITY_SCHEMA_VERSION = "spatial-agent.evidence-source-quality.v1"
SOURCE_QUALITY_STATUSES = frozenset(
    {"available", "stale", "partial", "duplicate", "unavailable", "unknown"}
)
FRESHNESS_STATES = frozenset({"fresh", "stale", "unknown"})
DEFAULT_FRESHNESS_SECONDS = {
    "web": 7 * 24 * 60 * 60,
    "metrics": 90 * 24 * 60 * 60,
    "raster": 365 * 24 * 60 * 60,
    "vector": 365 * 24 * 60 * 60,
    "dataset": 365 * 24 * 60 * 60,
    "text": 30 * 24 * 60 * 60,
    "unknown": 30 * 24 * 60 * 60,
}
MAX_REASON_CODES = 12


def build_source_quality(
    value: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    freshness_ttl_seconds: int | float | None = None,
    available: bool | None = None,
    complete: bool | None = None,
    duplicate: bool = False,
    reason_codes: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Build quality from declared source facts only.

    Missing timestamps remain ``unknown``.  The function never treats a URL
    or a source name as proof that the underlying content is current.
    """

    source = value if isinstance(value, Mapping) else {}
    identity = normalize_source_identity(source)
    reasons = _unique_reasons(reason_codes)
    reasons.extend(_unique_reasons(identity.get("reason_codes")))
    if available is None:
        status = normalize_source_status(source.get("status") or source.get("state"))
        available = status not in {"unavailable"} and bool(identity.get("source_id"))
    if complete is None:
        complete = _declared_complete(source)
    completeness = "complete" if complete is True else "partial" if complete is False else "unknown"
    freshness = _freshness_projection(
        identity,
        now=now,
        freshness_ttl_seconds=freshness_ttl_seconds,
    )
    if not available:
        quality_status = "unavailable"
        reasons.append("source_unavailable")
    elif duplicate:
        quality_status = "duplicate"
        reasons.append("source_duplicate")
    elif completeness == "partial":
        quality_status = "partial"
        reasons.append("source_incomplete")
    elif freshness["state"] == "stale":
        quality_status = "stale"
        reasons.append("source_stale")
    elif freshness["state"] == "unknown":
        quality_status = "unknown"
        reasons.append("source_freshness_unknown")
    else:
        quality_status = "available"
    return {
        "schema_version": SOURCE_QUALITY_SCHEMA_VERSION,
        "status": quality_status,
        "freshness": freshness,
        "completeness": completeness,
        "duplicate": bool(duplicate),
        "reason_codes": _unique_reasons(reasons),
        "source_id": str(identity.get("source_id") or "")[:80],
    }


def project_source_record(
    value: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    freshness_ttl_seconds: int | float | None = None,
    duplicate: bool = False,
) -> dict[str, Any]:
    """Project a public source record with identity and quality metadata."""

    source = value if isinstance(value, Mapping) else {}
    identity = build_source_identity(source)
    quality = build_source_quality(
        {**source, **identity},
        now=now,
        freshness_ttl_seconds=freshness_ttl_seconds,
        duplicate=duplicate,
    )
    result: dict[str, Any] = {
        "schema_version": SOURCE_IDENTITY_SCHEMA_VERSION,
        "source_id": identity["source_id"],
        "kind": identity["kind"],
        "locator": identity["locator"],
        "title": identity["title"] or "未命名来源",
        "domain": identity["domain"],
        "quality": quality,
    }
    for field in ("version", "content_hash", "retrieved_at", "published_at"):
        if identity.get(field):
            result[field] = identity[field]
    snippet = str(source.get("snippet") or "").replace("\x00", "").strip()[:600]
    if snippet:
        result["snippet"] = snippet
    if identity["kind"] == "web" and identity["locator"]:
        result["url"] = identity["locator"]
    return result


def normalize_source_quality(value: Any) -> dict[str, Any]:
    """Normalize persisted quality without trusting arbitrary nested fields."""

    source = value if isinstance(value, Mapping) else {}
    status = str(source.get("status") or "unknown").strip().lower()
    if status not in SOURCE_QUALITY_STATUSES:
        status = "unknown"
    freshness = source.get("freshness") if isinstance(source.get("freshness"), Mapping) else {}
    freshness_state = str(freshness.get("state") or "unknown").strip().lower()
    if freshness_state not in FRESHNESS_STATES:
        freshness_state = "unknown"
    completeness = str(source.get("completeness") or "unknown").strip().lower()
    if completeness not in {"complete", "partial", "unknown"}:
        completeness = "unknown"
    return {
        "schema_version": SOURCE_QUALITY_SCHEMA_VERSION,
        "status": status,
        "freshness": {
            "state": freshness_state,
            "reference": _text(freshness.get("reference"), 32),
            "ttl_seconds": _bounded_number(
                freshness.get("ttl_seconds"), 0, 0, 31_536_000
            ),
        },
        "completeness": completeness,
        "duplicate": bool(source.get("duplicate")),
        "reason_codes": _unique_reasons(source.get("reason_codes")),
        "source_id": _text(source.get("source_id"), 80),
    }


def _freshness_projection(
    identity: Mapping[str, Any],
    *,
    now: datetime | None,
    freshness_ttl_seconds: int | float | None,
) -> dict[str, Any]:
    reference_name = "published_at" if identity.get("published_at") else "retrieved_at"
    reference_value = identity.get(reference_name)
    ttl = _bounded_number(
        freshness_ttl_seconds,
        DEFAULT_FRESHNESS_SECONDS.get(str(identity.get("kind") or "unknown"), DEFAULT_FRESHNESS_SECONDS["unknown"]),
        1,
        31_536_000,
    )
    result = {
        "state": "unknown",
        "reference": reference_name if reference_value else "unknown",
        "ttl_seconds": ttl,
    }
    if not reference_value:
        return result
    reference = _parse_datetime(reference_value)
    current = now or datetime.now(timezone.utc)
    if reference is None or current.tzinfo is None:
        return result
    current = current.astimezone(timezone.utc)
    age = (current - reference).total_seconds()
    if age < 0:
        return result
    result["state"] = "stale" if age > ttl else "fresh"
    return result


def _declared_complete(source: Mapping[str, Any]) -> bool | None:
    if isinstance(source.get("complete"), bool):
        return source["complete"]
    if isinstance(source.get("truncated"), bool):
        return not source["truncated"]
    if str(source.get("status") or "").lower() in {"partial", "degraded"}:
        return False
    return True if source.get("source_id") or source.get("url") else None


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_number(value: Any, default: int | float, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return int(default)
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(parsed, maximum))


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _unique_reasons(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for value in values:
        item = _text(value, 96)
        if item and item not in result:
            result.append(item)
        if len(result) >= MAX_REASON_CODES:
            break
    return result


__all__ = [
    "DEFAULT_FRESHNESS_SECONDS",
    "FRESHNESS_STATES",
    "SOURCE_QUALITY_SCHEMA_VERSION",
    "SOURCE_QUALITY_STATUSES",
    "build_source_quality",
    "normalize_source_quality",
    "project_source_record",
]
