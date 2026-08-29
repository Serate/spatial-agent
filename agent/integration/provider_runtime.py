"""Bounded, provider-neutral health and deadline evidence.

The module is the public seam between a model adapter and the rest of the
Agent.  It accepts configuration or adapter metrics, but returns only safe
identity, state, counts and timing facts.  Keys, URLs, request bodies and
provider error text never cross this seam.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any
from urllib.parse import urlsplit

from agent.integration.provider_structured_output import (
    StructuredOutputProfileError,
    build_structured_output_profile,
    project_structured_output_profile,
)


PROVIDER_HEALTH_SCHEMA_VERSION = "spatial-agent.provider-health.v1"
PROVIDER_DEADLINE_SCHEMA_VERSION = "spatial-agent.provider-deadline.v1"
PROVIDER_RUNTIME_SCHEMA_VERSION = "spatial-agent.provider-runtime.v1"
PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION = "spatial-agent.planner-attempt.v1"

_SAFE_STATES = frozenset({"not_started", "in_progress", "completed", "failed", "timed_out"})
_SAFE_PLANNER_STAGES = frozenset({"discovery", "selection", "execution", "repair"})
_SAFE_PLANNER_OUTCOMES = frozenset(
    {"success", "needs_clarification", "rejected", "provider_failure", "execution_failure", "unknown"}
)
_SAFE_ACTIONS = frozenset(
    {"submit", "provide_facts", "adjust_request", "retry", "check_provider_config", "view_partial_result"}
)
_SAFE_ERROR_TYPES = frozenset(
    {"http_error", "url_error", "timeout", "response_json_error", "response_shape_error"}
)
_SAFE_REASONS = frozenset(
    {
        "configured",
        "api_key_missing",
        "endpoint_invalid",
        "structured_profile_invalid",
        "network_unavailable",
        "network_not_checked",
        "provider_timeout",
        "provider_network",
        "provider_http_error",
        "invalid_model_response",
        "provider_error",
    }
)


def build_provider_health(
    config: Mapping[str, Any] | None,
    *,
    network_available: bool | None = None,
    network_checked: bool = False,
) -> dict[str, Any]:
    """Build a safe, read-only health fact from model configuration.

    ``network_available`` is supplied by the caller because this module must
    not perform a socket probe or a token-consuming request as a side effect.
    """

    value = config if isinstance(config, Mapping) else {}
    api_key_present = bool(str(value.get("api_key") or "").strip())
    base_url = value.get("api_url") or value.get("base_url") or "https://api.openai.com"
    endpoint_valid = _valid_endpoint(base_url)
    wire_api = str(value.get("wire_api") or "responses").strip().lower()
    structured_mode = str(value.get("structured_output_mode") or "json_schema").strip().lower()
    try:
        profile = build_structured_output_profile(
            wire_api=wire_api,
            structured_mode=structured_mode,
            source="config",
        )
        profile_valid = True
    except StructuredOutputProfileError:
        profile = project_structured_output_profile({})
        profile_valid = False

    reason = "configured"
    if not api_key_present:
        reason = "api_key_missing"
    elif not endpoint_valid:
        reason = "endpoint_invalid"
    elif not profile_valid:
        reason = "structured_profile_invalid"
    elif network_checked and network_available is False:
        reason = "network_unavailable"
    elif not network_checked:
        reason = "network_not_checked"

    status = "ready"
    if reason in {"api_key_missing", "endpoint_invalid", "structured_profile_invalid", "network_unavailable"}:
        status = "unavailable"
    elif reason == "network_not_checked":
        status = "configured"

    return {
        "schema_version": PROVIDER_HEALTH_SCHEMA_VERSION,
        "status": status,
        "configured": api_key_present and endpoint_valid and profile_valid,
        "network": (
            "reachable"
            if network_checked and network_available is True
            else "unreachable"
            if network_checked and network_available is False
            else "not_checked"
        ),
        "provider": _safe_identity(value.get("provider") or "openai-compatible"),
        "model": _safe_identity(value.get("model") or "default"),
        "wire_api": wire_api if wire_api in {"responses", "chat_completions"} else "unknown",
        "structured_output": profile,
        "reason_code": reason,
    }


def build_provider_deadline_receipt(
    metrics: Mapping[str, Any] | None,
    *,
    harness_timeout_seconds: Any = None,
    deadline_exceeded: Any = None,
) -> dict[str, Any]:
    """Normalize adapter metrics into one bounded request deadline receipt."""

    value = metrics if isinstance(metrics, Mapping) else {}
    raw_status = str(value.get("status") or value.get("state") or "not_started").strip().lower()
    error_type = value.get("error_type")
    error_type = error_type if error_type in _SAFE_ERROR_TYPES else None
    exceeded = bool(deadline_exceeded) if isinstance(deadline_exceeded, bool) else False
    if not exceeded and isinstance(value.get("deadline_exceeded"), bool):
        exceeded = value["deadline_exceeded"]
    if not exceeded:
        exceeded = error_type == "timeout"
    if exceeded or raw_status == "timed_out":
        state = "timed_out"
    elif raw_status == "in_progress":
        state = "in_progress"
    elif raw_status in {"success", "completed"}:
        state = "completed"
    elif raw_status in {"error", "failed"}:
        state = "failed"
    else:
        state = "not_started"

    provider_timeout = _bounded_float(value.get("timeout_seconds"), 0.0, 86_400.0)
    harness_timeout = _bounded_float(harness_timeout_seconds, 0.0, 86_400.0)
    if harness_timeout is None:
        harness_timeout = _bounded_float(value.get("harness_timeout_seconds"), 0.0, 86_400.0)
    result: dict[str, Any] = {
        "schema_version": PROVIDER_DEADLINE_SCHEMA_VERSION,
        "state": state,
        "deadline_exceeded": exceeded,
        "retryable": bool(
            value.get("retryable")
            if isinstance(value.get("retryable"), bool)
            else state == "timed_out" or error_type in {"url_error", "timeout"}
        ),
    }
    if provider_timeout is not None:
        result["provider_timeout_seconds"] = provider_timeout
    if harness_timeout is not None:
        result["harness_timeout_seconds"] = harness_timeout
    for source_key, output_key, maximum in (
        ("attempts", "attempts", 128),
        ("retries", "retries", 128),
        ("max_retries", "max_retries", 128),
    ):
        bounded = _bounded_int(value.get(source_key), 0, maximum)
        if bounded is not None:
            result[output_key] = bounded
    latency = _bounded_float(value.get("latency_ms"), 0.0, 3_600_000.0)
    if latency is not None:
        result["elapsed_ms"] = latency
    if error_type:
        result["error_type"] = error_type
        result["reason_code"] = {
            "timeout": "provider_timeout",
            "url_error": "provider_network",
            "http_error": "provider_http_error",
            "response_json_error": "invalid_model_response",
            "response_shape_error": "invalid_model_response",
        }.get(error_type, "provider_error")
    elif state == "failed":
        result["reason_code"] = "provider_error"
    return result


def project_provider_health(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project a previously built health fact without trusting extra fields."""

    raw = value if isinstance(value, Mapping) else {}
    status = str(raw.get("status") or "unavailable").strip().lower()
    if status not in {"ready", "configured", "unavailable"}:
        status = "unavailable"
    network = str(raw.get("network") or "not_checked").strip().lower()
    if network not in {"reachable", "unreachable", "not_checked"}:
        network = "not_checked"
    reason = str(raw.get("reason_code") or "provider_error").strip().lower()
    if reason not in _SAFE_REASONS:
        reason = "provider_error"
    return {
        "schema_version": PROVIDER_HEALTH_SCHEMA_VERSION,
        "status": status,
        "configured": bool(raw.get("configured")),
        "network": network,
        "provider": _safe_identity(raw.get("provider") or "unknown"),
        "model": _safe_identity(raw.get("model") or "unknown"),
        "wire_api": str(raw.get("wire_api") or "unknown")[:32],
        "structured_output": project_structured_output_profile(
            raw.get("structured_output") if isinstance(raw.get("structured_output"), Mapping) else {}
        ),
        "reason_code": reason,
    }


