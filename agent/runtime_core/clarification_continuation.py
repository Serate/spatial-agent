"""Opaque, bounded continuation for component fact clarification.

The continuation carries no request text or model content.  Its signed
payload binds the original request/context fingerprint, the selected
component, the allowed field ids and an expiry time.  A resumed request must
provide only values for those declared fields; the caller then rebuilds the
normal context and planning gates.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Mapping
from typing import Any


CONTINUATION_SCHEMA_VERSION = "spatial-agent.component-clarification-continuation.v1"
COMPOSITE_CONTINUATION_SCHEMA_VERSION = "spatial-agent.composite-clarification-continuation.v1"
_MAX_TOKEN_BYTES = 8_192
_MAX_FIELD_VALUES = 16
_PRIVATE_KEYS = {"api_key", "password", "prompt", "raw_response", "secret", "token", "source_path"}


class ClarificationContinuationError(ValueError):
    """A continuation cannot be safely resumed."""

    def __init__(self, message: str, *, code: str = "continuation_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def issue_component_continuation(
    handoff: Mapping[str, Any], *, ttl_seconds: int = 1800, now: int | None = None
) -> dict[str, Any]:
    """Issue a restart-safe continuation descriptor for a required handoff."""

    if not isinstance(handoff, Mapping):
        raise ClarificationContinuationError("handoff is invalid", code="continuation_handoff_invalid")
    missing = [item for item in (handoff.get("missing_fields") or []) if isinstance(item, Mapping)]
    if not missing:
        raise ClarificationContinuationError("handoff has no missing fields", code="continuation_not_required")
    issued_at = int(time.time() if now is None else now)
    ttl = max(60, min(86_400, int(ttl_seconds)))
    payload = {
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "issued_at": issued_at,
        "expires_at": issued_at + ttl,
        "request_fingerprint": _text(handoff.get("request_fingerprint"), 128),
        "planner_selection_fingerprint": _text(handoff.get("planner_selection_fingerprint"), 128),
        "component_id": _text(handoff.get("component_id"), 96),
        "domain_id": _text(handoff.get("domain_id"), 64),
        "domain_ids": [
            _text(item, 64)
            for item in (handoff.get("domain_ids") or [handoff.get("domain_id")])[:8]
            if _text(item, 64)
        ],
        "capability_id": _text(handoff.get("capability_id"), 96),
        "field_ids": [_text(item.get("id"), 80) for item in missing if _text(item.get("id"), 80)],
        "field_kinds": {
            _text(item.get("id"), 80): _text(item.get("kind"), 32)
            for item in missing
            if _text(item.get("id"), 80)
        },
        "field_keys": {
            _text(item.get("id"), 80): [
                _text(value, 80) for value in (item.get("keys") or []) if _text(value, 80)
            ] or ([_text(item.get("key"), 80)] if _text(item.get("key"), 80) else [])
            for item in missing
            if _text(item.get("id"), 80)
        },
    }
    if not payload["request_fingerprint"] or not payload["component_id"] or not payload["domain_id"]:
        raise ClarificationContinuationError("handoff identity is incomplete", code="continuation_identity_missing")
    token = _encode(payload)
    return {
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "token": token,
        "issued_at": issued_at,
        "expires_at": issued_at + ttl,
        "component_id": payload["component_id"],
        "domain_id": payload["domain_id"],
        "domain_ids": list(payload.get("domain_ids") or [payload["domain_id"]])[:8],
        "capability_id": payload["capability_id"],
        "field_ids": payload["field_ids"][:16],
    }


def consume_component_continuation(
    token: Any,
    facts: Any,
    *,
    now: int | None = None,
    expected_request_fingerprint: str | None = None,
    expected_component_id: str | None = None,
    expected_domain_id: str | None = None,
) -> dict[str, Any]:
    """Validate a token and convert user facts to a domain-scoped override."""

    payload = _decode(token)
    current = int(time.time() if now is None else now)
    if current > int(payload["expires_at"]):
        raise ClarificationContinuationError("continuation has expired", code="continuation_expired")
    _match(payload, "request_fingerprint", expected_request_fingerprint, "continuation_request_mismatch")
    _match(payload, "component_id", expected_component_id, "continuation_component_mismatch")
    _match(payload, "domain_id", expected_domain_id, "continuation_domain_mismatch")
    normalized = _normalize_facts(facts, payload)
    return {
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "request_fingerprint": payload["request_fingerprint"],
        "planner_selection_fingerprint": payload.get("planner_selection_fingerprint"),
        "component_id": payload["component_id"],
        "domain_id": payload["domain_id"],
        "domain_ids": list(payload.get("domain_ids") or [payload["domain_id"]])[:8],
        "capability_id": payload.get("capability_id"),
        "field_ids": list(payload.get("field_ids") or [])[:16],
        "facts": normalized,
    }


def issue_composite_continuation(
    handoff: Mapping[str, Any], *, ttl_seconds: int = 1800, now: int | None = None
) -> dict[str, Any]:
    """Issue one continuation bound to a complete selected component set."""

    if not isinstance(handoff, Mapping):
        raise ClarificationContinuationError(
            "composite handoff is invalid", code="continuation_handoff_invalid"
        )
    raw_components = handoff.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ClarificationContinuationError(
            "composite handoff has no components", code="continuation_handoff_invalid"
        )
    component_payload: list[dict[str, Any]] = []
    component_ids: list[str] = []
    domain_ids: list[str] = []
    for raw in raw_components[:8]:
        if not isinstance(raw, Mapping):
            raise ClarificationContinuationError(
                "composite component is invalid", code="continuation_handoff_invalid"
            )
        component_id = _text(raw.get("component_id"), 96)
        domain_id = _text(raw.get("domain_id"), 64)
        capability_id = _text(raw.get("capability_id"), 96)
        if not component_id or not domain_id or not capability_id or component_id in component_ids:
            raise ClarificationContinuationError(
                "composite component identity is invalid",
                code="continuation_identity_missing",
            )
        component_ids.append(component_id)
        if domain_id not in domain_ids:
            domain_ids.append(domain_id)
        fields = [item for item in (raw.get("missing_fields") or []) if isinstance(item, Mapping)]
        component_payload.append(
            {
                "component_id": component_id,
                "domain_id": domain_id,
                "capability_id": capability_id,
                "field_ids": [
                    _text(item.get("id"), 80)
                    for item in fields
                    if _text(item.get("id"), 80)
                ][:16],
                "field_kinds": {
                    _text(item.get("id"), 80): _text(item.get("kind"), 32)
                    for item in fields
                    if _text(item.get("id"), 80)
                },
                "field_keys": {
                    _text(item.get("id"), 80): (
                        [_text(value, 80) for value in (item.get("keys") or []) if _text(value, 80)]
                        or ([_text(item.get("key"), 80)] if _text(item.get("key"), 80) else [])
                    )
                    for item in fields
                    if _text(item.get("id"), 80)
                },
            }
        )
    if not any(item.get("field_ids") for item in component_payload):
        raise ClarificationContinuationError(
            "composite handoff has no missing fields", code="continuation_not_required"
        )
    issued_at = int(time.time() if now is None else now)
    ttl = max(60, min(86_400, int(ttl_seconds)))
    payload = {
        "schema_version": COMPOSITE_CONTINUATION_SCHEMA_VERSION,
        "issued_at": issued_at,
        "expires_at": issued_at + ttl,
        "request_fingerprint": _text(handoff.get("request_fingerprint"), 128),
        "planner_selection_fingerprint": _text(
            handoff.get("planner_selection_fingerprint"), 128
        ),
        "component_ids": component_ids,
        "domain_ids": domain_ids,
        "components": component_payload,
    }
    if not payload["request_fingerprint"] or not payload["planner_selection_fingerprint"]:
        raise ClarificationContinuationError(
            "composite handoff identity is incomplete",
            code="continuation_identity_missing",
        )
    token = _encode(payload)
    return {
        "schema_version": COMPOSITE_CONTINUATION_SCHEMA_VERSION,
        "token": token,
        "issued_at": issued_at,
        "expires_at": issued_at + ttl,
        "component_ids": component_ids,
        "domain_ids": domain_ids,
    }


def consume_composite_continuation(
    token: Any, facts: Any, *, now: int | None = None
) -> dict[str, Any]:
    """Validate grouped facts for a multi-component continuation."""

    payload = _decode_token(
        token, allowed_schemas={COMPOSITE_CONTINUATION_SCHEMA_VERSION}
    )
    current = int(time.time() if now is None else now)
    if current > int(payload["expires_at"]):
        raise ClarificationContinuationError(
            "continuation has expired", code="continuation_expired"
        )
    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ClarificationContinuationError(
            "composite continuation components are invalid",
            code="continuation_identity_missing",
        )
    descriptors = {
        str(item.get("component_id")): item
        for item in raw_components
        if isinstance(item, Mapping) and str(item.get("component_id") or "")
    }
    source = facts.get("components") if isinstance(facts, Mapping) else None
    if source is None and len(descriptors) == 1 and isinstance(facts, Mapping):
        source = {next(iter(descriptors)): facts}
    if not isinstance(source, Mapping):
        raise ClarificationContinuationError(
            "supplement components must be an object",
            code="continuation_facts_invalid",
        )
    facts_by_component: dict[str, dict[str, Any]] = {}
    for raw_id, raw_facts in list(source.items())[:8]:
        component_id = _text(raw_id, 96)
        descriptor = descriptors.get(component_id)
        if descriptor is None:
            raise ClarificationContinuationError(
                "supplement component is not declared by the handoff",
                code="continuation_component_unknown",
            )
        facts_by_component[component_id] = _normalize_facts(raw_facts, descriptor)
    if not facts_by_component:
        raise ClarificationContinuationError(
            "supplement facts are empty", code="continuation_facts_empty"
        )
    domain_ids = [
        _text(item, 64)
        for item in (payload.get("domain_ids") or [])[:8]
        if _text(item, 64)
    ]
    return {
        "schema_version": COMPOSITE_CONTINUATION_SCHEMA_VERSION,
        "request_fingerprint": _text(payload.get("request_fingerprint"), 128),
        "planner_selection_fingerprint": _text(
            payload.get("planner_selection_fingerprint"), 128
        ),
        "component_ids": [
            _text(item, 96)
            for item in (payload.get("component_ids") or [])[:8]
            if _text(item, 96)
        ],
        "domain_ids": domain_ids,
        "components": [
            {
                "component_id": _text(item.get("component_id"), 96),
                "domain_id": _text(item.get("domain_id"), 64),
                "capability_id": _text(item.get("capability_id"), 96),
            }
            for item in raw_components
            if isinstance(item, Mapping)
        ][:8],
        "facts_by_component": facts_by_component,
        "fact_overrides": _merge_facts_by_domain(facts_by_component, descriptors),
    }


def consume_fact_continuation(token: Any, facts: Any) -> dict[str, Any]:
    """Consume either the M292 single-component or M293 composite token."""

    payload = _decode_token(
        token,
        allowed_schemas={
            CONTINUATION_SCHEMA_VERSION,
            COMPOSITE_CONTINUATION_SCHEMA_VERSION,
        },
    )
    if payload.get("schema_version") == COMPOSITE_CONTINUATION_SCHEMA_VERSION:
        return consume_composite_continuation(token, facts)
    return consume_component_continuation(token, facts)


def _normalize_facts(value: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ClarificationContinuationError("supplement facts must be an object", code="continuation_facts_invalid")
    source = value.get("facts") if isinstance(value.get("facts"), Mapping) else value
    allowed_ids = set(str(item) for item in (payload.get("field_ids") or []))
    kinds = payload.get("field_kinds") if isinstance(payload.get("field_kinds"), Mapping) else {}
    field_keys = payload.get("field_keys") if isinstance(payload.get("field_keys"), Mapping) else {}
    result = {"entities": {}, "datasets": [], "constraints": {}}
    for key, raw in source.items():
        name = str(key or "").strip()[:80]
        if not name or name.lower() in _PRIVATE_KEYS:
            raise ClarificationContinuationError("supplement contains an unsupported field", code="continuation_field_unknown")
        if name in {"entities", "datasets", "constraints"}:
            if name == "entities":
                if not isinstance(raw, Mapping):
                    raise ClarificationContinuationError("entities supplement must be an object", code="continuation_field_type_invalid")
                for entity_key, entity_value in list(raw.items())[:16]:
                    _put_entity(result, str(entity_key), entity_value)
            elif name == "datasets":
                result["datasets"] = _string_values(raw)
            else:
                if not isinstance(raw, Mapping):
                    raise ClarificationContinuationError("constraints supplement must be an object", code="continuation_field_type_invalid")
                for constraint_key, constraint_value in list(raw.items())[:16]:
                    _put_constraint(result, str(constraint_key), constraint_value)
            continue
        if name not in allowed_ids:
            raise ClarificationContinuationError("supplement field is not declared by the handoff", code="continuation_field_unknown")
        kind = str(kinds.get(name) or "")
        if kind == "entity":
            keys = field_keys.get(name) or [name]
            for entity_key in list(keys)[:4]:
                _put_entity(result, str(entity_key), raw)
        elif kind == "dataset":
            result["datasets"] = _string_values(raw)
        elif kind == "constraint":
            if isinstance(raw, Mapping):
                for constraint_key, constraint_value in list(raw.items())[:16]:
                    _put_constraint(result, str(constraint_key), constraint_value)
            else:
                keys = field_keys.get(name) or [name]
                for constraint_key in list(keys)[:8]:
                    _put_constraint(result, str(constraint_key), raw)
        else:
            raise ClarificationContinuationError("supplement field kind is unknown", code="continuation_field_type_invalid")
    if not result["entities"] and not result["datasets"] and not result["constraints"]:
        raise ClarificationContinuationError("supplement facts are empty", code="continuation_facts_empty")
    return result


def _decode_token(token: Any, *, allowed_schemas: set[str]) -> dict[str, Any]:
    text = str(token or "").strip()
    if not text or len(text.encode("utf-8")) > _MAX_TOKEN_BYTES:
        raise ClarificationContinuationError("continuation token is invalid", code="continuation_token_invalid")
    parts = text.split(".")
    if len(parts) != 2:
        raise ClarificationContinuationError("continuation token is invalid", code="continuation_token_invalid")
    try:
        encoded = base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        supplied = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        expected = hmac.new(_signing_key(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied, expected):
            raise ClarificationContinuationError("continuation token signature is invalid", code="continuation_token_tampered")
        payload = json.loads(encoded.decode("utf-8"))
    except ClarificationContinuationError:
        raise
    except Exception as exc:
        raise ClarificationContinuationError("continuation token is invalid", code="continuation_token_invalid") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") not in allowed_schemas:
        raise ClarificationContinuationError("continuation token schema is invalid", code="continuation_schema_invalid")
    schema = payload.get("schema_version")
    required = (
        ("request_fingerprint", "planner_selection_fingerprint", "component_ids", "components", "expires_at")
        if schema == COMPOSITE_CONTINUATION_SCHEMA_VERSION
        else ("request_fingerprint", "component_id", "domain_id", "expires_at", "field_ids", "field_kinds")
    )
    for key in required:
        if key not in payload:
            raise ClarificationContinuationError("continuation token identity is incomplete", code="continuation_identity_missing")
    return dict(payload)


def _decode(token: Any) -> dict[str, Any]:
    return _decode_token(token, allowed_schemas={CONTINUATION_SCHEMA_VERSION})


def _merge_facts_by_domain(
    facts_by_component: Mapping[str, Mapping[str, Any]],
    descriptors: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for component_id, facts in facts_by_component.items():
        descriptor = descriptors.get(component_id) or {}
        domain_id = _text(descriptor.get("domain_id"), 64)
        if not domain_id:
            continue
        target = result.setdefault(
            domain_id, {"entities": {}, "datasets": [], "constraints": {}}
        )
        target["entities"].update(facts.get("entities") or {})
        for value in facts.get("datasets") or []:
            if value not in target["datasets"]:
                target["datasets"].append(value)
        target["constraints"].update(facts.get("constraints") or {})
    return result


def _encode(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(_signing_key(), encoded, hashlib.sha256).digest()).decode("ascii").rstrip("=")
    return body + "." + signature


def _signing_key() -> bytes:
    configured = os.environ.get("SPATIAL_AGENT_CONTINUATION_SECRET", "")
    if configured:
        return configured.encode("utf-8")[:512]
    # The fallback is deliberately only an integrity guard for local/demo
    # deployments. Production deployments should inject a stable secret.
    return b"spatial-agent-component-continuation-v1"


def _match(payload: Mapping[str, Any], key: str, expected: Any, code: str) -> None:
    if expected is not None and str(payload.get(key) or "") != str(expected or ""):
        raise ClarificationContinuationError("continuation identity does not match", code=code)


def _put_entity(result: dict[str, Any], key: str, value: Any) -> None:
    name = str(key or "").strip()[:80]
    if not name or isinstance(value, (Mapping, list, tuple, set)) and not isinstance(value, str):
        raise ClarificationContinuationError("entity fact type is invalid", code="continuation_field_type_invalid")
    result["entities"][name] = str(value).strip()[:320]


def _put_constraint(result: dict[str, Any], key: str, value: Any) -> None:
    name = str(key or "").strip()[:80]
    if not name or name.lower() in _PRIVATE_KEYS or isinstance(value, (Mapping, list, tuple, set)) and not isinstance(value, str):
        if isinstance(value, Mapping):
            safe = {str(k)[:80]: v for k, v in list(value.items())[:16]}
            result["constraints"].update(safe)
            return
        raise ClarificationContinuationError("constraint fact type is invalid", code="continuation_field_type_invalid")
    result["constraints"][name] = value if not isinstance(value, str) else value[:320]


def _string_values(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        raise ClarificationContinuationError("dataset fact type is invalid", code="continuation_field_type_invalid")
    result: list[str] = []
    for item in list(values)[:_MAX_FIELD_VALUES]:
        text = str(item or "").strip()[:160]
        if text and text not in result:
            result.append(text)
    if not result:
        raise ClarificationContinuationError("dataset facts are empty", code="continuation_facts_empty")
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = [
    "COMPOSITE_CONTINUATION_SCHEMA_VERSION",
    "CONTINUATION_SCHEMA_VERSION",
    "ClarificationContinuationError",
    "consume_composite_continuation",
    "consume_component_continuation",
    "consume_fact_continuation",
    "issue_composite_continuation",
    "issue_component_continuation",
]
