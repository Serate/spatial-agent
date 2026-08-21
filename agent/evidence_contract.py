"""Versioned, domain-neutral metadata for evidence projections.

The payload of runtime/release evidence remains owned by a Domain Pack. This
Module only adds the small, stable envelope that callers need to identify the
kind, owner and status of that projection without understanding GIS fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


DOMAIN_EVIDENCE_SCHEMA_VERSION = "spatial-agent.domain-evidence.v1"
CAPABILITY_EVIDENCE_SCHEMA_VERSION = "spatial-agent.capability-evidence.v1"
EVIDENCE_KINDS = frozenset({"runtime", "release"})
CAPABILITY_EVIDENCE_STATUSES = frozenset(
    {"ready", "degraded", "unavailable", "unknown", "not_applicable"}
)


class EvidenceProvider(Protocol):
    """Minimal provider seam owned by a Domain Pack."""

    domain_id: str

    def snapshot(
        self,
        kind: str,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Return one bounded runtime or release evidence projection."""


def attach_evidence_contract(
    value: Mapping[str, Any],
    *,
    domain_id: str,
    kind: str,
) -> dict[str, Any]:
    """Return a bounded flat projection plus a versioned evidence contract."""
    normalized_kind = str(kind or "unknown")[:24]
    if normalized_kind not in EVIDENCE_KINDS:
        raise ValueError("unsupported evidence kind: " + normalized_kind)
    payload = dict(value)
    existing = payload.get("evidence_contract")
    if isinstance(existing, Mapping):
        contract = dict(existing)
    else:
        contract = {}
    status = _status_for(payload, normalized_kind)
    updated_at = (
        payload.get("updated_at")
        or payload.get("generated_at")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    payload["evidence_contract"] = {
        "schema_version": DOMAIN_EVIDENCE_SCHEMA_VERSION,
        "kind": normalized_kind,
        "domain_id": str(domain_id or "unknown")[:80],
        "status": str(contract.get("status") or status)[:32],
        "updated_at": str(contract.get("updated_at") or updated_at)[:64],
    }
    return payload


def _status_for(payload: Mapping[str, Any], kind: str) -> str:
    if kind == "runtime":
        return str(
            payload.get("health_status")
            or payload.get("data_readiness")
            or "unknown"
        )[:32]
    return str(payload.get("status") or payload.get("data_readiness") or "unknown")[:32]


def build_capability_evidence(
    capability: Mapping[str, Any] | None = None,
    *,
    runtime_evidence: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project capability data quality into a small domain-neutral summary.

    Domain Packs own the raw dataset/readiness/provenance evidence. The
    selection contract only carries statuses, counts and bounded reasons so a
    candidate card can explain availability without exposing paths or large
    geometry/data reports.
    """

    source = capability if isinstance(capability, Mapping) else {}
    runtime = runtime_evidence or source.get("runtime_evidence") or {}
    runtime = runtime if isinstance(runtime, Mapping) else {}
    datasets = runtime.get("datasets")
    datasets = datasets if isinstance(datasets, Mapping) else {}
    raw_statuses = [
        _safe_status(source.get("capability_status")),
        _safe_status(source.get("dataset_gate")),
        _safe_status(runtime.get("status")),
        _safe_status(runtime.get("data_readiness")),
    ]
    availability_mode = _safe_availability_mode(source.get("availability_mode"))
    availability_reason = _bounded_text(
        source.get("availability_reason") or "unknown", 96
    )
    dataset_statuses = [
        _safe_status(item.get("status") or item.get("quality"))
        for item in datasets.values()
        if isinstance(item, Mapping)
    ]
    statuses = [item for item in raw_statuses + dataset_statuses if item != "unknown"]
    if availability_mode == "unavailable":
        status = "unavailable"
    elif "unavailable" in statuses or "missing" in statuses or source.get("available") is False:
        status = "unavailable"
    elif "degraded" in statuses or "warning" in statuses:
        status = "degraded"
    elif availability_mode == "demo":
        status = "degraded"
    elif statuses and all(item in {"ready", "aligned"} for item in statuses):
        status = "ready"
    elif source.get("available") is True and not statuses:
        status = "unknown"
    else:
        status = "unknown"
    missing = _bounded_strings(source.get("missing_datasets"))
    reasons = _bounded_strings(
        source.get("degradation_reasons") or runtime.get("reasons") or runtime.get("warnings")
    )
    for item in missing:
        reason = "缺少数据：" + item
        if reason not in reasons:
            reasons.append(reason)
    alignment = runtime.get("alignment") or runtime.get("grid_alignment")
    alignment_status = _safe_status(alignment.get("status") if isinstance(alignment, Mapping) else alignment)
    provenance_value = provenance or runtime.get("provenance") or {}
    provenance_status = (
        _safe_status(provenance_value.get("status"))
        if isinstance(provenance_value, Mapping)
        else "unknown"
    )
    return {
        "schema_version": CAPABILITY_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "availability": {
            "mode": availability_mode,
            "reason": availability_reason,
            "native_available": bool(source.get("native_available", False)),
            "demo_available": bool(source.get("demo_available", False)),
        },
        "readiness": {
            "status": _safe_status(
                runtime.get("data_readiness") or source.get("dataset_gate")
            ),
            "required": bool(source.get("datasets")),
        },
        "coverage": {
            "status": _safe_status(runtime.get("coverage_status")) if runtime.get("coverage_status") else "unknown",
            "dataset_count": len(datasets),
            "covered_dataset_count": sum(
                1
                for item in datasets.values()
                if isinstance(item, Mapping) and item.get("coverage")
            ),
        },
        "alignment": {"status": alignment_status},
        "provenance": {
            "status": provenance_status,
            "source_count": len(provenance_value) if isinstance(provenance_value, Mapping) else 0,
        },
        "missing_reasons": reasons[:8],
    }


def normalize_capability_evidence(value: Any) -> dict[str, Any]:
    """Normalize persisted capability evidence without trusting its shape."""

    source = value if isinstance(value, Mapping) else {}
    if source.get("schema_version") != CAPABILITY_EVIDENCE_SCHEMA_VERSION:
        return build_capability_evidence(
            {"available": False},
        )
    readiness = source.get("readiness") if isinstance(source.get("readiness"), Mapping) else {}
    coverage = source.get("coverage") if isinstance(source.get("coverage"), Mapping) else {}
    alignment = source.get("alignment") if isinstance(source.get("alignment"), Mapping) else {}
    provenance = source.get("provenance") if isinstance(source.get("provenance"), Mapping) else {}
    status = _safe_status(source.get("status"))
    availability = source.get("availability") if isinstance(source.get("availability"), Mapping) else {}
    return {
        "schema_version": CAPABILITY_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "availability": {
            "mode": _safe_availability_mode(availability.get("mode")),
            "reason": _bounded_text(availability.get("reason") or "unknown", 96),
            "native_available": bool(availability.get("native_available", False)),
            "demo_available": bool(availability.get("demo_available", False)),
        },
        "readiness": {
            "status": _safe_status(readiness.get("status")),
            "required": bool(readiness.get("required", False)),
        },
        "coverage": {
            "status": _safe_status(coverage.get("status")),
            "dataset_count": _bounded_count(coverage.get("dataset_count")),
            "covered_dataset_count": _bounded_count(coverage.get("covered_dataset_count")),
        },
        "alignment": {"status": _safe_status(alignment.get("status"))},
        "provenance": {
            "status": _safe_status(provenance.get("status")),
            "source_count": _bounded_count(provenance.get("source_count")),
        },
        "missing_reasons": _bounded_strings(source.get("missing_reasons"))[:8],
    }


def _safe_status(value: Any) -> str:
    value = str(value or "unknown").strip().lower()[:32]
    value = {
        "missing": "unavailable",
        "not_ready": "unavailable",
        "warning": "degraded",
    }.get(value, value)
    return value if value in CAPABILITY_EVIDENCE_STATUSES else "unknown"


def _safe_availability_mode(value: Any) -> str:
    value = str(value or "unknown").strip().lower()[:24]
    return value if value in {"native", "demo", "unavailable", "unknown"} else "unknown"


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit] or "unknown"


def _bounded_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()[:160]
        if text and text not in result:
            result.append(text)
        if len(result) >= 16:
            break
    return result


def _bounded_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(value, 64))


__all__ = [
    "DOMAIN_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_EVIDENCE_SCHEMA_VERSION",
    "CAPABILITY_EVIDENCE_STATUSES",
    "EVIDENCE_KINDS",
    "EvidenceProvider",
    "attach_evidence_contract",
    "build_capability_evidence",
    "normalize_capability_evidence",
]
