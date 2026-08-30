"""Versioned, bounded configuration evidence for one Agent Runtime run.

The context is deliberately descriptive rather than executable.  It records
which replaceable components and policy were selected, without retaining
requests, credentials, tool arguments, or raw provider responses.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any, Iterable

from .contract_versions import (
    MODEL_EVIDENCE_SCHEMA_VERSION,
    RESULT_ENVELOPE_SCHEMA_VERSION,
    TASK_PLAN_SCHEMA_VERSION,
)
from .domain_registry import DOMAIN_REGISTRY_SCHEMA_VERSION
from .execution_contract import EXECUTION_RECORD_SCHEMA_VERSION
from .tool_provider import TOOL_PROVIDER_CONTRACT_SCHEMA

RUNTIME_CONTEXT_SCHEMA_VERSION = "spatial-agent.runtime-context.v1"


class RuntimeContextMismatchError(ValueError):
    """Raised when a persisted run would execute under different config."""

    code = "runtime_context_mismatch"


def build_runtime_context(
    *,
    domain_id: str,
    planner: str,
    backend: str,
    tool_provider: Mapping[str, Any] | None = None,
    permissions: Iterable[str] = (),
    approved_tools: Iterable[str] = (),
    require_dependency_evidence: bool = False,
    web_mode: str = "allowlist",
) -> dict[str, Any]:
    """Build a stable JSON-safe snapshot of the selected runtime boundary."""

    provider = tool_provider if isinstance(tool_provider, Mapping) else {}
    provider_id = str(provider.get("id") or "unknown")[:96]
    try:
        tool_count = max(0, min(128, int(provider.get("tool_count") or 0)))
    except (TypeError, ValueError):
        tool_count = 0
    context = {
        "schema_version": RUNTIME_CONTEXT_SCHEMA_VERSION,
        "domain_id": str(domain_id or "unknown")[:80],
        "planner": str(planner or "unknown")[:32],
        "backend": str(backend or "unknown")[:32],
        "tool_provider": {
            "id": provider_id,
            "tool_count": tool_count,
        },
        "permissions": _bounded_strings(permissions, 32, 96),
        "approved_tools": _bounded_strings(approved_tools, 32, 96),
        "policies": {
            "require_dependency_evidence": bool(require_dependency_evidence),
            "web_mode": str(web_mode or "allowlist")[:32],
        },
        "contracts": {
            "domain_registry": DOMAIN_REGISTRY_SCHEMA_VERSION,
            "task_plan": TASK_PLAN_SCHEMA_VERSION,
            "execution_record": EXECUTION_RECORD_SCHEMA_VERSION,
            "result_envelope": RESULT_ENVELOPE_SCHEMA_VERSION,
            "tool_provider": TOOL_PROVIDER_CONTRACT_SCHEMA,
            "model_evidence": MODEL_EVIDENCE_SCHEMA_VERSION,
        },
    }
    return _with_fingerprint(context)


def normalize_runtime_context(value: Any) -> dict[str, Any] | None:
    """Normalize a persisted snapshot while keeping old payloads readable."""

    if not isinstance(value, Mapping):
        return None
    context = {
        "schema_version": str(
            value.get("schema_version") or RUNTIME_CONTEXT_SCHEMA_VERSION
        )[:96],
        "domain_id": str(value.get("domain_id") or "unknown")[:80],
        "planner": str(value.get("planner") or "unknown")[:32],
        "backend": str(value.get("backend") or "unknown")[:32],
        "tool_provider": _normalize_provider(value.get("tool_provider")),
        "permissions": _bounded_strings(value.get("permissions"), 32, 96),
        "approved_tools": _bounded_strings(value.get("approved_tools"), 32, 96),
        "policies": {
            "require_dependency_evidence": bool(
                (value.get("policies") or {}).get("require_dependency_evidence", False)
                if isinstance(value.get("policies"), Mapping)
                else False
            ),
            "web_mode": str(
                (value.get("policies") or {}).get("web_mode", "allowlist")
                if isinstance(value.get("policies"), Mapping)
                else "allowlist"
            )[:32],
        },
        "contracts": _normalize_contracts(value.get("contracts")),
    }
    return _with_fingerprint(context)


def runtime_context_fingerprint(value: Any) -> str:
    """Return a credential-free stable identity for a normalized context."""

    context = normalize_runtime_context(value)
    if context is None:
        return ""
    return str(context.get("fingerprint") or "")


def assert_runtime_context_compatible(expected: Any, actual: Any) -> None:
    """Reject execution when a persisted snapshot differs from live config."""

    if expected is None:
        return
    expected_context = normalize_runtime_context(expected)
    actual_context = normalize_runtime_context(actual)
    if expected_context is None or actual_context is None:
        raise RuntimeContextMismatchError(
            "persisted runtime context is not compatible with the current runtime"
        )
    if expected_context != actual_context:
        raise RuntimeContextMismatchError(
            "persisted runtime context differs from the current runtime"
        )


def _normalize_provider(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        value = {}
    try:
        tool_count = max(0, min(128, int(value.get("tool_count") or 0)))
    except (TypeError, ValueError):
        tool_count = 0
    return {
        "id": str(value.get("id") or "unknown")[:96],
        "tool_count": tool_count,
    }


def _normalize_contracts(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        value = {}
    defaults = {
        "domain_registry": DOMAIN_REGISTRY_SCHEMA_VERSION,
        "task_plan": TASK_PLAN_SCHEMA_VERSION,
        "execution_record": EXECUTION_RECORD_SCHEMA_VERSION,
        "result_envelope": RESULT_ENVELOPE_SCHEMA_VERSION,
        "tool_provider": TOOL_PROVIDER_CONTRACT_SCHEMA,
        "model_evidence": MODEL_EVIDENCE_SCHEMA_VERSION,
    }
    return {
        key: str(value.get(key) or default)[:96]
        for key, default in defaults.items()
    }


def _with_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    context = dict(context)
    context.pop("fingerprint", None)
    encoded = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    context["fingerprint"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return context


def _bounded_strings(value: Any, limit: int, item_limit: int) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:item_limit])
        if len(result) >= limit:
            break
    return sorted(result)


__all__ = [
    "RUNTIME_CONTEXT_SCHEMA_VERSION",
    "RuntimeContextMismatchError",
    "assert_runtime_context_compatible",
    "build_runtime_context",
    "normalize_runtime_context",
    "runtime_context_fingerprint",
]