def project_provider_runtime_evidence(
    metrics: Mapping[str, Any] | None,
    *,
    provider_health: Mapping[str, Any] | None = None,
    harness_timeout_seconds: Any = None,
    deadline_exceeded: Any = None,
) -> dict[str, Any] | None:
    """Return the common health + deadline evidence used by all consumers."""

    value = metrics if isinstance(metrics, Mapping) else {}
    if (
        str(value.get("schema_version") or "") == PROVIDER_RUNTIME_SCHEMA_VERSION
        and isinstance(value.get("deadline"), Mapping)
    ):
        result: dict[str, Any] = {
            "schema_version": PROVIDER_RUNTIME_SCHEMA_VERSION,
            "deadline": build_provider_deadline_receipt(value.get("deadline")),
        }
        if isinstance(value.get("health"), Mapping):
            result["health"] = project_provider_health(value["health"])
        return result
    health_source = provider_health or value.get("provider_health")
    if not isinstance(health_source, Mapping) and not value:
        return None
    health = project_provider_health(health_source) if isinstance(health_source, Mapping) else None
    deadline = build_provider_deadline_receipt(
        value,
        harness_timeout_seconds=harness_timeout_seconds,
        deadline_exceeded=deadline_exceeded,
    )
    result: dict[str, Any] = {
        "schema_version": PROVIDER_RUNTIME_SCHEMA_VERSION,
        "deadline": deadline,
    }
    if health is not None:
        result["health"] = health
    return result


