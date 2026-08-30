"""Shared, bounded handling for provider structured responses.

Provider adapters are allowed to differ in keyword support and recovery
methods, but Planner, ReAct and answer generation must share the same safety
boundary: one normal structured call, at most one compact recovery call, then
the caller's contract validator. This module intentionally does not validate
domain semantics or execute anything.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import inspect
from typing import Any

from agent.errors import PlanningError


STRUCTURED_RESPONSE_SCHEMA_VERSION = "spatial-agent.structured-response.v1"
MAX_STRUCTURED_RECOVERY_ATTEMPTS = 1


@dataclass(frozen=True)
class StructuredResponseCall:
    """A validated provider object plus bounded recovery metadata."""

    payload: Mapping[str, Any]
    recovery_attempts: int = 0


def call_structured_json(
    client: Any,
    messages: Any,
    schema: Mapping[str, Any],
    *,
    schema_name: str | None = None,
    recovery_messages: Any = None,
    deterministic: bool = False,
    on_recovery: Callable[[], None] | None = None,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    timeout_provider: Callable[[], float | None] | None = None,
) -> StructuredResponseCall:
    """Call a structured provider and allow one shape-only recovery.

    A provider transport error, authentication error or timeout is propagated
    unchanged. Only the stable ``invalid_model_response`` classification is
    eligible for the one compact retry. The retry response is not retried a
    second time here; the caller still owns its normal schema/permission
    validation and may fail closed.
    """

    try:
        payload = _invoke(
            client,
            "complete_json",
            messages,
            schema,
            schema_name=schema_name,
            deterministic=deterministic,
            timeout_seconds=_resolve_timeout(timeout_seconds, timeout_provider),
            deadline=deadline,
            on_progress=on_progress,
        )
    except PlanningError as error:
        if getattr(error, "code", None) != "invalid_model_response":
            raise
        compact_messages = messages if recovery_messages is None else recovery_messages
        _report_progress(
            on_progress,
            {"kind": "structured_recovery_started", "recovery_attempt": 1},
        )
        if callable(on_recovery):
            on_recovery()
        method_name = (
            "complete_compact_json"
            if callable(getattr(client, "complete_compact_json", None))
            else "complete_json"
        )
        payload = _invoke(
            client,
            method_name,
            compact_messages,
            schema,
            schema_name=schema_name,
            deterministic=True,
            timeout_seconds=_resolve_timeout(timeout_seconds, timeout_provider),
            deadline=deadline,
            on_progress=on_progress,
        )
        return StructuredResponseCall(payload=payload, recovery_attempts=1)
    return StructuredResponseCall(payload=payload, recovery_attempts=0)


def call_compact_structured_json(
    client: Any,
    messages: Any,
    schema: Mapping[str, Any],
    *,
    schema_name: str | None = None,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
    on_progress: Callable[[Mapping[str, Any]], None] | None = None,
    timeout_provider: Callable[[], float | None] | None = None,
) -> Mapping[str, Any]:
    """Invoke an already-authorized semantic repair call exactly once.

    This is intentionally separate from :func:`call_structured_json`: ReAct
    may first apply a local alias repair, and only then ask the provider to
    correct the remaining action shape. It must not silently repeat the normal
    provider request.
    """

    method_name = (
        "complete_compact_json"
        if callable(getattr(client, "complete_compact_json", None))
        else "complete_json"
    )
    _report_progress(
        on_progress,
        {"kind": "structured_recovery_started", "recovery_attempt": 1},
    )
    return _invoke(
        client,
        method_name,
        messages,
        schema,
        schema_name=schema_name,
        deterministic=True,
        timeout_seconds=_resolve_timeout(timeout_seconds, timeout_provider),
        deadline=deadline,
        on_progress=on_progress,
    )


def repair_structured_fields(
    value: Any,
    aliases: Mapping[str, tuple[str, ...]],
) -> dict[str, Any] | None:
    """Apply only unambiguous field aliases, without dropping unknown data.

    The caller must run its strict contract validator after this function. A
    field is repaired only when the canonical key is absent and exactly one
    documented alias is present. Conflicting aliases and non-object values
    return ``None`` so a model cannot turn ambiguity into an executable value.
    """

    if not isinstance(value, Mapping):
        return None
    source = dict(value)
    changed = False
    for canonical, candidates in aliases.items():
        if canonical in source:
            continue
        present = [candidate for candidate in candidates if candidate in source]
        if len(present) != 1:
            if len(present) > 1:
                return None
            continue
        source[canonical] = source.pop(present[0])
        changed = True
    return source if changed else None


def structured_failure_receipt(
    error: Any,
    *,
    stage: str,
    recovery_attempts: int = 0,
) -> dict[str, Any]:
    """Project a stable, secret-free classification for observability."""

    code = str(getattr(error, "code", "") or "").strip()
    category = str(getattr(error, "category", "") or "").strip()
    retryable = getattr(error, "retryable", None)
    if code not in {
        "invalid_model_response",
        "provider_timeout",
        "provider_network",
        "provider_authentication",
        "provider_rate_limited",
        "provider_transient_http",
        "provider_http_error",
    }:
        code = "structured_response_invalid"
    if category not in {"planning", "provider", "answer"}:
        category = "planning" if code == "invalid_model_response" else "provider"
    return {
        "schema_version": STRUCTURED_RESPONSE_SCHEMA_VERSION,
        "stage": str(stage or "unknown")[:32],
        "category": category,
        "reason_code": code,
        "retryable": retryable is True,
        "recovery_attempts": max(
            0, min(int(recovery_attempts), MAX_STRUCTURED_RECOVERY_ATTEMPTS)
        ),
    }


def _invoke(
    client: Any,
    method_name: str,
    messages: Any,
    schema: Mapping[str, Any],
    *,
    schema_name: str | None,
    deterministic: bool,
    timeout_seconds: float | None,
    deadline: float | None,
    on_progress: Callable[[Mapping[str, Any]], None] | None,
) -> Mapping[str, Any]:
    method = getattr(client, method_name, None)
    if not callable(method):
        raise PlanningError(
            "LLM client does not support structured JSON",
            category="provider",
            code="provider_network",
            retryable=False,
        )
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD
        for item in parameters.values()
    )
    kwargs: dict[str, Any] = {}
    if schema_name and (accepts_kwargs or "schema_name" in parameters):
        kwargs["schema_name"] = schema_name
    if deterministic and (accepts_kwargs or "deterministic" in parameters):
        kwargs["deterministic"] = True
    if timeout_seconds is not None and (accepts_kwargs or "timeout_seconds" in parameters):
        kwargs["timeout_seconds"] = timeout_seconds
    if deadline is not None and (accepts_kwargs or "deadline" in parameters):
        kwargs["deadline"] = deadline
    if on_progress is not None:
        if accepts_kwargs or "on_progress" in parameters:
            kwargs["on_progress"] = on_progress
        elif "progress_callback" in parameters:
            kwargs["progress_callback"] = on_progress
    try:
        payload = method(messages, schema, **kwargs)
    except PlanningError:
        raise
    except (TypeError, ValueError) as exc:
        raise PlanningError(
            "structured provider response could not be normalized",
            category="planning",
            code="invalid_model_response",
            retryable=False,
        ) from exc
    if not isinstance(payload, Mapping):
        raise PlanningError(
            "LLM structured response must be an object",
            category="planning",
            code="invalid_model_response",
            retryable=False,
        )
    return payload


def _resolve_timeout(
    timeout_seconds: float | None,
    timeout_provider: Callable[[], float | None] | None,
) -> float | None:
    """Resolve a fresh timeout for each normal/recovery provider call."""

    if callable(timeout_provider):
        return timeout_provider()
    return timeout_seconds


def _report_progress(
    callback: Callable[[Mapping[str, Any]], None] | None,
    value: Mapping[str, Any],
) -> None:
    if not callable(callback):
        return
    try:
        callback(dict(value))
    except Exception:
        # Progress is advisory and must never weaken structured validation.
        pass


__all__ = [
    "MAX_STRUCTURED_RECOVERY_ATTEMPTS",
    "STRUCTURED_RESPONSE_SCHEMA_VERSION",
    "StructuredResponseCall",
    "call_compact_structured_json",
    "call_structured_json",
    "repair_structured_fields",
    "structured_failure_receipt",
]
