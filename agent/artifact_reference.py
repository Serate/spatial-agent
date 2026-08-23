"""Portable, bounded references for persisted run and geometry artifacts.

The runtime keeps legacy ``artifact_ref``/``geojson_ref`` strings for
compatibility, but public result consumers should use this small structured
reference.  It contains only a safe artifact name and a transport-neutral
HTTP access hint; host filesystem paths never cross this seam.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, Optional

from agent.contract_versions import ARTIFACT_REFERENCE_SCHEMA_VERSION

_KINDS = {
    "run": ("runs", ".json", "application/json", "run_snapshot"),
    "action": ("actions", ".json", "application/json", "action_snapshot"),
    "geojson": (
        "geojson",
        ".geojson",
        "application/geo+json",
        "bounded_geometry_summary",
    ),
}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_SAFE_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def build_artifact_reference(
    ref: Any,
    *,
    kind: str,
    status: str = "available",
    truncated: bool = False,
    representation: Optional[str] = None,
    geometry_status: Optional[str] = None,
    domain_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a bounded reference without exposing a host filesystem path."""

    spec = _KINDS.get(str(kind or ""))
    normalized_kind = str(kind or "unknown")[:32]
    if spec is None:
        return _unavailable(normalized_kind, "artifact_kind_unknown")
    route, suffix, media_type, default_representation = spec
    name = _safe_name(ref, suffix)
    result: Dict[str, Any] = {
        "schema_version": ARTIFACT_REFERENCE_SCHEMA_VERSION,
        "available": bool(name),
        "kind": normalized_kind,
        "ref": name,
        "media_type": media_type,
        "representation": str(representation or default_representation)[:64],
        "mode": "on_demand",
        "status": str(status or ("available" if name else "unavailable"))[:32],
        "truncated": bool(truncated),
    }
    if name:
        selected_domain = _safe_domain_id(domain_id)
        if selected_domain:
            result["domain_id"] = selected_domain
        result["access"] = {
            "transport": "http",
            "method": "GET",
            "path": (
                f"/domains/{selected_domain}/artifacts/{route}/{name}"
                if selected_domain
                else f"/artifacts/{route}/{name}"
            ),
        }
    else:
        result["status"] = "unavailable"
        result["reason_code"] = "artifact_ref_missing"
    if geometry_status:
        result["geometry_status"] = str(geometry_status)[:32]
    return result


def normalize_artifact_reference(value: Any) -> Dict[str, Any]:
    """Normalize a persisted reference and rebuild its safe access hint."""

    if not isinstance(value, Mapping):
        return _unavailable("unknown", "artifact_reference_missing")
    if value.get("schema_version") not in (None, ARTIFACT_REFERENCE_SCHEMA_VERSION):
        return _unavailable("unknown", "artifact_reference_unknown_schema")
    kind = str(value.get("kind") or "")
    if kind not in _KINDS:
        return _unavailable(kind[:32] or "unknown", "artifact_kind_unknown")
    raw_ref = value.get("ref")
    if isinstance(raw_ref, str) and ("/" in raw_ref or "\\" in raw_ref):
        return _unavailable(kind, "artifact_ref_not_portable")
    result = build_artifact_reference(
        raw_ref,
        kind=kind,
        status=value.get("status") or "available",
        truncated=bool(value.get("truncated")),
        representation=value.get("representation"),
        geometry_status=value.get("geometry_status"),
        domain_id=value.get("domain_id"),
    )
    if value.get("available") is False:
        result["available"] = False
        result.pop("access", None)
        result["status"] = "unavailable"
    return result


def _safe_name(ref: Any, suffix: str) -> Optional[str]:
    if not ref:
        return None
    value = str(ref).replace("\\", "/").rsplit("/", 1)[-1]
    if (
        not value
        or value in {".", ".."}
        or not _SAFE_NAME.fullmatch(value)
        or not value.endswith(suffix)
    ):
        return None
    return value


def _safe_domain_id(value: Any) -> Optional[str]:
    candidate = str(value or "").strip().lower()
    return candidate if _SAFE_DOMAIN_ID.fullmatch(candidate) else None


def _unavailable(kind: str, reason_code: str) -> Dict[str, Any]:
    return {
        "schema_version": ARTIFACT_REFERENCE_SCHEMA_VERSION,
        "available": False,
        "kind": str(kind or "unknown")[:32],
        "ref": None,
        "media_type": None,
        "representation": "unknown",
        "mode": "on_demand",
        "status": "unavailable",
        "truncated": False,
        "reason_code": str(reason_code or "artifact_reference_unavailable")[:96],
    }


__all__ = [
    "ARTIFACT_REFERENCE_SCHEMA_VERSION",
    "build_artifact_reference",
    "normalize_artifact_reference",
]