def build_planner_attempt_receipt(
    metrics: Mapping[str, Any] | None,
    *,
    stage: Any = "selection",
    outcome: Any = None,
    reason_code: Any = None,
    request_budget: Mapping[str, Any] | None = None,
    repair: Mapping[str, Any] | None = None,
    next_actions: Any = None,
) -> dict[str, Any] | None:
    """Build a bounded receipt for one planner/provider attempt.

    The receipt is deliberately smaller than provider runtime evidence.  It
    records enough information to explain latency, budget use and the next
    action, while never carrying prompt text, response text, URLs or keys.
    """

    value = metrics if isinstance(metrics, Mapping) else {}
    if not value and not isinstance(request_budget, Mapping) and not isinstance(repair, Mapping):
        return None
    raw_stage = str(stage or "selection").strip().lower()
    stage = raw_stage if raw_stage in _SAFE_PLANNER_STAGES else "selection"
    deadline = build_provider_deadline_receipt(value)
    state = str(deadline.get("state") or "not_started")
    raw_outcome = str(outcome or "").strip().lower()
    if raw_outcome not in _SAFE_PLANNER_OUTCOMES:
        if state == "timed_out" or deadline.get("error_type"):
            raw_outcome = "provider_failure"
        elif state == "completed":
            raw_outcome = "success"
        else:
            raw_outcome = "unknown"
    result: dict[str, Any] = {
        "schema_version": PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION,
        "stage": stage,
        "state": state,
        "outcome": raw_outcome,
        "attempts": _bounded_int(value.get("attempts"), 0, 128) or 0,
        "retries": _bounded_int(value.get("retries"), 0, 128) or 0,
        "retryable": bool(
            value.get("retryable")
            if isinstance(value.get("retryable"), bool)
            else deadline.get("retryable")
        ),
        "next_actions": _project_actions(
            next_actions
            if next_actions is not None
            else _default_planner_actions(raw_outcome, bool(deadline.get("retryable")))
        ),
    }
    code = _safe_code(reason_code) or _safe_code(deadline.get("reason_code"))
    if code:
        result["reason_code"] = code
    elapsed = _bounded_float(value.get("latency_ms"), 0.0, 3_600_000.0)
    if elapsed is not None:
        result["elapsed_ms"] = elapsed
    budget = _project_planner_budget(value, request_budget)
    if budget:
        result["budget"] = budget
    repair_projection = _project_repair_receipt(repair)
    if repair_projection:
        result["repair"] = repair_projection
    return result


