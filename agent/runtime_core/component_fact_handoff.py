"""Bounded fact handoff between Composite Planner components and Domains.

The Composite Planner is allowed to choose a registered capability, but it is
not allowed to invent or forward a Domain's private request model.  This seam
projects only the public requirements declared by the capability, the facts
already extracted by the request context, and the selected workflow's public
constraints.  Domain preview can then consume the handoff without reparsing
the component text or silently guessing missing values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from agent.request_model import RequestFacts
from agent.runtime_core.clarification_continuation import (
    issue_component_continuation,
)


COMPONENT_FACT_HANDOFF_SCHEMA_VERSION = "spatial-agent.component-fact-handoff.v1"
_MAX_FIELDS = 8
_MAX_COMPONENTS = 8
_MAX_STRINGS = 24
_MAX_BYTES = 24_000
_ALLOWED_STATES = {"ready", "required"}
_ALLOWED_KINDS = {"entity", "dataset", "constraint"}


class ComponentFactHandoffError(ValueError):
    """A component handoff is invalid or cannot be used safely."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "component_fact_handoff_invalid",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)[:96]
        self.details = _safe_details(details)
        super().__init__(str(message)[:320])


def build_component_fact_handoff(
    component: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    max_fields: int = _MAX_FIELDS,
) -> dict[str, Any]:
    """Build a safe handoff for one planner-selected component.

    The returned value is derived from the context/catalog, never from an
    untrusted planner-supplied handoff.  Workflow constraints may satisfy a
    declared requirement, but they are kept separately from request facts so
    evidence can explain where each value came from.
    """

    if not isinstance(component, Mapping):
        raise ComponentFactHandoffError(
            "component is not an object", code="component_fact_component_invalid"
        )
    if not isinstance(context, Mapping):
        raise ComponentFactHandoffError(
            "component context is not an object", code="component_fact_context_invalid"
        )
    component_id = _text(component.get("component_id"), 96)
    domain_id = _text(component.get("domain_id"), 64)
    capability_id = _text(component.get("capability_id"), 96)
    if not component_id or not domain_id or not capability_id:
        raise ComponentFactHandoffError(
            "component identity is incomplete", code="component_fact_identity_missing"
        )

    capability = _find_capability(context, domain_id, capability_id)
    if capability is None:
        raise ComponentFactHandoffError(
            "component capability is not registered",
            code="component_fact_capability_not_registered",
        )
    domain_context = _find_domain_context(context, domain_id)
    facts = _facts_projection(domain_context.get("facts"))
    workflow = component.get("workflow")
    if not isinstance(workflow, Mapping):
        workflow = domain_context.get("workflow")
    workflow_constraints = _mapping_values(
        workflow.get("constraints") if isinstance(workflow, Mapping) else None
    )
    effective_constraints = dict(facts["constraints"])
    effective_constraints.update(workflow_constraints)

    requirements = _requirements_projection(capability.get("request_requirements"))
    missing_fields = _missing_fields(
        requirements,
        facts=facts,
        workflow_constraints=workflow_constraints,
        component_id=component_id,
        domain_id=domain_id,
        capability_id=capability_id,
        max_fields=max_fields,
    )
    request_fingerprint = _text(context.get("request_fingerprint"), 128) or None
    selection_fingerprint = _selection_fingerprint(
        request_fingerprint=request_fingerprint,
        component=component,
        workflow=workflow,
    )
    state = "required" if missing_fields else "ready"
    result = {
        "schema_version": COMPONENT_FACT_HANDOFF_SCHEMA_VERSION,
        "state": state,
        "reason_code": (
            "component_facts_missing" if missing_fields else "component_facts_ready"
        ),
        "request_fingerprint": request_fingerprint,
        "planner_selection_fingerprint": selection_fingerprint,
        "component_id": component_id,
        "domain_id": domain_id,
        "domain_ids": _safe_strings(context.get("domain_ids"), 8) or [domain_id],
        "capability_id": capability_id,
        "requirements": requirements,
        "known_facts": facts,
        "workflow_constraints": workflow_constraints,
        "effective_constraints": effective_constraints,
        "missing_fields": missing_fields,
        "next_actions": ["provide_facts"] if missing_fields else ["preview"],
    }
    if missing_fields:
        continuation = issue_component_continuation(result)
        result["continuation"] = continuation
        result["continuation_token"] = continuation["token"]
    _assert_budget(result)
    return result


