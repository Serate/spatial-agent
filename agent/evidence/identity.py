"""Stable, domain-neutral identity for bounded evidence sources.

Source identity is deliberately smaller than a result.  It carries safe
locators, versions and fingerprints so different tools can recognize the
same source without persisting document bodies, local paths or credentials.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from typing import Any


SOURCE_IDENTITY_SCHEMA_VERSION = "spatial-agent.evidence-source-identity.v1"
SOURCE_IDENTITY_STATUSES = frozenset(
    {"available", "ok", "degraded", "partial", "unavailable", "unknown"}
)
MAX_SOURCE_ID = 80
MAX_LOCATOR = 2048
MAX_TEXT = 240
MAX_VERSION = 96
MAX_REASON_CODES = 8

_TOKEN_RE = re.compile(r"^[A-Za-z0-9:._/-]+$")
_KIND_ALIASES = {
    "document_evidence": "web",
    "web_document": "web",
    "web": "web",
    "raster": "raster",
    "vector": "vector",
    "metrics": "metrics",
    "metric": "metrics",
    "text": "text",
    "dataset": "dataset",
}


def build_source_identity(
    value: Mapping[str, Any] | None,
    *,
    source_kind: Any = None,
) -> dict[str, Any]:
    """Build a safe, stable identity projection from a source-shaped value."""

    source = value if isinstance(value, Mapping) else {}
    kind = normalize_source_kind(
        source_kind
        or source.get("kind")
        or source.get("source_kind")
        or source.get("data_kind")
        or source.get("result_type")
    )
    raw_locator = (
        source.get("locator")
        or source.get("url")
        or source.get("dataset_id")
        or source.get("asset_id")
        or source.get("source")
    )
    locator, locator_kind = normalize_source_locator(raw_locator)
    if locator_kind == "web":
        kind = "web"
    version = _safe_text(
        source.get("version") or source.get("data_version") or source.get("release"),
        MAX_VERSION,
    )
    content_hash = normalize_content_hash(source.get("content_hash"))
    status = normalize_source_status(source.get("status") or source.get("state"))
    title = _safe_text(source.get("title") or source.get("name"), MAX_TEXT)
    domain = _safe_domain(source.get("domain"))
    if not domain and locator_kind == "web":
        try:
            domain = (urlsplit(locator).hostname or "").lower().rstrip(".")[:255]
        except ValueError:
            domain = ""
    retrieved_at = normalize_timestamp(source.get("retrieved_at"))
    published_at = normalize_timestamp(source.get("published_at"))
    reasons: list[str] = []
    if not locator:
        reasons.append("source_locator_missing")
        status = "unavailable"
    source_id = build_source_id(
        kind=kind,
        locator=locator,
        version=version,
        content_hash=content_hash,
    )
    result: dict[str, Any] = {
        "schema_version": SOURCE_IDENTITY_SCHEMA_VERSION,
        "source_id": source_id,
        "kind": kind,
        "locator": locator,
        "version": version,
        "content_hash": content_hash,
        "status": status,
        "title": title,
        "domain": domain,
        "reason_codes": reasons[:MAX_REASON_CODES],
    }
    if retrieved_at:
        result["retrieved_at"] = retrieved_at
    if published_at:
        result["published_at"] = published_at
    return result


def normalize_source_identity(value: Any) -> dict[str, Any]:
    """Normalize a persisted identity without trusting its source id."""

    source = value if isinstance(value, Mapping) else {}
    identity = build_source_identity(source, source_kind=source.get("kind"))
    if source.get("schema_version") != SOURCE_IDENTITY_SCHEMA_VERSION:
        identity["reason_codes"] = _unique_reasons(
            ["source_identity_legacy_schema", *identity["reason_codes"]]
        )
    return identity


def build_source_id(
    *,
    kind: Any,
    locator: Any,
    version: Any = "",
    content_hash: Any = "",
) -> str:
    """Return a stable opaque id; an empty locator cannot form an identity."""

    normalized_locator, _ = normalize_source_locator(locator)
    if not normalized_locator:
        return ""
    payload = "\n".join(
        (
            normalize_source_kind(kind),
            normalized_locator,
            _safe_text(version, MAX_VERSION),
            normalize_content_hash(content_hash),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return "source-" + digest[: MAX_SOURCE_ID - 7]


def source_dedupe_key(value: Mapping[str, Any] | None) -> str:
    """Return a deterministic key for same-content or same-location sources."""

    identity = normalize_source_identity(value)
    content_hash = identity.get("content_hash") or ""
    if content_hash.lower().startswith("sha256:"):
        return "content:" + content_hash.lower()
    locator = identity.get("locator") or ""
    if locator:
        return "locator:" + ":".join(
            (
                str(identity.get("kind") or "unknown"),
                locator,
                str(identity.get("version") or ""),
            )
        )
    return "source:" + str(identity.get("source_id") or "unknown")


def normalize_source_kind(value: Any) -> str:
    raw = _safe_text(value, 48).lower().replace("-", "_")
    return _KIND_ALIASES.get(raw, raw or "unknown")


def normalize_source_status(value: Any) -> str:
    raw = _safe_text(value, 32).lower()
    if raw in {"success", "completed", "available"}:
        return "available"
    if raw in {"error", "failed", "missing"}:
        return "unavailable"
    if raw in {"warning"}:
        return "degraded"
    return raw if raw in SOURCE_IDENTITY_STATUSES else "unknown"


def normalize_source_locator(value: Any) -> tuple[str, str]:
    """Normalize an HTTPS/HTTP URL or a non-path public dataset identifier."""

    raw = _safe_text(value, MAX_LOCATOR)
    if not raw:
        return "", "unknown"
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "", "unknown"
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"}:
            # ``urlsplit`` treats identifiers such as ``indicator:demo`` as
            # schemes.  Keep opaque public dataset ids valid, while local
            # paths and explicitly unsafe URI forms remain rejected below.
            if (
                parsed.netloc
                or parsed.path.startswith(("/", "\\"))
                or "\\" in raw
                or parsed.scheme.lower() in {"file", "data", "javascript"}
                or not _TOKEN_RE.fullmatch(raw)
            ):
                return "", "unknown"
            return raw[:MAX_LOCATOR], "dataset"
        if parsed.username or parsed.password or not parsed.hostname:
            return "", "unknown"
        try:
            port = parsed.port
        except ValueError:
            return "", "unknown"
        host = parsed.hostname.lower().rstrip(".")
        netloc = host
        if port is not None and not (
            (parsed.scheme.lower() == "https" and port == 443)
            or (parsed.scheme.lower() == "http" and port == 80)
        ):
            netloc += ":" + str(port)
        return (
            urlunsplit(
                (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
            )[:MAX_LOCATOR],
            "web",
        )
    if raw.startswith(('/', "\\")) or "\\" in raw or "\x00" in raw:
        return "", "unknown"
    if not _TOKEN_RE.fullmatch(raw):
        return "", "unknown"
    return raw[:MAX_LOCATOR], "dataset"


def normalize_content_hash(value: Any) -> str:
    raw = _safe_text(value, 128)
    return raw if raw.lower().startswith("sha256:") and _TOKEN_RE.fullmatch(raw) else ""


def normalize_timestamp(value: Any) -> str:
    raw = _safe_text(value, 64)
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _safe_domain(value: Any) -> str:
    raw = _safe_text(value, 255).lower().rstrip(".")
    if not raw or "/" in raw or ":" in raw or " " in raw or "." not in raw:
        return ""
    return raw


def _safe_text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _unique_reasons(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = _safe_text(value, 96)
        if item and item not in result:
            result.append(item)
        if len(result) >= MAX_REASON_CODES:
            break
    return result


__all__ = [
    "MAX_LOCATOR",
    "SOURCE_IDENTITY_SCHEMA_VERSION",
    "SOURCE_IDENTITY_STATUSES",
    "build_source_id",
    "build_source_identity",
    "normalize_content_hash",
    "normalize_source_identity",
    "normalize_source_kind",
    "normalize_source_locator",
    "normalize_source_status",
    "normalize_timestamp",
    "source_dedupe_key",
]