def project_planner_attempt_receipt(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Idempotently project an existing planner attempt receipt."""

    if not isinstance(value, Mapping):
        return None
    if not value and not value.get("schema_version"):
        return None
    stage = str(value.get("stage") or "selection").strip().lower()
    state = str(value.get("state") or "not_started").strip().lower()
    outcome = str(value.get("outcome") or "unknown").strip().lower()
    result: dict[str, Any] = {
        "schema_version": PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION,
        "stage": stage if stage in _SAFE_PLANNER_STAGES else "selection",
        "state": state if state in _SAFE_STATES else "not_started",
        "outcome": outcome if outcome in _SAFE_PLANNER_OUTCOMES else "unknown",
        "attempts": _bounded_int(value.get("attempts"), 0, 128) or 0,
        "retries": _bounded_int(value.get("retries"), 0, 128) or 0,
        "retryable": value.get("retryable") is True,
        "next_actions": _project_actions(value.get("next_actions")),
    }
    code = _safe_code(value.get("reason_code"))
    if code:
        result["reason_code"] = code
    elapsed = _bounded_float(value.get("elapsed_ms"), 0.0, 3_600_000.0)
    if elapsed is not None:
        result["elapsed_ms"] = elapsed
    budget = _project_planner_budget({}, value.get("budget"))
    if budget:
        result["budget"] = budget
    repair_projection = _project_repair_receipt(value.get("repair"))
    if repair_projection:
        result["repair"] = repair_projection
    return result


def _project_planner_budget(
    metrics: Mapping[str, Any], budget: Mapping[str, Any] | None
) -> dict[str, Any]:
    source = budget if isinstance(budget, Mapping) else {}
    result: dict[str, Any] = {}
    fields = (
        ("envelope_max_bytes", ("envelope_max_bytes", "max_envelope_bytes"), 1, 1_000_000),
        ("envelope_bytes", ("envelope_bytes",), 0, 1_000_000),
        ("output_max_tokens", ("output_max_tokens", "max_output_tokens"), 1, 2_000_000),
        ("provider_timeout_seconds", ("provider_timeout_seconds", "timeout_seconds"), 0.0, 86_400.0),
        ("harness_timeout_seconds", ("harness_timeout_seconds",), 0.0, 86_400.0),
    )
    for output_key, source_keys, minimum, maximum in fields:
        raw = None
        for key in source_keys:
            if source.get(key) not in (None, ""):
                raw = source.get(key)
                break
            if metrics.get(key) not in (None, ""):
                raw = metrics.get(key)
                break
        bounded = (
            _bounded_int(raw, int(minimum), int(maximum))
            if isinstance(minimum, int)
            else _bounded_float(raw, float(minimum), float(maximum))
        )
        if bounded is not None:
            result[output_key] = bounded
    return result


def _project_repair_receipt(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        "attempted": value.get("attempted") is True,
        "count": _bounded_int(value.get("count"), 0, 1) or 0,
        "max_attempts": _bounded_int(value.get("max_attempts"), 0, 1) or 1,
        "state": _safe_code(value.get("status")) or "not_attempted",
    }
    return result


def _default_planner_actions(outcome: str, retryable: bool) -> list[str]:
    if outcome == "success":
        return ["submit"]
    if outcome == "needs_clarification":
        return ["provide_facts"]
    if outcome == "provider_failure":
        return ["retry" if retryable else "check_provider_config"]
    if outcome == "rejected":
        return ["adjust_request"]
    if outcome == "execution_failure":
        return ["view_partial_result"]
    return []


def _project_actions(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in values[:4]:
        action = str(item or "").strip().lower()[:48]
        if action in _SAFE_ACTIONS and action not in result:
            result.append(action)
    return result


def _safe_code(value: Any) -> str:
    text = str(value or "").strip()[:96]
    return text if re.fullmatch(r"[A-Za-z0-9_.:/-]{1,96}", text) else ""


def _valid_endpoint(value: Any) -> bool:
    try:
        parsed = urlsplit(str(value or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def _safe_identity(value: Any) -> str:
    text = str(value or "unknown").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,96}", text):
        return "unknown"
    return text


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return None


def _bounded_float(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return round(max(minimum, min(maximum, parsed)), 3)


__all__ = [
    "PROVIDER_DEADLINE_SCHEMA_VERSION",
    "PROVIDER_HEALTH_SCHEMA_VERSION",
    "PROVIDER_RUNTIME_SCHEMA_VERSION",
    "PLANNER_ATTEMPT_RECEIPT_SCHEMA_VERSION",
    "build_provider_deadline_receipt",
    "build_provider_health",
    "build_planner_attempt_receipt",
    "project_provider_health",
    "project_planner_attempt_receipt",
    "project_provider_runtime_evidence",
]
