"""Bounded, transport-neutral evidence for replaceable planner models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from agent.contract_versions import MODEL_EVIDENCE_SCHEMA_VERSION
from agent.runtime_context import runtime_context_fingerprint


_EXECUTION_MODES = {"rule", "offline_replay", "live_model"}
_IDENTITY_FIELDS = ("provider", "model", "wire_api", "status", "error_type")
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
)


def project_model_evidence(
    metrics: Any,
    runtime_context: Any,
) -> Dict[str, Any]:
    """Project safe planner identity and usage evidence.

    The interface accepts the untrusted planner metrics and a descriptive
    runtime context, then returns a bounded JSON object. Provider responses,
    prompts, credentials, filesystem paths and arbitrary metric keys never
    cross this seam. Sync envelopes, async polling and artifact readers use
    the same implementation so their model identity remains comparable.
    """

    value = metrics if isinstance(metrics, Mapping) else {}
    explicit_available = value.get("available")
    available = (
        explicit_available
        if isinstance(explicit_available, bool)
        else bool(value)
    )
    result: Dict[str, Any] = {
        "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
        "available": available,
    }
    execution_mode = str(value.get("execution_mode") or "").strip().lower()
    if execution_mode not in _EXECUTION_MODES:
        context_mapping = runtime_context if isinstance(runtime_context, Mapping) else {}
        execution_mode = (
            "rule"
            if context_mapping.get("planner") == "rule"
            else "live_model"
            if value
            else "unknown"
        )
    result["execution_mode"] = execution_mode

    context_fingerprint = runtime_context_fingerprint(runtime_context)
    if context_fingerprint:
        result["context_fingerprint"] = context_fingerprint

    for key in _IDENTITY_FIELDS:
        item = value.get(key)
        if isinstance(item, str) and item:
            result[key] = item[:96]
    if execution_mode == "offline_replay":
        fixture_id = value.get("fixture_id")
        if isinstance(fixture_id, str) and fixture_id:
            result["fixture_id"] = fixture_id[:96]

    for key in ("attempts", "retries"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = max(0, min(item, 128))

    latency = value.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        result["latency_ms"] = round(max(0.0, min(float(latency), 3_600_000.0)), 3)

    usage = value.get("usage")
    if isinstance(usage, Mapping):
        safe_usage = {}
        for key in _USAGE_FIELDS:
            item = usage.get(key)
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                safe_usage[key] = min(item, 10_000_000)
        if safe_usage:
            result["usage"] = safe_usage
    return result


__all__ = ["project_model_evidence"]
