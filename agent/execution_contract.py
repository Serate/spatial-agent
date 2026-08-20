"""Domain-neutral execution identity and observability projection.

Run and Domain Action implementations have different internal state, but
clients need the same small answer to operational questions: what executed,
what state is it in, can its artifact be recovered, and can a failure be
identified safely?  This module is the single bounded projection for those
questions.  It never copies request text, action payloads, or tool results.
"""

from __future__ import annotations

from typing import Any, Mapping


EXECUTION_RECORD_SCHEMA_VERSION = "spatial-agent.execution-record.v1"


def build_execution_record(
    payload: Mapping[str, Any],
    *,
    kind: str | None = None,
    artifact_available: bool | None = None,
) -> dict[str, Any]:
    """Return a stable, bounded projection for a Run or Domain Action."""
    if not isinstance(payload, Mapping):
        raise ValueError("execution payload must be a mapping")
    action_execution = payload.get("action_execution")
    action_execution = action_execution if isinstance(action_execution, Mapping) else {}
    inferred_kind = "action" if payload.get("action_execution_id") else "run"
    normalized_kind = str(kind or inferred_kind).strip().lower()
    if normalized_kind not in {"run", "action"}:
        raise ValueError("execution kind must be run or action")
    identifier = payload.get("action_execution_id") if normalized_kind == "action" else payload.get("run_id")
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("execution payload must include its id")
    result = payload.get("result")
    result = result if isinstance(result, Mapping) else {}
    action_result = payload.get("action_result")
    action_result = action_result if isinstance(action_result, Mapping) else {}
    result_type = payload.get("result_type") or result.get("type") or action_result.get("result_type")
    duration = action_execution.get("duration_ms") or payload.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        duration = None
    else:
        duration = round(float(duration), 3)
    trace = payload.get("trace_summary")
    trace_count = len(trace) if isinstance(trace, list) else 0
    if artifact_available is None:
        artifact_available = isinstance(payload.get("artifact_ref"), str) and bool(
            payload.get("artifact_ref")
        )
    domain_id = payload.get("domain_id")
    if not domain_id:
        planning = result.get("planning")
        if isinstance(planning, Mapping):
            domain_id = planning.get("domain_id")
    return {
        "schema_version": EXECUTION_RECORD_SCHEMA_VERSION,
        "kind": normalized_kind,
        "id": str(identifier)[:128],
        "status": str(payload.get("status") or action_execution.get("status") or "UNKNOWN")[:32],
        "domain_id": str(domain_id or "unknown")[:80],
        "result_type": str(result_type or "unknown")[:96],
        "duration_ms": duration,
        "trace_count": min(trace_count, 1000),
        "artifact_available": bool(artifact_available),
        "idempotency_key_present": isinstance(payload.get("idempotency_key"), str)
        and bool(payload.get("idempotency_key")),
        "input_fingerprint_present": isinstance(payload.get("input_fingerprint"), str)
        and bool(payload.get("input_fingerprint")),
        "idempotency_reused": bool(payload.get("idempotency_reused")),
        "error_code": str(
            payload.get("action_error_code")
            or payload.get("error_code")
            or action_execution.get("error_code")
            or ""
        )[:96],
    }


def execution_record_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """Remove volatile identity/timing from a result-envelope projection."""
    return {
        key: record.get(key)
        for key in (
            "schema_version",
            "kind",
            "status",
            "domain_id",
            "result_type",
            "trace_count",
            "artifact_available",
            "idempotency_key_present",
            "input_fingerprint_present",
            "idempotency_reused",
            "error_code",
        )
    }


__all__ = [
    "EXECUTION_RECORD_SCHEMA_VERSION",
    "build_execution_record",
    "execution_record_summary",
]
