"""Domain-neutral registry for public evidence projections.

The registry is an index, not a new source of truth. It names the bounded
evidence projections already owned by the result, lifecycle, and timeline
seams and gives every consumer the same JSON location and schema version.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_lifecycle import ACTION_LIFECYCLE_SCHEMA_VERSION, project_action_lifecycle
from .contract_versions import RESULT_ENVELOPE_SCHEMA_VERSION
from .execution_timeline import EXECUTION_TIMELINE_SCHEMA_VERSION, normalize_execution_timeline
from .plan_quality import PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION, project_plan_quality_evidence


EVIDENCE_REGISTRY_SCHEMA_VERSION = "spatial-agent.evidence-registry.v1"
REPLANNING_SCHEMA_VERSION = "spatial-agent.replanning.v1"
_MAX_ENTRIES = 12
_MAX_TEXT = 96
_KNOWN_SCHEMA_VERSIONS = {
    RESULT_ENVELOPE_SCHEMA_VERSION,
    PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION,
    EXECUTION_TIMELINE_SCHEMA_VERSION,
    ACTION_LIFECYCLE_SCHEMA_VERSION,
    REPLANNING_SCHEMA_VERSION,
}


def build_evidence_registry(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build one bounded catalogue of evidence available for a result."""

    source = payload if isinstance(payload, Mapping) else {}
    result = source.get("result") if isinstance(source.get("result"), Mapping) else {}
    planning = result.get("planning") if isinstance(result.get("planning"), Mapping) else {}
    quality = project_plan_quality_evidence(planning.get("plan_quality"))
    timeline = normalize_execution_timeline(result.get("execution_timeline"))
    lifecycle = result.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        lifecycle = project_action_lifecycle({"status": source.get("status")})
    replanning = result.get("replanning") if isinstance(result.get("replanning"), Mapping) else {}
    events = replanning.get("events") if isinstance(replanning.get("events"), list) else []
    entries = [
        _entry("result", RESULT_ENVELOPE_SCHEMA_VERSION, bool(result), "available" if result else "unavailable", "result"),
        _entry("plan_quality", PLAN_QUALITY_EVIDENCE_SCHEMA_VERSION, quality["available"], quality["state"], "result.planning.plan_quality"),
        _entry("execution_timeline", EXECUTION_TIMELINE_SCHEMA_VERSION, timeline["available"], "available" if timeline["available"] else "unavailable", "result.execution_timeline"),
        _entry("action_lifecycle", ACTION_LIFECYCLE_SCHEMA_VERSION, bool(lifecycle), str(lifecycle.get("state") or "unknown"), "result.lifecycle"),
        _entry("replanning", REPLANNING_SCHEMA_VERSION, bool(events), "available" if events else "none", "result.replanning", count=len(events)),
    ][: _MAX_ENTRIES]
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": bool(result),
        "entry_count": len(entries),
        "entries": entries,
    }


def normalize_evidence_registry(value: Any) -> dict[str, Any]:
    """Normalize persisted registry data without trusting arbitrary entries."""

    if not isinstance(value, Mapping):
        return _unavailable("evidence_registry_missing")
    if value.get("schema_version") != EVIDENCE_REGISTRY_SCHEMA_VERSION:
        return _unavailable("evidence_registry_unknown_schema")
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        return _unavailable("evidence_registry_entries_invalid")
    entries = []
    for item in raw_entries[:_MAX_ENTRIES]:
        if not isinstance(item, Mapping):
            continue
        entry_id = _text(item.get("id"))
        schema_version = _text(item.get("schema_version"))
        reference = _text(item.get("reference"))
        if not entry_id or not schema_version or not reference:
            continue
        if schema_version not in _KNOWN_SCHEMA_VERSIONS:
            return _unavailable("evidence_registry_unknown_entry_schema")
        if reference != "result" and not reference.startswith("result."):
            return _unavailable("evidence_registry_reference_invalid")
        normalized = {
            "id": entry_id,
            "schema_version": schema_version,
            "available": bool(item.get("available")),
            "state": _text(item.get("state")) or "unknown",
            "reference": reference,
        }
        count = item.get("count")
        if isinstance(count, int) and not isinstance(count, bool):
            normalized["count"] = max(0, min(count, 128))
        entries.append(normalized)
    if not entries:
        return _unavailable("evidence_registry_entries_missing")
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "entry_count": len(entries),
        "entries": entries,
    }


def _entry(entry_id: str, schema_version: str, available: bool, state: str, reference: str, *, count: int | None = None) -> dict[str, Any]:
    result = {
        "id": entry_id[:_MAX_TEXT],
        "schema_version": schema_version[:_MAX_TEXT],
        "available": bool(available),
        "state": str(state or "unknown")[:_MAX_TEXT],
        "reference": reference[:_MAX_TEXT],
    }
    if count is not None:
        result["count"] = max(0, min(int(count), 128))
    return result


def _unavailable(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "available": False,
        "entry_count": 0,
        "entries": [],
        "reason_code": _text(reason_code),
    }


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


__all__ = ["EVIDENCE_REGISTRY_SCHEMA_VERSION", "build_evidence_registry", "normalize_evidence_registry"]
