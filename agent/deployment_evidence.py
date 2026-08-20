"""Domain-neutral deployment evidence projection.

This module joins already bounded Runtime, data, model and degradation
evidence.  It never reads a dataset or provider response and never copies
filesystem paths, request text or credentials.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contract_versions import MODEL_EVIDENCE_SCHEMA_VERSION
from .runtime_context import normalize_runtime_context


DEPLOYMENT_EVIDENCE_SCHEMA_VERSION = "spatial-agent.deployment-evidence.v1"
_EXECUTION_MODES = {"rule", "offline_replay", "live_model"}


def build_deployment_evidence(
    payload: Mapping[str, Any],
    *,
    model_evidence: Mapping[str, Any] | None = None,
    degradation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded projection that can be compared across deployments."""

    payload = payload if isinstance(payload, Mapping) else {}
    context = normalize_runtime_context(payload.get("runtime_context"))
    runtime_evidence = _mapping(payload.get("runtime_evidence"))
    release_evidence = _mapping(payload.get("release_evidence"))
    data = {
        "observed": bool(runtime_evidence or release_evidence),
        "runtime_status": _status(runtime_evidence, "health_status"),
        "runtime_readiness": _status(runtime_evidence, "data_readiness"),
        "release_status": _status(release_evidence, "status"),
        "manifest": _manifest_summary(
            release_evidence.get("manifest") or runtime_evidence.get("manifest")
        ),
        "source_binding": _status_summary(release_evidence.get("source_binding")),
        "output_manifest": _status_summary(release_evidence.get("output_manifest")),
    }
    degradation = degradation if isinstance(degradation, Mapping) else {}
    degradation_summary = {
        "status": str(degradation.get("status") or "none")[:24],
        "item_count": _bounded_int(degradation.get("item_count"), 0, 40),
    }
    model = _model_summary(model_evidence)
    context_fingerprint = context.get("fingerprint") if context else ""
    status = _aggregate_status(data, degradation_summary, context)
    result = {
        "schema_version": DEPLOYMENT_EVIDENCE_SCHEMA_VERSION,
        "available": bool(
            context
            or data["observed"]
            or model.get("available")
            or model.get("provider")
            or model.get("model")
            or model.get("fixture_id")
        ),
        "status": status,
        "domain_id": str(context.get("domain_id") if context else payload.get("domain_id") or "unknown")[:80],
        "context_fingerprint": str(context_fingerprint or "")[:80],
        "data": data,
        "model": model,
        "degradation": degradation_summary,
    }
    return result


def _aggregate_status(
    data: Mapping[str, Any],
    degradation: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> str:
    statuses = [
        data.get("runtime_status"),
        data.get("runtime_readiness"),
        data.get("release_status"),
        degradation.get("status"),
    ]
    if any(value == "unavailable" for value in statuses):
        return "unavailable"
    if any(value in {"degraded", "warning"} for value in statuses):
        return "degraded"
    if any(value in {"ready", "not_applicable", "not_configured"} for value in statuses):
        return "ready"
    return "context_only" if context else "unknown"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _status(value: Mapping[str, Any], key: str) -> str:
    if not value:
        return "not_observed"
    return str(value.get(key) or value.get("status") or "unknown")[:24]


def _status_summary(value: Any) -> dict[str, Any]:
    item = _mapping(value)
    return {
        "status": str(item.get("status") or "not_observed")[:24],
        "verification_mode": str(item.get("verification_mode") or "unknown")[:24],
        "hashes_verified": bool(item.get("hashes_verified", False)),
        "mismatch_count": _bounded_int(item.get("mismatch_count"), 0, 1000),
    }


def _manifest_summary(value: Any) -> dict[str, Any]:
    return _status_summary(value)


def _model_summary(value: Any) -> dict[str, Any]:
    """Keep deployment evidence safe even when called with raw metrics."""

    raw = _mapping(value)
    result: dict[str, Any] = {
        "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
        "available": bool(raw.get("available", raw)),
    }
    mode = str(raw.get("execution_mode") or "").strip().lower()
    result["execution_mode"] = mode if mode in _EXECUTION_MODES else "unknown"
    for key in (
        "provider",
        "model",
        "wire_api",
        "status",
        "error_type",
        "context_fingerprint",
    ):
        item = raw.get(key)
        if isinstance(item, str) and item:
            result[key] = item[:96]
    if result["execution_mode"] == "offline_replay":
        item = raw.get("fixture_id")
        if isinstance(item, str) and item:
            result["fixture_id"] = item[:96]
    for key in ("attempts", "retries"):
        item = raw.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = max(0, min(item, 128))
    latency = raw.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        result["latency_ms"] = round(max(0.0, min(float(latency), 3_600_000.0)), 3)
    usage = raw.get("usage")
    if isinstance(usage, Mapping):
        safe_usage: dict[str, int] = {}
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
        ):
            item = usage.get(key)
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                safe_usage[key] = min(item, 10_000_000)
        if safe_usage:
            result["usage"] = safe_usage
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return minimum
    try:
        return max(minimum, min(maximum, int(value or 0)))
    except (TypeError, ValueError):
        return minimum


__all__ = ["DEPLOYMENT_EVIDENCE_SCHEMA_VERSION", "build_deployment_evidence"]
