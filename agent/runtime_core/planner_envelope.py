"""Small, versioned context envelope sent to a Planner provider.

The Composite request context is intentionally richer than the provider
payload: Runtime validation and recovery need the full receipt, while an LLM
only needs request facts, registered choices, and the execution closure for
those choices.  This module is a domain-neutral projection seam; it never
selects a tool or interprets a Domain field.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent.request_understanding import normalize_request_understanding_guidance
from agent.runtime_core.request_fact_readiness import project_request_fact_readiness


PLANNER_ENVELOPE_SCHEMA_VERSION = "spatial-agent.planner-envelope.v1"
PLANNER_ENVELOPE_MAX_BYTES = 96_000
PLANNER_ENVELOPE_LAYERS = (
    "request_facts",
    "capability_index",
    "selection",
    "execution_contract",
)

_MAX_DOMAINS = 8
_MAX_CANDIDATES = 16
_MAX_WORKFLOWS = 24
_MAX_FIELDS = 8
_MAX_LIST = 16
_PRIVATE_KEYS = {
    "api_key",
    "credential",
    "messages",
    "model_response",
    "password",
    "private_payload",
    "prompt",
    "raw_response",
    "secret",
    "source_path",
    "token",
}


class PlannerEnvelopeError(ValueError):
    """A provider-facing planner envelope cannot be safely projected."""

    def __init__(self, message: str, *, code: str = "planner_envelope_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def build_planner_envelope(
    context: Mapping[str, Any] | None,
    *,
    max_bytes: int = PLANNER_ENVELOPE_MAX_BYTES,
    max_candidates: int = _MAX_CANDIDATES,
    max_workflows: int = _MAX_WORKFLOWS,
) -> dict[str, Any]:
    """Project a bounded context into the four provider-facing layers."""

    if not isinstance(context, Mapping):
        context = {}
    byte_limit = _positive_limit(max_bytes, "max_bytes")
    candidate_limit = _positive_limit(max_candidates, "max_candidates")
    workflow_limit = _positive_limit(max_workflows, "max_workflows")
    candidates = _candidate_index(context.get("capability_index"), candidate_limit)
    envelope: dict[str, Any] = {
        "schema_version": PLANNER_ENVELOPE_SCHEMA_VERSION,
        "source_context_schema_version": _text(context.get("schema_version"), 96)
        or None,
        "planner": _text(context.get("planner"), 32) or None,
        "backend": _text(context.get("backend"), 32) or None,
        "request_fingerprint": _text(context.get("request_fingerprint"), 128) or None,
        "request_summary": _text(context.get("request_summary"), 640),
        "layers": list(PLANNER_ENVELOPE_LAYERS),
        "redaction": {
            "applied": True,
            "private_fields_removed": True,
        },
        "request_facts": _request_facts(context),
        "capability_index": candidates,
        "selection": _selection_projection(context, candidates),
        "execution_contract": _execution_projection(
            context, candidates, workflow_limit
        ),
        "discovery": _discovery_projection(context.get("discovery")),
        "clarification": _clarification_projection(context.get("clarification")),
        "limits": {
            "max_bytes": byte_limit,
            "max_candidates": candidate_limit,
            "max_workflows": workflow_limit,
        },
    }
    repair = context.get("planner_repair")
    if isinstance(repair, Mapping):
        envelope["planner_repair"] = _repair_projection(repair)
    _assert_budget(envelope, byte_limit)
    return envelope


def normalize_planner_envelope(
    value: Mapping[str, Any], *, max_bytes: int = PLANNER_ENVELOPE_MAX_BYTES
) -> dict[str, Any]:
    """Validate an already projected envelope without accepting new fields."""

    if str(value.get("schema_version") or "") != PLANNER_ENVELOPE_SCHEMA_VERSION:
        raise PlannerEnvelopeError(
            "planner envelope schema is unsupported",
            code="planner_envelope_schema_invalid",
        )
    envelope = build_planner_envelope(value, max_bytes=max_bytes)
    envelope["source_context_schema_version"] = _text(
        value.get("source_context_schema_version"), 96
    ) or None
    _assert_budget(envelope, _positive_limit(max_bytes, "max_bytes"))
    return envelope


def _request_facts(context: Mapping[str, Any]) -> dict[str, Any]:
    domains: list[dict[str, Any]] = []
    for raw in _sequence(context.get("domain_contexts"))[:_MAX_DOMAINS]:
        if not isinstance(raw, Mapping):
            continue
        facts = raw.get("facts") if isinstance(raw.get("facts"), Mapping) else {}
        domains.append(
            {
                "domain_id": _text(raw.get("domain_id"), 64),
                "facts": {
                    "schema_version": _text(facts.get("schema_version"), 96) or None,
                    "admin_name": _text(facts.get("admin_name"), 120) or None,
                    "entities": _safe_value(facts.get("entities") or {}, depth=0),
                    "tasks": _strings(facts.get("tasks"), 8),
                    "datasets": _strings(facts.get("datasets"), 16),
                    "constraints": _safe_value(
                        facts.get("constraints") or {}, depth=0
                    ),
                },
                "understanding": _understanding_projection(
                    raw.get("request_understanding"),
                    domain_id=raw.get("domain_id"),
                ),
                "data_readiness": _readiness(raw.get("data_readiness")),
                "fact_readiness": project_request_fact_readiness(
                    raw.get("fact_readiness")
                ),
                "clarification": _small_clarification(raw.get("clarification")),
            }
        )
    if not domains:
        facts = context.get("facts")
        domains.append(
            {
                "domain_id": None,
                "facts": _safe_value(facts or {}, depth=0),
                "data_readiness": {},
                "clarification": {},
            }
        )
    return {"domains": domains}


def _understanding_projection(value: Any, *, domain_id: Any = None) -> dict[str, Any]:
    """Keep Domain-owned request hints bounded in the provider envelope."""

    return normalize_request_understanding_guidance(
        value,
        domain_id=str(domain_id or "unknown")[:80],
    )


def _candidate_index(value: Any, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _sequence(value):
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        capability_id = _text(raw.get("capability_id"), 96)
        if not domain_id or not capability_id:
            continue
        identity = (domain_id, capability_id)
        if identity in seen:
            continue
        seen.add(identity)
        item: dict[str, Any] = {
            "domain_id": domain_id,
            "capability_id": capability_id,
            "selection_key": _text(raw.get("selection_key"), 140)
            or f"{domain_id}::{capability_id}"[:140],
            "label": _text(raw.get("label"), 160),
            "description": _text(raw.get("description"), 320),
            "available": bool(raw.get("available")),
            "availability_reason": _text(raw.get("availability_reason"), 160),
            "datasets": _strings(raw.get("datasets"), 8),
            "missing_datasets": _strings(raw.get("missing_datasets"), 8),
            "result_types": _strings(raw.get("result_types"), 16),
            "output_profiles": _profiles(raw.get("output_profiles")),
            "request_requirements": _requirements(raw.get("request_requirements")),
        }
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _selection_projection(
    context: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    discovery = context.get("discovery")
    discovery = discovery if isinstance(discovery, Mapping) else {}
    selected: list[str] = []
    for raw in _sequence(context.get("domain_contexts")):
        if not isinstance(raw, Mapping):
            continue
        domain_id = _text(raw.get("domain_id"), 64)
        local_discovery = raw.get("discovery")
        local_discovery = (
            local_discovery if isinstance(local_discovery, Mapping) else {}
        )
        value = local_discovery.get("selected_capability_id")
        if value:
            key = f"{domain_id}::{_text(value, 96)}"[:140]
            if key not in selected:
                selected.append(key)
    if not selected:
        for raw in _sequence(discovery.get("candidates")):
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("state") or "") not in {"available", "selected"}:
                continue
            key = f"{_text(raw.get('domain_id'), 64)}::{_text(raw.get('capability_id'), 96)}"[:140]
            if key not in selected:
                selected.append(key)
    candidate_keys = [
        _text(item.get("selection_key"), 140)
        for item in candidates
        if _text(item.get("selection_key"), 140)
    ]
    return {
        "state": _text(discovery.get("state"), 32) or "unknown",
        "reason_code": _text(discovery.get("reason_code"), 96) or "unknown",
        "candidate_count": len(candidate_keys),
        "candidate_keys": candidate_keys[:_MAX_CANDIDATES],
        "selected_capability_keys": selected[:_MAX_CANDIDATES],
    }


def _execution_projection(
    context: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    workflow_limit: int,
) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    workflow_ids: set[tuple[str, str]] = set()
    candidate_identities = {
        (str(item.get("domain_id")), str(item.get("capability_id")))
        for item in candidates
        if isinstance(item, Mapping)
    }
    for raw in _sequence(context.get("capability_index")):
        if not isinstance(raw, Mapping):
            continue
        identity = {
            "domain_id": _text(raw.get("domain_id"), 64),
            "capability_id": _text(raw.get("capability_id"), 96),
        }
        if not identity["domain_id"] or not identity["capability_id"]:
            continue
        if (identity["domain_id"], identity["capability_id"]) not in candidate_identities:
            continue
        allowed = {
            **identity,
            "workflow_ids": _strings(raw.get("workflow_ids"), 8),
            "plan_mode": _text(raw.get("plan_mode"), 32) or None,
            "tools": _strings(raw.get("tools"), 24),
            "result_types": _strings(raw.get("result_types"), 16),
            "output_profiles": _profiles(raw.get("output_profiles")),
            "execution_readiness": _text(raw.get("execution_readiness"), 32)
            or None,
            "execution_ready": (
                bool(raw.get("execution_ready"))
                if "execution_ready" in raw
                else None
            ),
            "execution_reason_code": _text(raw.get("execution_reason_code"), 96)
            or None,
            "missing_tools": _strings(raw.get("missing_tools"), 8),
            "missing_result_types": _strings(raw.get("missing_result_types"), 8),
        }
        bindings.append(allowed)
        for workflow_id in allowed["workflow_ids"]:
            workflow_ids.add((identity["domain_id"], workflow_id))

    workflows: list[dict[str, Any]] = []
    for raw in _sequence(context.get("workflow_index")):
        if not isinstance(raw, Mapping):
            continue
        identity = (_text(raw.get("domain_id"), 64), _text(raw.get("workflow_id"), 96))
        if identity not in workflow_ids:
            continue
        workflows.append(
            {
                "domain_id": identity[0],
                "workflow_id": identity[1],
                "label": _text(raw.get("label"), 160),
                "allowed_tools": _strings(raw.get("allowed_tools"), 24),
                "result_types": _strings(raw.get("result_types"), 16),
            }
        )
        if len(workflows) >= workflow_limit:
            break
    return {
        "capabilities": bindings[: len(candidates)],
        "workflows": workflows,
        "data_readiness": _safe_value(context.get("data_readiness") or {}, depth=0),
    }


def _discovery_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    candidates = _sequence(source.get("candidates"))
    states: dict[str, int] = {}
    for raw in candidates:
        if isinstance(raw, Mapping):
            state = _text(raw.get("state"), 32) or "unknown"
            states[state] = states.get(state, 0) + 1
    return {
        "schema_version": _text(source.get("schema_version"), 96) or None,
        "state": _text(source.get("state"), 32) or "unknown",
        "reason_code": _text(source.get("reason_code"), 96) or "unknown",
        "candidate_states": states,
        "data_requirement_count": len(_sequence(source.get("data_requirements"))),
        "next_actions": _strings(source.get("next_actions"), 4),
    }


def _clarification_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "not_required",
        "reason_code": _text(source.get("reason_code"), 96) or "unknown",
        "message": _text(source.get("message"), 640),
        "missing_by_domain": _safe_value(
            source.get("missing_by_domain") or [], depth=0
        ),
        "next_actions": _strings(source.get("next_actions"), 4),
    }


def _small_clarification(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "state": _text(source.get("state"), 32) or "not_required",
        "missing_fields": _safe_value(source.get("missing_fields") or [], depth=0),
    }


def _readiness(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "status": _text(source.get("status"), 32) or "unknown",
        "reason_code": _text(source.get("reason_code"), 96) or None,
    }


def _repair_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": _text(value.get("schema_version"), 96),
        "reason_code": _text(value.get("reason_code"), 96),
        "attempt": value.get("attempt") if isinstance(value.get("attempt"), int) else 1,
        "max_attempts": value.get("max_attempts")
        if isinstance(value.get("max_attempts"), int)
        else 1,
    }


def _requirements(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    fields = []
    for raw in _sequence(source.get("clarification_fields"))[:_MAX_FIELDS]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        label = _text(raw.get("label"), 120)
        if not field_id or not label:
            continue
        fields.append(
            {
                "id": field_id,
                "label": label,
                "kind": _text(raw.get("kind"), 32),
                "required": bool(raw.get("required", True)),
            }
        )
    return {"clarification_fields": fields}


def _profiles(value: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _sequence(value)[:24]:
        if not isinstance(raw, Mapping):
            continue
        result_type = _text(raw.get("result_type"), 96)
        kinds = _strings(raw.get("kinds"), 8)
        if not result_type or not kinds:
            continue
        result.append(
            {
                "result_type": result_type,
                "schema_version": _text(raw.get("schema_version"), 96) or None,
                "primary": _text(raw.get("primary"), 32) or kinds[0],
                "kinds": kinds,
            }
        )
    return result


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if str(key).strip().lower().replace("-", "_") not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:_MAX_LIST]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)[:640] if isinstance(value, str) else value
    return str(value)[:160]


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    return list(value)


def _strings(value: Any, limit: int) -> list[str]:
    values = [value] if isinstance(value, str) else _sequence(value)
    result = []
    for item in values[:limit]:
        text = _text(item, 160)
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _positive_limit(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PlannerEnvelopeError(name + " must be positive") from exc
    if result <= 0:
        raise PlannerEnvelopeError(name + " must be positive")
    return result


def _assert_budget(value: Mapping[str, Any], limit: int) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise PlannerEnvelopeError(
            "planner envelope exceeds max_bytes", code="planner_envelope_too_large"
        )


__all__ = [
    "PLANNER_ENVELOPE_LAYERS",
    "PLANNER_ENVELOPE_MAX_BYTES",
    "PLANNER_ENVELOPE_SCHEMA_VERSION",
    "PlannerEnvelopeError",
    "build_planner_envelope",
    "normalize_planner_envelope",
]
