"""Bounded aggregation of heterogeneous evidence source records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from agent.evidence.identity import normalize_source_locator, source_dedupe_key
from agent.evidence.quality import (
    FRESHNESS_STATES,
    SOURCE_QUALITY_STATUSES,
    normalize_source_quality,
    project_source_record,
)


EVIDENCE_BUNDLE_SCHEMA_VERSION = "spatial-agent.evidence-bundle.v1"
MAX_BUNDLE_ENTRIES = 16
MAX_DUPLICATES = 16
MAX_CONFLICTS = 16
MAX_LIMITATIONS = 12


def build_evidence_bundle(
    entries: Sequence[Mapping[str, Any]] | None,
    *,
    now: datetime | None = None,
    max_entries: int = MAX_BUNDLE_ENTRIES,
) -> dict[str, Any]:
    """Build a stable, bounded source bundle from Web/Domain evidence."""

    limit = _bounded_limit(max_entries)
    canonical: list[dict[str, Any]] = []
    duplicates: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    seen: dict[str, dict[str, Any]] = {}
    by_locator: dict[str, dict[str, Any]] = {}
    rejected_count = 0
    candidates: list[dict[str, Any]] = []
    for raw in list(entries or [])[: limit * 4]:
        if not isinstance(raw, Mapping):
            rejected_count += 1
            continue
        projected = project_source_record(raw, now=now)
        source_id = _text(projected.get("source_id"), 80)
        if not source_id:
            rejected_count += 1
            continue
        candidates.append(projected)

    # Tool completion order is not a source ordering guarantee. Sort the
    # bounded candidates before choosing canonical entries so sync/async and
    # restart projections select the same source when input order differs.
    candidates.sort(key=_entry_sort_key)
    for projected in candidates:
        source_id = _text(projected.get("source_id"), 80)
        key = source_dedupe_key(projected)
        prior = seen.get(key)
        if prior is not None:
            duplicates.append(
                {
                    "source_id": source_id,
                    "canonical_source_id": _text(prior.get("source_id"), 80),
                }
            )
            continue
        locator_key = _locator_key(projected)
        prior_locator = by_locator.get(locator_key) if locator_key else None
        current_hash = _text(projected.get("content_hash"), 128).lower()
        prior_hash = _text((prior_locator or {}).get("content_hash"), 128).lower()
        if (
            prior_locator is not None
            and current_hash
            and prior_hash
            and current_hash != prior_hash
        ):
            conflicts.append(
                {
                    "source_id": source_id,
                    "conflicting_source_id": _text(prior_locator.get("source_id"), 80),
                    "locator": _text(projected.get("locator"), 2048),
                }
            )
        if len(canonical) >= limit:
            rejected_count += 1
            continue
        seen[key] = projected
        if locator_key and prior_locator is None:
            by_locator[locator_key] = projected
        canonical.append(projected)

    status_counts = {status: 0 for status in sorted(SOURCE_QUALITY_STATUSES)}
    freshness_counts = {state: 0 for state in sorted(FRESHNESS_STATES)}
    completeness_counts = {state: 0 for state in ("complete", "partial", "unknown")}
    kinds: list[str] = []
    domains: list[str] = []
    for item in canonical:
        quality = normalize_source_quality(item.get("quality"))
        status = quality["status"]
        status_counts[status if status in status_counts else "unknown"] += 1
        freshness_state = quality["freshness"]["state"]
        freshness_counts[freshness_state if freshness_state in freshness_counts else "unknown"] += 1
        completeness = quality["completeness"]
        completeness_counts[completeness if completeness in completeness_counts else "unknown"] += 1
        kind = _text(item.get("kind"), 32) or "unknown"
        domain = _text(item.get("domain"), 255).lower().rstrip(".")
        if kind not in kinds:
            kinds.append(kind)
        if domain and domain not in domains:
            domains.append(domain)

    limitations: list[str] = []
    if duplicates:
        limitations.append("重复来源已合并，仅保留一个规范来源记录。")
    if conflicts:
        limitations.append("同一来源定位出现不同内容指纹，系统保留差异并未自动裁决。")
    if rejected_count:
        limitations.append("部分来源因缺少安全定位或超出数量上限未纳入汇总。")
    if freshness_counts["stale"]:
        limitations.append("部分来源已过期，相关结论需要结合更新时间判断。")
    if freshness_counts["unknown"]:
        limitations.append("部分来源缺少可用时间信息，无法判断新鲜度。")
    if status_counts["unavailable"]:
        limitations.append("部分来源不可用，汇总不代表完整来源范围。")
    if status_counts["partial"]:
        limitations.append("部分来源内容不完整，相关结论可能遗漏信息。")
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "available": bool(canonical),
        "entries": canonical,
        "unique_count": len(canonical),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates[:MAX_DUPLICATES],
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:MAX_CONFLICTS],
        "coverage": {
            "kinds": kinds[:8],
            "domains": domains[:16],
            "entry_count": len(canonical),
        },
        "quality_summary": {
            "status_counts": status_counts,
            "freshness_counts": freshness_counts,
            "completeness_counts": completeness_counts,
        },
        "limitations": _unique_text(limitations),
    }


def normalize_evidence_bundle(value: Any) -> dict[str, Any]:
    """Normalize a persisted Bundle into the same bounded public shape."""

    source = value if isinstance(value, Mapping) else {}
    raw_entries = source.get("entries")
    entries: list[dict[str, Any]] = []
    if isinstance(raw_entries, list):
        for raw in raw_entries[:MAX_BUNDLE_ENTRIES]:
            if not isinstance(raw, Mapping):
                continue
            item = _normalize_entry(raw)
            if item is not None:
                entries.append(item)
    coverage = source.get("coverage") if isinstance(source.get("coverage"), Mapping) else {}
    quality = source.get("quality_summary") if isinstance(source.get("quality_summary"), Mapping) else {}
    normalized = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "available": bool(source.get("available")) and bool(entries),
        "entries": entries,
        "unique_count": _bounded_count(source.get("unique_count"), len(entries)),
        "duplicate_count": _bounded_count(source.get("duplicate_count"), 0),
        "duplicates": _normalize_duplicates(source.get("duplicates")),
        "conflict_count": _bounded_count(source.get("conflict_count"), 0),
        "conflicts": _normalize_conflicts(source.get("conflicts")),
        "coverage": {
            "kinds": _unique_text(coverage.get("kinds"), 8),
            "domains": _unique_text(coverage.get("domains"), 16),
            "entry_count": _bounded_count(coverage.get("entry_count"), len(entries)),
        },
        "quality_summary": {
            "status_counts": _normalize_counts(quality.get("status_counts"), SOURCE_QUALITY_STATUSES),
            "freshness_counts": _normalize_counts(quality.get("freshness_counts"), FRESHNESS_STATES),
            "completeness_counts": _normalize_counts(
                quality.get("completeness_counts"), {"complete", "partial", "unknown"}
            ),
        },
        "limitations": _unique_text(source.get("limitations"), MAX_LIMITATIONS),
    }
    return normalized


def evidence_quality_limitations(value: Any) -> list[str]:
    """Return concise, user-facing caveats for a source bundle.

    This is intentionally a projection of declared counts and statuses. It
    does not judge whether a source is factually correct or choose between
    conflicting sources.
    """

    bundle = normalize_evidence_bundle(value)
    quality = bundle["quality_summary"]
    statuses = quality["status_counts"]
    freshness = quality["freshness_counts"]
    limitations = list(bundle.get("limitations") or [])
    additions = []
    if bundle.get("conflict_count"):
        additions.append("同一来源定位出现不同内容指纹，系统保留差异并未自动裁决。")
    if statuses.get("partial"):
        additions.append("部分来源内容不完整，相关结论可能遗漏信息。")
    if freshness.get("stale"):
        additions.append("部分来源可能已过期，相关结论不一定反映最新情况。")
    if freshness.get("unknown"):
        additions.append("部分来源缺少时间信息，无法判断是否最新。")
    if statuses.get("unavailable"):
        additions.append("部分来源当前不可用，结论未覆盖全部信息。")
    for item in additions:
        if item not in limitations:
            limitations.append(item)
    return _unique_text(limitations, MAX_LIMITATIONS)


def _normalize_entry(value: Mapping[str, Any]) -> dict[str, Any] | None:
    projected = project_source_record(value)
    source_id = _text(projected.get("source_id"), 80)
    locator, locator_kind = normalize_source_locator(projected.get("locator"))
    if not source_id or not locator:
        return None
    quality = normalize_source_quality(value.get("quality"))
    result: dict[str, Any] = {
        "schema_version": "spatial-agent.evidence-source-identity.v1",
        "source_id": source_id,
        "kind": _text(projected.get("kind"), 48) or "unknown",
        "locator": locator,
        "title": _text(projected.get("title"), 240) or "未命名来源",
        "domain": _text(projected.get("domain"), 255).lower().rstrip("."),
        "quality": quality,
    }
    for field in ("version", "content_hash", "retrieved_at", "published_at"):
        item = _text(projected.get(field), 2048 if field == "content_hash" else 96)
        if item:
            result[field] = item
    snippet = _text(projected.get("snippet"), 600)
    if snippet:
        result["snippet"] = snippet
    if result["kind"] == "web" and locator_kind == "web":
        result["url"] = locator
    return result


def _normalize_duplicates(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value[:MAX_DUPLICATES]:
        if not isinstance(item, Mapping):
            continue
        source_id = _text(item.get("source_id"), 80)
        canonical_id = _text(item.get("canonical_source_id"), 80)
        if source_id and canonical_id:
            result.append({"source_id": source_id, "canonical_source_id": canonical_id})
    return result


def _normalize_conflicts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value[:MAX_CONFLICTS]:
        if not isinstance(item, Mapping):
            continue
        source_id = _text(item.get("source_id"), 80)
        conflicting_id = _text(item.get("conflicting_source_id"), 80)
        locator, locator_kind = normalize_source_locator(item.get("locator"))
        if not locator or locator_kind == "unknown":
            continue
        if source_id and conflicting_id and locator:
            result.append(
                {
                    "source_id": source_id,
                    "conflicting_source_id": conflicting_id,
                    "locator": locator,
                }
            )
    return result


def _entry_sort_key(value: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(value.get(key), 2048).lower()
        for key in ("kind", "locator", "version", "content_hash", "source_id")
    )


def _locator_key(value: Mapping[str, Any]) -> str:
    return ":".join(
        (
            _text(value.get("kind"), 48).lower(),
            _text(value.get("locator"), 2048),
            _text(value.get("version"), 96),
        )
    )


def _normalize_counts(value: Any, allowed: set[str] | frozenset[str]) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    return {
        name: _bounded_count(source.get(name), 0)
        for name in sorted(allowed)
    }


def _bounded_limit(value: Any) -> int:
    try:
        return max(1, min(int(value), MAX_BUNDLE_ENTRIES))
    except (TypeError, ValueError):
        return MAX_BUNDLE_ENTRIES


def _bounded_count(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return max(0, min(default, MAX_BUNDLE_ENTRIES))
    return max(0, min(value, MAX_BUNDLE_ENTRIES))


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _unique_text(value: Any, limit: int = MAX_LIMITATIONS) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in values:
        text = _text(item, 320)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


__all__ = [
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "MAX_BUNDLE_ENTRIES",
    "MAX_CONFLICTS",
    "build_evidence_bundle",
    "evidence_quality_limitations",
    "normalize_evidence_bundle",
]