def normalize_component_fact_handoff(
    value: Any,
    *,
    expected_component_id: str | None = None,
    expected_domain_id: str | None = None,
    expected_request_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Validate the internal handoff before a Domain preview consumes it."""

    if not isinstance(value, Mapping):
        raise ComponentFactHandoffError(
            "component fact handoff must be an object",
            code="component_fact_handoff_required",
        )
    if str(value.get("schema_version") or "") != COMPONENT_FACT_HANDOFF_SCHEMA_VERSION:
        raise ComponentFactHandoffError(
            "component fact handoff schema is unsupported",
            code="component_fact_handoff_schema_invalid",
        )
    state = _text(value.get("state"), 24)
    if state not in _ALLOWED_STATES:
        raise ComponentFactHandoffError(
            "component fact handoff state is invalid",
            code="component_fact_handoff_state_invalid",
        )
    component_id = _text(value.get("component_id"), 96)
    domain_id = _text(value.get("domain_id"), 64)
    request_fingerprint = _text(value.get("request_fingerprint"), 128)
    _assert_identity(component_id, domain_id, request_fingerprint, expected_component_id, expected_domain_id, expected_request_fingerprint)
    missing = _normalize_missing_fields(value.get("missing_fields"), component_id, domain_id, _text(value.get("capability_id"), 96))
    if state == "ready" and missing:
        raise ComponentFactHandoffError(
            "ready component fact handoff still has missing fields",
            code="component_fact_handoff_state_mismatch",
        )
    if state == "required" and not missing:
        raise ComponentFactHandoffError(
            "required component fact handoff has no missing fields",
            code="component_fact_handoff_state_mismatch",
        )
    result = {
        "schema_version": COMPONENT_FACT_HANDOFF_SCHEMA_VERSION,
        "state": state,
        "reason_code": _text(value.get("reason_code"), 96),
        "request_fingerprint": request_fingerprint or None,
        "planner_selection_fingerprint": _text(value.get("planner_selection_fingerprint"), 128) or None,
        "component_id": component_id,
        "domain_id": domain_id,
        "domain_ids": _safe_strings(value.get("domain_ids"), 8) or [domain_id],
        "capability_id": _text(value.get("capability_id"), 96),
        "requirements": _requirements_projection(value.get("requirements")),
        "known_facts": _facts_projection(value.get("known_facts")),
        "workflow_constraints": _mapping_values(value.get("workflow_constraints")),
        "effective_constraints": _mapping_values(value.get("effective_constraints")),
        "missing_fields": missing,
        "next_actions": _safe_strings(value.get("next_actions"), 4),
    }
    continuation = value.get("continuation")
    if isinstance(continuation, Mapping):
        token = _text(continuation.get("token"), 8192)
        if token:
            result["continuation"] = {
                "schema_version": _text(continuation.get("schema_version"), 96),
                "token": token,
                "expires_at": continuation.get("expires_at"),
                "field_ids": _safe_strings(continuation.get("field_ids"), 16),
            }
            result["continuation_token"] = token
    _assert_budget(result)
    return result


def request_facts_from_handoff(
    value: Mapping[str, Any], *, text: str, require_ready: bool = True
) -> RequestFacts:
    """Convert ready handoff facts to the shared RequestFacts object."""

    handoff = normalize_component_fact_handoff(value)
    if require_ready and handoff["state"] != "ready":
        raise ComponentFactHandoffError(
            "component facts are incomplete", code="component_facts_missing", details=handoff
        )
    facts = handoff["known_facts"]
    constraints = dict(facts.get("constraints") or {})
    constraints.update(handoff.get("effective_constraints") or {})
    entities = facts.get("entities") or {}
    admin_name = str(entities.get("admin_name") or "").strip() or None
    return RequestFacts(
        text=str(text or "")[:2000],
        admin_name=admin_name,
        tasks=tuple(_safe_strings(facts.get("tasks"), 16)),
        datasets=tuple(_safe_strings(facts.get("datasets"), 24)),
        constraints=constraints,
        evidence=tuple(_safe_strings(facts.get("evidence"), 16)),
        entities=dict(entities),
    )


def project_component_fact_handoff(value: Any) -> dict[str, Any]:
    """Return only the safe handoff fields for evidence and transport."""

    try:
        normalized = normalize_component_fact_handoff(value)
    except ComponentFactHandoffError as exc:
        return {
            "schema_version": COMPONENT_FACT_HANDOFF_SCHEMA_VERSION,
            "state": "required",
            "reason_code": exc.code,
            "missing_fields": [],
        }
    return normalized


def _find_capability(context: Mapping[str, Any], domain_id: str, capability_id: str) -> Mapping[str, Any] | None:
    for item in context.get("capability_index") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("domain_id")) == domain_id and str(item.get("capability_id")) == capability_id:
            return item
    return None


def _find_domain_context(context: Mapping[str, Any], domain_id: str) -> Mapping[str, Any]:
    for item in context.get("domain_contexts") or []:
        if isinstance(item, Mapping) and str(item.get("domain_id")) == domain_id:
            return item
    return {}


def _facts_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    entities = _safe_mapping(source.get("entities"))
    admin_name = _text(source.get("admin_name"), 120)
    if admin_name and "admin_name" not in entities:
        entities["admin_name"] = admin_name
    return {
        "schema_version": _text(source.get("schema_version"), 96),
        "entities": entities,
        "tasks": _safe_strings(source.get("tasks"), 16),
        "datasets": _safe_strings(source.get("datasets"), 24),
        "constraints": _safe_mapping(source.get("constraints")),
        "evidence": _safe_strings(source.get("evidence"), 16),
    }


def _requirements_projection(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    fields: list[dict[str, Any]] = []
    for raw in (source.get("clarification_fields") or [])[:16]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        kind = _text(raw.get("kind"), 32)
        label = _text(raw.get("label"), 120)
        if not field_id or kind not in _ALLOWED_KINDS or not label:
            continue
        item = {
            "id": field_id,
            "label": label,
            "kind": kind,
            "required": bool(raw.get("required", True)),
            "source": "catalog",
            "mode": _text(raw.get("mode"), 8) if raw.get("mode") in {"any", "all"} else "any",
        }
        key = raw.get("key") or raw.get("fact")
        if key:
            item["key"] = _text(key, 80)
        keys = _safe_strings(raw.get("keys"), 16)
        values = _safe_strings(raw.get("values"), 16)
        if keys:
            item["keys"] = keys
        if values:
            item["values"] = values
        fields.append(item)
    return {
        "schema_version": _text(source.get("schema_version"), 96),
        "entities": _safe_strings(source.get("entities"), 16),
        "datasets": _safe_strings(source.get("datasets"), 24),
        "constraints": _safe_strings(source.get("constraints"), 24),
        "clarification_fields": fields[:_MAX_FIELDS],
    }


def _missing_fields(
    requirements: Mapping[str, Any],
    *,
    facts: Mapping[str, Any],
    workflow_constraints: Mapping[str, Any],
    component_id: str,
    domain_id: str,
    capability_id: str,
    max_fields: int,
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    entities = facts.get("entities") if isinstance(facts.get("entities"), Mapping) else {}
    datasets = set(_safe_strings(facts.get("datasets"), 24))
    constraints = dict(facts.get("constraints") or {})
    constraints.update(workflow_constraints)
    for field in requirements.get("clarification_fields") or []:
        if not isinstance(field, Mapping) or not field.get("required", True):
            continue
        kind = str(field.get("kind") or "")
        if kind == "entity":
            key = str(field.get("key") or "admin_name")
            present = bool(entities.get(key))
        elif kind == "dataset":
            expected = set(_safe_strings(field.get("values") or requirements.get("datasets"), 24))
            observed = datasets
            present = bool(expected & observed) if field.get("mode") != "all" else expected.issubset(observed)
        elif kind == "constraint":
            expected = set(_safe_strings(field.get("keys") or requirements.get("constraints"), 24))
            present = all(key in constraints and constraints.get(key) not in (None, "") for key in expected)
        else:
            present = True
        if present:
            continue
        item = {
            "component_id": component_id,
            "domain_id": domain_id,
            "capability_id": capability_id,
            "id": _text(field.get("id"), 80),
            "label": _text(field.get("label"), 120),
            "kind": kind,
            "source": "user",
            "required": True,
        }
        if field.get("key"):
            item["key"] = _text(field.get("key"), 80)
        if field.get("keys"):
            item["keys"] = _safe_strings(field.get("keys"), 16)
        missing.append(item)
        if len(missing) >= max(1, min(_MAX_FIELDS, int(max_fields))):
            break
    return missing


def _selection_fingerprint(*, request_fingerprint: str | None, component: Mapping[str, Any], workflow: Any) -> str:
    payload = {
        "request_fingerprint": request_fingerprint,
        "component_id": _text(component.get("component_id"), 96),
        "domain_id": _text(component.get("domain_id"), 64),
        "capability_id": _text(component.get("capability_id"), 96),
        "workflow": {
            "template_id": _text(workflow.get("template_id"), 96) if isinstance(workflow, Mapping) else None,
            "template_version": _text(workflow.get("template_version"), 48) if isinstance(workflow, Mapping) else None,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:64]


def _normalize_missing_fields(value: Any, component_id: str, domain_id: str, capability_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in (value or [])[:_MAX_FIELDS]:
        if not isinstance(raw, Mapping):
            raise ComponentFactHandoffError(
                "missing field is invalid", code="component_fact_field_invalid"
            )
        item = {
            "component_id": _text(raw.get("component_id") or component_id, 96),
            "domain_id": _text(raw.get("domain_id") or domain_id, 64),
            "capability_id": _text(raw.get("capability_id") or capability_id, 96),
            "id": _text(raw.get("id"), 80),
            "label": _text(raw.get("label"), 120),
            "kind": _text(raw.get("kind"), 32),
            "source": _text(raw.get("source"), 32),
            "required": bool(raw.get("required", True)),
        }
        if not item["id"] or not item["label"] or item["kind"] not in _ALLOWED_KINDS or item["source"] not in {"request", "catalog", "workflow", "user"}:
            raise ComponentFactHandoffError(
                "missing field contains unsupported metadata", code="component_fact_field_invalid"
            )
        result.append(item)
    return result


def _assert_identity(component_id: str, domain_id: str, request_fingerprint: str, expected_component_id: Any, expected_domain_id: Any, expected_request_fingerprint: Any) -> None:
    if not component_id or not domain_id or not request_fingerprint:
        raise ComponentFactHandoffError(
            "component fact handoff identity is incomplete", code="component_fact_identity_missing"
        )
    if expected_component_id and component_id != _text(expected_component_id, 96):
        raise ComponentFactHandoffError(
            "component fact handoff component mismatch", code="component_fact_component_mismatch"
        )
    if expected_domain_id and domain_id != _text(expected_domain_id, 64):
        raise ComponentFactHandoffError(
            "component fact handoff domain mismatch", code="component_fact_domain_mismatch"
        )
    if expected_request_fingerprint and request_fingerprint != _text(expected_request_fingerprint, 128):
        raise ComponentFactHandoffError(
            "component fact handoff request mismatch", code="component_fact_request_mismatch"
        )


def _mapping_values(value: Any) -> dict[str, Any]:
    return _safe_mapping(value)


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:32]:
        name = _text(key, 80)
        if not name or name.lower() in {"prompt", "raw_response", "api_key", "password", "token", "source_path"}:
            continue
        result[name] = _safe_value(item, depth=0)
    return result


def _safe_value(value: Any, *, depth: int) -> Any:
    if depth >= 3:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {_text(key, 80): _safe_value(item, depth=depth + 1) for key, item in list(value.items())[:24] if _text(key, 80)}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:320]
    return str(value)[:160]


def _safe_strings(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, 160)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _safe_details(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {"component_fact_handoff": project_component_fact_handoff(value)} if value.get("schema_version") else {}


def _assert_budget(value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise ComponentFactHandoffError(
            "component fact handoff exceeds max_bytes", code="component_fact_handoff_too_large"
        )


__all__ = [
    "COMPONENT_FACT_HANDOFF_SCHEMA_VERSION",
    "ComponentFactHandoffError",
    "build_component_fact_handoff",
    "normalize_component_fact_handoff",
    "project_component_fact_handoff",
    "request_facts_from_handoff",
]
