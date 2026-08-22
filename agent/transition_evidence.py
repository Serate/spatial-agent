"""Bounded data-evidence transition projection for recovery actions.

Selection and fact-provision actions may change the data evidence available to
the next plan.  This module records only safe, versioned summaries of the
readiness/coverage/alignment/provenance fields already present in a result;
it never copies raw dataset records, local paths, request text, or provider
responses.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


TRANSITION_EVIDENCE_SCHEMA_VERSION = "spatial-agent.action-transition-evidence.v1"
_FIELDS = ("readiness", "coverage", "alignment", "provenance")
_ALIASES = {
    "readiness": {
        "readiness",
        "data_readiness",
        "health_status",
        "analysis_ready_status",
    },
    "coverage": {"coverage", "coverage_status", "coverage_percent", "coverage_ratio"},
    "alignment": {"alignment", "grid_alignment", "alignment_status", "aligned"},
    "provenance": {
        "provenance",
        "source_binding",
        "output_manifest",
        "dataset_manifest",
    },
}
_SUMMARY_KEYS = (
    "value",
    "status",
    "state",
    "available",
    "ready",
    "aligned",
    "required",
    "verified",
    "fingerprint",
    "version",
    "binding_version",
    "derived_version",
    "verification_mode",
    "mismatch_count",
    "verified_files",
    "datasets",
    "dataset_count",
    "covered_dataset_count",
    "source_count",
    "source",
    "percent",
    "ratio",
    "metadata_only",
    "pixels_read",
)
_MAX_OBSERVATIONS = 8
_MAX_ITEMS = 8
_MAX_TEXT = 128
_MAX_DEPTH = 8
_MAX_NODES = 512


def project_transition_evidence(value: Any) -> dict[str, Any]:
    """Extract a safe, deterministic data-evidence summary from a payload."""

    payload = value if isinstance(value, Mapping) else {}
    fields: dict[str, list[dict[str, Any]]] = {field: [] for field in _FIELDS}
    node_count = [0]
    _collect(payload, fields, depth=0, node_count=node_count)
    fields = {
        field: _dedupe(items)[:_MAX_OBSERVATIONS]
        for field, items in fields.items()
        if items
    }
    canonical = {"schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION, "fields": fields}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **canonical,
        "available": bool(fields),
        "fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def build_transition_evidence(source: Any, result: Any) -> dict[str, Any]:
    """Compare source/result evidence without treating missing data as ready."""

    source_projection = _as_projection(source)
    result_projection = _as_projection(result)
    source_fields = source_projection.get("fields", {})
    result_fields = result_projection.get("fields", {})
    changes = []
    for field in _FIELDS:
        before = source_fields.get(field)
        after = result_fields.get(field)
        if before == after:
            continue
        if before is None:
            change = "added"
        elif after is None:
            change = "removed"
        else:
            change = "changed"
        changes.append({
            "field": field,
            "change": change,
            "before": before,
            "after": after,
        })
    if not source_projection.get("available") and not result_projection.get("available"):
        state = "unavailable"
    elif not changes:
        state = "unchanged"
    else:
        state = "changed"
    return {
        "schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": bool(source_projection.get("available") or result_projection.get("available")),
        "state": state,
        "source": source_projection,
        "result": result_projection,
        "changes": changes[: len(_FIELDS)],
    }


def normalize_transition_evidence(value: Any) -> dict[str, Any] | None:
    """Normalize persisted transition evidence and reject future schemas."""

    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != TRANSITION_EVIDENCE_SCHEMA_VERSION:
        return None
    source = _normalize_projection(value.get("source"))
    result = _normalize_projection(value.get("result"))
    if source is None or result is None:
        return None
    changes = []
    raw_changes = value.get("changes")
    if isinstance(raw_changes, list):
        for item in raw_changes[: len(_FIELDS)]:
            if not isinstance(item, Mapping):
                continue
            field = str(item.get("field") or "")
            if field not in _FIELDS:
                continue
            change = str(item.get("change") or "")
            if change not in {"added", "removed", "changed"}:
                continue
            changes.append({
                "field": field,
                "change": change,
                "before": _normalize_field(item.get("before")),
                "after": _normalize_field(item.get("after")),
            })
    state = str(value.get("state") or "unavailable")
    if state not in {"unavailable", "unchanged", "changed"}:
        state = "unavailable"
    return {
        "schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value.get("available")) and bool(
            source.get("available") or result.get("available")
        ),
        "state": state,
        "source": source,
        "result": result,
        "changes": changes,
    }


def _as_projection(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("schema_version") == TRANSITION_EVIDENCE_SCHEMA_VERSION:
        normalized = _normalize_projection_payload(value)
        if normalized is not None:
            return normalized
    return project_transition_evidence(value)


def _normalize_projection_payload(value: Mapping[str, Any]) -> dict[str, Any] | None:
    fields = _normalize_fields(value.get("fields"))
    if fields is None:
        return None
    return {
        "schema_version": TRANSITION_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value.get("available")) and bool(fields),
        "fingerprint": str(value.get("fingerprint") or "")[:96],
        "fields": fields,
    }


def _normalize_projection(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != TRANSITION_EVIDENCE_SCHEMA_VERSION:
        return None
    return _normalize_projection_payload(value)


def _normalize_fields(value: Any) -> dict[str, list[dict[str, Any]]] | None:
    if not isinstance(value, Mapping):
        return None
    fields: dict[str, list[dict[str, Any]]] = {}
    for field in _FIELDS:
        raw = value.get(field)
        if not isinstance(raw, list):
            continue
        normalized = []
        for item in raw[:_MAX_OBSERVATIONS]:
            if isinstance(item, Mapping):
                safe = _normalize_field(item)
                if isinstance(safe, Mapping):
                    normalized.append(dict(safe))
        if normalized:
            fields[field] = _dedupe(normalized)[:_MAX_OBSERVATIONS]
    return fields


def _normalize_field(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in _SUMMARY_KEYS:
        if key not in value:
            continue
        item = value.get(key)
        if isinstance(item, bool):
            result[key] = item
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            result[key] = item
        elif isinstance(item, str) and item.strip():
            result[key] = item.strip()[:_MAX_TEXT]
        elif isinstance(item, list):
            safe_items = [
                str(entry)[:_MAX_TEXT]
                for entry in item[:_MAX_ITEMS]
                if isinstance(entry, (str, int, float)) and not isinstance(entry, bool)
            ]
            if safe_items:
                result[key] = safe_items
    return result or None


def _collect(
    value: Any,
    fields: dict[str, list[dict[str, Any]]],
    *,
    depth: int,
    node_count: list[int],
) -> None:
    if depth > _MAX_DEPTH or node_count[0] >= _MAX_NODES:
        return
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            node_count[0] += 1
            key = str(raw_key or "").strip().lower()
            for field, aliases in _ALIASES.items():
                if key in aliases:
                    normalized = _normalize_observation(item)
                    if normalized is not None and len(fields[field]) < _MAX_OBSERVATIONS:
                        fields[field].append(normalized)
                    break
            if isinstance(item, (Mapping, list, tuple)):
                _collect(item, fields, depth=depth + 1, node_count=node_count)
    elif isinstance(value, (list, tuple)):
        for item in value[:_MAX_ITEMS]:
            _collect(item, fields, depth=depth + 1, node_count=node_count)


def _normalize_observation(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return _normalize_field(value)
    if isinstance(value, bool):
        return {"value": value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"value": value}
    if isinstance(value, str) and value.strip():
        return {"value": value.strip()[:_MAX_TEXT]}
    return None


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


__all__ = [
    "TRANSITION_EVIDENCE_SCHEMA_VERSION",
    "build_transition_evidence",
    "normalize_transition_evidence",
    "project_transition_evidence",
]
