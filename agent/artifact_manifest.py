"""Bounded, portable discovery metadata for persisted run artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional

from agent.artifact_reference import build_artifact_reference, normalize_artifact_reference
from agent.conversation_turn import normalize_conversation_turn


ARTIFACT_MANIFEST_SCHEMA_VERSION = "spatial-agent.artifact-manifest.v1"


def build_artifact_manifest(
    payload: Any,
    *,
    artifact_ref: Any = None,
    max_entries: int = 16,
) -> Dict[str, Any]:
    """Describe available artifact sections without returning their content."""

    if not isinstance(payload, Mapping):
        return unavailable_artifact_manifest("artifact_payload_missing")
    try:
        limit = max(1, min(int(max_entries), 32))
    except (TypeError, ValueError):
        limit = 16
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    run_reference = build_artifact_reference(
        artifact_ref or payload.get("artifact_ref"),
        kind="run",
        domain_id=payload.get("domain_id"),
    )
    geometry = result.get("geometry") if isinstance(result, Mapping) else {}
    geometry = geometry if isinstance(geometry, Mapping) else {}
    geometry_reference = geometry.get("reference")
    if geometry_reference is None:
        artifacts = result.get("artifacts")
        geometry_reference = artifacts.get("geometry") if isinstance(artifacts, Mapping) else None
    geojson_reference = normalize_artifact_reference(geometry_reference)
    if not geojson_reference.get("available"):
        geojson_reference = build_artifact_reference(
            payload.get("geojson_ref"),
            kind="geojson",
            status=geometry.get("status") or "unavailable",
            truncated=bool(geometry.get("truncated")),
            geometry_status=geometry.get("status"),
            domain_id=payload.get("domain_id"),
        )
    artifact_name = run_reference.get("ref")
    evidence_available = bool(
        payload.get("evidence_registry")
        or result.get("evidence_registry")
        or payload.get("async_result_evidence")
    )
    entries = [
        _entry("result", bool(result), "application/json", run_reference),
        _entry(
            "evidence",
            evidence_available,
            "application/json",
            _evidence_reference(artifact_name, payload.get("domain_id")),
        ),
        _entry(
            "geometry",
            bool(geojson_reference.get("available")),
            "application/geo+json",
            geojson_reference,
        ),
        {
            "id": "trace",
            "available": bool(payload.get("trace_summary")),
            "media_type": "application/json",
            "mode": "inline_summary",
            "count": min(len(payload.get("trace_summary") or []), 128)
            if isinstance(payload.get("trace_summary"), list)
            else 0,
        },
        {
            "id": "conversation_turn",
            "available": normalize_conversation_turn(
                payload.get("conversation_turn") or result.get("conversation_turn")
            ).get("available", False),
            "media_type": "application/json",
            "mode": "inline_summary",
        },
    ]
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "available": True,
        "kind": "run",
        "run_id": str(payload.get("run_id") or "")[:128] or None,
        "domain_id": str(payload.get("domain_id") or "unknown")[:80],
        "status": str(payload.get("status") or "UNKNOWN")[:32],
        "result_type": str(
            payload.get("result_type") or result.get("type") or "unknown"
        )[:96],
        "artifact": run_reference,
        "entries": entries[:limit],
        "mode": "on_demand",
        "max_entries": limit,
    }


def normalize_artifact_manifest(value: Any) -> Dict[str, Any]:
    """Keep a manifest safe when it crosses an artifact or HTTP boundary."""

    if not isinstance(value, Mapping):
        return unavailable_artifact_manifest("artifact_manifest_missing")
    if value.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION:
        return unavailable_artifact_manifest("artifact_manifest_unknown_schema")
    entries = []
    raw_entries = value.get("entries") if isinstance(value.get("entries"), list) else []
    for item in raw_entries[:32]:
        if not isinstance(item, Mapping) or not item.get("id"):
            continue
        entry = {
            "id": str(item.get("id"))[:64],
            "available": bool(item.get("available")),
            "media_type": str(item.get("media_type") or "application/json")[:96],
            "mode": str(item.get("mode") or "on_demand")[:32],
        }
        if item.get("count") is not None:
            try:
                entry["count"] = max(0, min(int(item.get("count")), 128))
            except (TypeError, ValueError):
                pass
        if isinstance(item.get("reference"), Mapping):
            entry["reference"] = normalize_artifact_reference(item["reference"])
        if isinstance(item.get("access"), Mapping):
            path = item["access"].get("path")
            if isinstance(path, str) and path.startswith("/artifacts/") and ".." not in path:
                entry["access"] = {
                    "transport": "http",
                    "method": "GET",
                    "path": path[:240],
                }
        entries.append(entry)
    try:
        max_entries = max(1, min(int(value.get("max_entries") or 16), 32))
    except (TypeError, ValueError):
        max_entries = 16
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "available": bool(value.get("available")),
        "kind": str(value.get("kind") or "run")[:32],
        "run_id": str(value.get("run_id") or "")[:128] or None,
        "domain_id": str(value.get("domain_id") or "unknown")[:80],
        "status": str(value.get("status") or "UNKNOWN")[:32],
        "result_type": str(value.get("result_type") or "unknown")[:96],
        "artifact": normalize_artifact_reference(value.get("artifact")),
        "entries": entries[:max_entries],
        "mode": "on_demand",
        "max_entries": max_entries,
    }


def unavailable_artifact_manifest(reason_code: str) -> Dict[str, Any]:
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "available": False,
        "kind": "run",
        "artifact": build_artifact_reference(None, kind="run"),
        "entries": [],
        "mode": "on_demand",
        "reason_code": str(reason_code or "artifact_manifest_unavailable")[:96],
    }


def _entry(
    entry_id: str,
    available: bool,
    media_type: str,
    reference: Mapping[str, Any],
) -> Dict[str, Any]:
    result = {
        "id": entry_id,
        "available": bool(available),
        "media_type": media_type,
        "mode": "on_demand",
        "reference": dict(reference),
    }
    access = reference.get("access") if isinstance(reference, Mapping) else None
    if isinstance(access, Mapping):
        result["access"] = dict(access)
    return result


def _evidence_reference(
    artifact_name: Optional[str], domain_id: Optional[str] = None
) -> Dict[str, Any]:
    reference = build_artifact_reference(
        artifact_name, kind="run", domain_id=domain_id
    )
    access = reference.get("access")
    if isinstance(access, dict):
        reference["access"] = dict(access)
        reference["access"]["path"] = str(access.get("path")) + "/evidence"
    reference["representation"] = "evidence_projection"
    return reference


__all__ = [
    "ARTIFACT_MANIFEST_SCHEMA_VERSION",
    "build_artifact_manifest",
    "normalize_artifact_manifest",
    "unavailable_artifact_manifest",
]
