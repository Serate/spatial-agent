"""Domain-neutral evidence projection for composed workflow components.

Each Domain owns the observations.  This module only gives composition a
bounded, versioned shape for readiness, coverage, freshness, provenance,
conflicts and revalidation so the same selection/evidence contract can be
replayed by HTTP, async, SQLite and artifact consumers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .evidence_contract import normalize_capability_evidence
from .evidence_revalidation import normalize_evidence_revalidation


WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION = (
    "spatial-agent.workflow-component-evidence.v1"
)
_MAX_COMPONENTS = 8
_MAX_TEXT = 96
_FRESHNESS_STATES = {"current", "stale", "expired", "unknown", "not_applicable"}
_CONFLICT_STATES = {"none", "detected", "resolved", "unknown"}


def project_workflow_component_evidence(value: Any) -> dict[str, Any]:
    """Project component-owned evidence without copying constraints or data."""

    source = value if isinstance(value, Mapping) else {}
    raw_components = source.get("components")
    raw_components = raw_components if isinstance(raw_components, (list, tuple)) else []
    components = []
    for index, item in enumerate(raw_components[:_MAX_COMPONENTS]):
        if not isinstance(item, Mapping):
            continue
        component_id = _text(item.get("component_id") or f"component-{index + 1}")
        template_id = _text(item.get("template_id"))
        if not component_id or not template_id:
            continue
        evidence_source = item.get("evidence_summary") or item.get("evidence_state")
        if isinstance(evidence_source, Mapping):
            evidence_source = dict(evidence_source)
            for key in ("freshness", "freshness_status", "conflicts", "conflict", "evidence_revalidation"):
                if key in item and key not in evidence_source:
                    evidence_source[key] = item.get(key)
        evidence = normalize_component_evidence(evidence_source)
        components.append(
            {
                "component_id": component_id,
                "template_id": template_id,
                "template_version": _text(item.get("template_version")) or "1.0.0",
                "depends_on_components": _strings(
                    item.get("depends_on_components") or item.get("depends_on")
                ),
                **evidence,
            }
        )

    counts = {state: 0 for state in ("ready", "degraded", "unavailable", "unknown", "blocked")}
    freshness_counts = {state: 0 for state in _FRESHNESS_STATES}
    conflict_counts = {state: 0 for state in _CONFLICT_STATES}
    for item in components:
        state = item.get("state") if item.get("state") in counts else "unknown"
        counts[state] += 1
        freshness = item.get("freshness") or {}
        freshness_state = freshness.get("status") if isinstance(freshness, Mapping) else "unknown"
        freshness_counts[freshness_state if freshness_state in freshness_counts else "unknown"] += 1
        conflicts = item.get("conflicts") or {}
        conflict_state = conflicts.get("status") if isinstance(conflicts, Mapping) else "unknown"
        conflict_counts[conflict_state if conflict_state in conflict_counts else "unknown"] += 1

    canonical = {
        "schema_version": WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION,
        "components": components,
        "summary": {
            "component_count": len(components),
            "state_counts": counts,
            "freshness_counts": freshness_counts,
            "conflict_counts": conflict_counts,
            "all_ready": bool(components) and counts["ready"] == len(components),
        },
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **canonical,
        "available": bool(components),
        "fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def normalize_component_evidence(value: Any) -> dict[str, Any]:
    """Normalize one component's evidence and preserve safe quality dimensions."""

    source = value if isinstance(value, Mapping) else {}
    capability = normalize_capability_evidence(source)
    freshness = _normalize_freshness(source.get("freshness") or source.get("freshness_status"))
    conflicts = _normalize_conflicts(source.get("conflicts") or source.get("conflict"))
    revalidation = normalize_evidence_revalidation(source.get("evidence_revalidation"))
    if revalidation is not None and revalidation.get("state") == "blocked":
        state = "blocked"
    elif capability.get("status") == "unavailable":
        state = "unavailable"
    elif (
        capability.get("status") == "degraded"
        or freshness.get("status") in {"stale", "expired"}
        or conflicts.get("status") == "detected"
    ):
        state = "degraded"
    elif capability.get("status") == "ready":
        state = "ready"
    else:
        state = "unknown"
    result = {
        "state": state,
        "evidence_summary": capability,
        "freshness": freshness,
        "conflicts": conflicts,
    }
    if revalidation is not None:
        result["evidence_revalidation"] = revalidation
    return result


def normalize_workflow_component_evidence(value: Any) -> dict[str, Any]:
    """Normalize persisted composed evidence while rejecting unknown schemas."""

    if not isinstance(value, Mapping):
        return project_workflow_component_evidence({})
    if value.get("schema_version") != WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION:
        return project_workflow_component_evidence({})
    projected = project_workflow_component_evidence(value)
    if value.get("fingerprint") and value.get("fingerprint") != projected.get("fingerprint"):
        projected["available"] = False
        projected["reason_code"] = "workflow_component_evidence_fingerprint_mismatch"
    return projected


def _normalize_freshness(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {"status": value}
    status = _text(source.get("status") or source.get("state")) or "unknown"
    if status in {"ready", "valid", "fresh"}:
        status = "current"
    if status not in _FRESHNESS_STATES:
        status = "unknown"
    result = {"status": status}
    for key in ("observed_at", "expires_at", "version"):
        if source.get(key) is not None:
            result[key] = _text(source.get(key), 64)
    for key in ("age_seconds", "max_age_seconds"):
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = max(0, min(float(value), 31536000))
    return result


def _normalize_conflicts(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {"status": value}
    status = _text(source.get("status") or source.get("state")) or "unknown"
    if status in {"ready", "clear", "no_conflict"}:
        status = "none"
    if status not in _CONFLICT_STATES:
        status = "unknown"
    result = {"status": status}
    count = source.get("count")
    if isinstance(count, int) and not isinstance(count, bool):
        result["count"] = max(0, min(count, 128))
    reasons = _strings(source.get("reason_codes") or source.get("reasons"))
    if reasons:
        result["reason_codes"] = reasons
    return result


def _text(value: Any, limit: int = _MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        text = _text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= 8:
            break
    return result


__all__ = [
    "WORKFLOW_COMPONENT_EVIDENCE_SCHEMA_VERSION",
    "normalize_component_evidence",
    "normalize_workflow_component_evidence",
    "project_workflow_component_evidence",
]
