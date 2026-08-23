"""Versioned, domain-neutral contract for all user/runtime interactions.

The contract is deliberately a pure projection.  It answers two questions:
what is the authoritative subject now, and which bounded commands may be
submitted next?  Stateful loading, compare-and-swap and dispatch live in
``interaction_host``; transports and Domain Packs must not recreate policy.

Legacy lifecycle, workflow-selection and Domain-routing projections remain
readable inputs during migration.  Their public aliases are derived from this
contract so ``interaction.actions`` is the single authorization source.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .contract_versions import (
    INTERACTION_ACTION_SCHEMA_VERSION,
    INTERACTION_COMMAND_SCHEMA_VERSION,
    INTERACTION_SCHEMA_VERSION,
)


INTERACTION_STATES = frozenset(
    {
        "candidate_selection",
        "facts_required",
        "confirmation_required",
        "repairable",
        "recoverable",
        "processing",
        "completed",
        "rejected",
        "cancelled",
        "failed",
        "unavailable",
    }
)
INTERACTION_ACTION_IDS = frozenset(
    {
        "select_domain",
        "select_capability",
        "select_workflow",
        "provide_facts",
        "preview",
        "repair",
        "confirm",
        "reject",
        "retry",
        "recover",
        "cancel",
        "rebuild_from_result",
        "start_new_run",
    }
)

_MAX_ACTIONS = 12
_MAX_ITEMS = 24
_MAX_ID = 160
_MAX_TEXT = 320
_MAX_SCHEMA_DEPTH = 4


class InteractionContractError(ValueError):
    """Stable validation failure at the interaction boundary."""

    def __init__(self, message: str, *, code: str = "interaction_invalid"):
        self.code = str(code or "interaction_invalid")[:64]
        super().__init__(message)


def project_interaction(
    source: Any,
    *,
    prefer_existing: bool = True,
) -> dict[str, Any]:
    """Project a run, result, routing response, or legacy interaction.

    This function performs no I/O and trusts no caller-provided action list
    without normalizing every action and input schema.  Projection precedence
    follows the user journey: Domain routing, workflow/facts/confirmation,
    then the generic lifecycle.
    """

    value = _mapping(source)
    existing = _interaction_value(value) if prefer_existing else None
    if existing is not None:
        return normalize_interaction(existing)

    nested = _mapping(value.get("result"))
    routing = _legacy(value, nested, "domain_routing_interaction")
    selection = _legacy(value, nested, "selection_interaction")
    lifecycle = _legacy(value, nested, "lifecycle")
    routing_evidence = _legacy(value, nested, "domain_routing_evidence")
    receipt = _legacy(value, nested, "action_receipt")

    if _is_schema(routing, "spatial-agent.domain-routing-interaction.v1"):
        return _project_routing(value, routing)
    if _is_schema(selection, "spatial-agent.selection-interaction.v1"):
        return _project_selection(
            value,
            selection,
            lifecycle=lifecycle,
            routing_evidence=routing_evidence,
            receipt=receipt,
        )
    if lifecycle:
        return _project_lifecycle(
            value,
            lifecycle,
            routing_evidence=routing_evidence,
            receipt=receipt,
        )
    return unavailable_interaction("interaction_source_unavailable")


def normalize_interaction(value: Any) -> dict[str, Any]:
    """Strictly normalize one current contract; future schemas fail closed."""

    if not isinstance(value, Mapping):
        return unavailable_interaction("interaction_missing")
    if value.get("schema_version") != INTERACTION_SCHEMA_VERSION:
        return unavailable_interaction("interaction_unknown_schema")
    try:
        subject = _normalize_subject(value.get("subject"))
        state = _token(value.get("state"), 48)
        if state not in INTERACTION_STATES:
            raise InteractionContractError("interaction state is invalid")
        raw_actions = value.get("actions")
        if not isinstance(raw_actions, list):
            raise InteractionContractError("interaction actions must be a list")
        actions = []
        seen = set()
        for raw in raw_actions[:_MAX_ACTIONS]:
            action = normalize_interaction_action(raw)
            if action["id"] not in seen:
                actions.append(action)
                seen.add(action["id"])
        blocked = []
        for raw in list(value.get("blocked_actions") or ())[:_MAX_ACTIONS]:
            action_id = _canonical_action_id(raw.get("id") if isinstance(raw, Mapping) else raw)
            if action_id and action_id not in blocked:
                blocked.append(action_id)
        content = _bounded_content(value.get("content"))
        lineage = _bounded_content(value.get("lineage"))
        receipt = value.get("receipt") if isinstance(value.get("receipt"), Mapping) else None
        result = {
            "schema_version": INTERACTION_SCHEMA_VERSION,
            "available": bool(value.get("available")),
            "actionable": bool(actions) and state not in {"completed", "rejected", "cancelled", "failed", "unavailable"},
            "subject": subject,
            "kind": _token(value.get("kind"), 64) or "lifecycle",
            "state": state,
            "phase": _token(value.get("phase"), 32) or "unknown",
            "status": _token(value.get("status"), 32).upper() or "UNKNOWN",
            "reason_code": _token(value.get("reason_code"), 96) or "interaction_unavailable",
            "actions": actions,
            # Read-only migration alias. Authorization always reads actions.
            "allowed_actions": [item["id"] for item in actions],
            "blocked_actions": blocked,
            "content": content,
            "receipt": _bounded_content(receipt) if receipt is not None else None,
            "lineage": lineage,
        }
        if not result["available"]:
            result["actionable"] = False
            result["actions"] = []
            result["allowed_actions"] = []
        return result
    except InteractionContractError as exc:
        return unavailable_interaction(exc.code)


def normalize_interaction_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InteractionContractError("interaction action must be an object")
    action_id = _canonical_action_id(value.get("id"))
    if not action_id:
        raise InteractionContractError(
            "interaction action id is invalid", code="interaction_action_invalid"
        )
    schema = normalize_action_input_schema(
        value.get("input_schema") or _default_input_schema(action_id)
    )
    return {
        "schema_version": INTERACTION_ACTION_SCHEMA_VERSION,
        "id": action_id,
        "kind": _action_kind(action_id),
        "label": _text(value.get("label"), _action_label(action_id), 80),
        "description": _text(value.get("description"), "", _MAX_TEXT),
        "input_schema": schema,
        "idempotency_required": value.get("idempotency_required") is not False,
    }


def normalize_action_input_schema(value: Any, *, _depth: int = 0) -> dict[str, Any]:
    """Normalize the supported, bounded JSON-Schema subset."""

    if _depth > _MAX_SCHEMA_DEPTH or not isinstance(value, Mapping):
        raise InteractionContractError(
            "action input schema is invalid", code="interaction_action_schema_invalid"
        )
    schema_type = _token(value.get("type"), 16) or "object"
    if schema_type not in {"object", "string", "number", "integer", "boolean", "array"}:
        raise InteractionContractError(
            "action input schema type is unsupported",
            code="interaction_action_schema_invalid",
        )
    result: dict[str, Any] = {"type": schema_type}
    if schema_type == "object":
        raw_properties = value.get("properties") or {}
        if not isinstance(raw_properties, Mapping):
            raise InteractionContractError(
                "action schema properties must be an object",
                code="interaction_action_schema_invalid",
            )
        properties = {}
        for raw_name, raw_spec in list(raw_properties.items())[:_MAX_ITEMS]:
            name = _token(raw_name, 64)
            if name and name not in properties:
                properties[name] = normalize_action_input_schema(
                    raw_spec, _depth=_depth + 1
                )
                if isinstance(raw_spec, Mapping):
                    for key, limit in (("title", 80), ("description", 240)):
                        text = _text(raw_spec.get(key), "", limit)
                        if text:
                            properties[name][key] = text
                    if isinstance(raw_spec.get("enum"), list):
                        properties[name]["enum"] = [
                            item for item in raw_spec["enum"][:_MAX_ITEMS]
                            if isinstance(item, (str, int, float, bool)) or item is None
                        ]
        required = []
        for item in list(value.get("required") or ())[:_MAX_ITEMS]:
            name = _token(item, 64)
            if name in properties and name not in required:
                required.append(name)
        result.update(
            {
                "properties": properties,
                "required": required,
                "additionalProperties": value.get("additionalProperties") is True,
            }
        )
    elif schema_type == "array":
        result["items"] = normalize_action_input_schema(
            value.get("items") or {"type": "string"}, _depth=_depth + 1
        )
        _copy_int_bounds(value, result, ("minItems", "maxItems"), maximum=128)
    else:
        if isinstance(value.get("enum"), list):
            result["enum"] = [
                item for item in value["enum"][:_MAX_ITEMS]
                if isinstance(item, (str, int, float, bool)) or item is None
            ]
        if schema_type == "string":
            _copy_int_bounds(value, result, ("minLength", "maxLength"), maximum=10000)
        if schema_type in {"number", "integer"}:
            for key in ("minimum", "maximum"):
                number = value.get(key)
                if isinstance(number, (int, float)) and not isinstance(number, bool):
                    result[key] = number
    return result


def normalize_interaction_command(value: Any) -> dict[str, Any]:
    """Validate command envelope shape without authorizing it."""

    if not isinstance(value, Mapping):
        raise InteractionContractError(
            "interaction command must be an object",
            code="interaction_command_invalid",
        )
    if value.get("schema_version") != INTERACTION_COMMAND_SCHEMA_VERSION:
        raise InteractionContractError(
            "interaction command schema is unsupported",
            code="interaction_command_unknown_schema",
        )
    action_id = _canonical_action_id(value.get("action_id"))
    if not action_id:
        raise InteractionContractError(
            "interaction command action_id is invalid",
            code="interaction_action_invalid",
        )
    payload = value.get("input")
    if not isinstance(payload, Mapping):
        raise InteractionContractError(
            "interaction command input must be an object",
            code="interaction_input_invalid",
        )
    _validate_input_bounds(payload)
    key = _text(value.get("idempotency_key"), "", 128)
    if not key or "/" in key or "\\" in key:
        raise InteractionContractError(
            "interaction command requires a safe idempotency_key",
            code="interaction_idempotency_key_invalid",
        )
    return {
        "schema_version": INTERACTION_COMMAND_SCHEMA_VERSION,
        "subject": _normalize_subject(value.get("subject")),
        "action_id": action_id,
        "input": deepcopy(dict(payload)),
        "idempotency_key": key,
    }


def validate_interaction_command(
    command: Any,
    interaction: Any,
) -> dict[str, Any]:
    """Authorize a command against a freshly loaded interaction contract."""

    normalized_command = normalize_interaction_command(command)
    authoritative = normalize_interaction(interaction)
    if not authoritative.get("available"):
        raise InteractionContractError(
            "authoritative interaction is unavailable",
            code="interaction_unavailable",
        )
    if normalized_command["subject"] != authoritative["subject"]:
        raise InteractionContractError(
            "interaction subject or revision is stale",
            code="interaction_revision_conflict",
        )
    action = next(
        (
            item
            for item in authoritative.get("actions", ())
            if item.get("id") == normalized_command["action_id"]
        ),
        None,
    )
    if action is None:
        raise InteractionContractError(
            "interaction action is not allowed",
            code="interaction_action_not_allowed",
        )
    validate_action_input(normalized_command["input"], action["input_schema"])
    normalized_command["action"] = action
    return normalized_command


def validate_action_input(value: Any, schema: Any, *, _path: str = "$", _depth: int = 0) -> None:
    """Validate an input using the same bounded subset exposed to clients."""

    if _depth > _MAX_SCHEMA_DEPTH:
        raise InteractionContractError(
            "interaction input is too deeply nested", code="interaction_input_invalid"
        )
    spec = normalize_action_input_schema(schema)
    kind = spec["type"]
    if kind == "object":
        if not isinstance(value, Mapping):
            raise InteractionContractError(
                _path + " must be an object", code="interaction_input_invalid"
            )
        properties = spec["properties"]
        missing = [name for name in spec["required"] if name not in value]
        if missing:
            raise InteractionContractError(
                "interaction input is missing: " + ", ".join(missing),
                code="interaction_input_required",
            )
        unknown = [name for name in value if name not in properties]
        if unknown and not spec["additionalProperties"]:
            raise InteractionContractError(
                "interaction input contains unknown fields: " + ", ".join(map(str, unknown[:8])),
                code="interaction_input_additional_property",
            )
        for name, item in value.items():
            if name in properties:
                validate_action_input(
                    item,
                    properties[name],
                    _path=_path + "." + str(name),
                    _depth=_depth + 1,
                )
        return
    if kind == "string":
        valid = isinstance(value, str)
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        valid = isinstance(value, list)
    if not valid:
        raise InteractionContractError(
            _path + " has the wrong type", code="interaction_input_invalid"
        )
    if "enum" in spec and value not in spec["enum"]:
        raise InteractionContractError(
            _path + " is outside the allowed values", code="interaction_input_enum"
        )
    if kind == "string":
        if len(value) < spec.get("minLength", 0) or len(value) > spec.get("maxLength", 10000):
            raise InteractionContractError(
                _path + " has an invalid length", code="interaction_input_invalid"
            )
    elif kind in {"number", "integer"}:
        if "minimum" in spec and value < spec["minimum"]:
            raise InteractionContractError(_path + " is below minimum", code="interaction_input_invalid")
        if "maximum" in spec and value > spec["maximum"]:
            raise InteractionContractError(_path + " is above maximum", code="interaction_input_invalid")
    elif kind == "array":
        if len(value) < spec.get("minItems", 0) or len(value) > spec.get("maxItems", 128):
            raise InteractionContractError(_path + " has an invalid item count", code="interaction_input_invalid")
        for index, item in enumerate(value):
            validate_action_input(item, spec["items"], _path=f"{_path}[{index}]", _depth=_depth + 1)


def legacy_selection_interaction(
    interaction: Any,
    template: Any = None,
) -> dict[str, Any]:
    """Derive the legacy workflow-selection alias from canonical actions."""

    canonical = normalize_interaction(interaction)
    result = deepcopy(dict(template)) if isinstance(template, Mapping) else {}
    actions = canonical.get("actions", ())
    result["allowed_actions"] = [item["id"] for item in actions]
    result["actions"] = [
        {
            "schema_version": "spatial-agent.recovery-action.v1",
            "id": item["id"],
            "kind": item["kind"],
            "state": "available",
            "requires_receipt": item["idempotency_required"],
            "idempotency_required": item["idempotency_required"],
            **({"subject_id": canonical["subject"]["current"]["id"]} if canonical["subject"]["current"]["kind"] == "run" else {}),
        }
        for item in actions
    ]
    blocked = list(canonical.get("blocked_actions") or ())
    if blocked or "blocked_actions" in result:
        result["blocked_actions"] = blocked
    return result


def legacy_domain_routing_interaction(
    interaction: Any,
    template: Any = None,
) -> dict[str, Any]:
    """Derive the legacy Domain-routing alias from canonical actions."""

    canonical = normalize_interaction(interaction)
    result = deepcopy(dict(template)) if isinstance(template, Mapping) else {}
    actions = canonical.get("actions", ())
    result["allowed_actions"] = [item["id"] for item in actions]
    result["actions"] = [
        {
            "id": item["id"],
            "label": item["label"],
            "description": item["description"],
            "input_schema": deepcopy(item["input_schema"]),
        }
        for item in actions
    ]
    return result


def unavailable_interaction(reason_code: str = "interaction_unavailable") -> dict[str, Any]:
    return {
        "schema_version": INTERACTION_SCHEMA_VERSION,
        "available": False,
        "actionable": False,
        "subject": {
            "root": {"kind": "unknown", "id": "unknown"},
            "current": {"kind": "unknown", "id": "unknown"},
            "revision": 0,
        },
        "kind": "unavailable",
        "state": "unavailable",
        "phase": "unknown",
        "status": "UNKNOWN",
        "reason_code": _token(reason_code, 96) or "interaction_unavailable",
        "actions": [],
        "allowed_actions": [],
        "blocked_actions": [],
        "content": {},
        "receipt": None,
        "lineage": {},
    }


def _project_routing(source: Mapping[str, Any], routing: Mapping[str, Any]) -> dict[str, Any]:
    decision_id = _identity(routing.get("decision_id"), "unknown")
    domain_routing = _mapping(source.get("domain_routing"))
    parent_id = _identity(domain_routing.get("parent_decision_id"), "")
    root_id = parent_id or decision_id
    candidates = _bounded_list(routing.get("candidates"))
    actions = _actions_from_legacy(routing.get("actions"), routing.get("allowed_actions"), candidates=candidates)
    state = _token(routing.get("state"), 48) or "unavailable"
    return normalize_interaction(
        {
            "schema_version": INTERACTION_SCHEMA_VERSION,
            "available": state != "unavailable",
            "subject": {
                "root": {"kind": "routing_decision", "id": root_id},
                "current": {"kind": "routing_decision", "id": decision_id},
                "revision": 2 if parent_id else 1,
            },
            "kind": "domain_selection",
            "state": state,
            "phase": "routing",
            "status": "NEEDS_CLARIFICATION" if state == "candidate_selection" else "COMPLETED",
            "reason_code": routing.get("reason_code"),
            "actions": actions,
            "blocked_actions": routing.get("blocked_actions") or [],
            "content": {"candidates": candidates, "missing_fields": []},
            "receipt": None,
            "lineage": {
                "root_subject_id": root_id,
                "current_subject_id": decision_id,
            },
        }
    )


def _project_selection(
    source: Mapping[str, Any],
    selection: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, Any],
    routing_evidence: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    state = _token(selection.get("state"), 48) or "unavailable"
    run_id = _identity(
        source.get("run_id") or selection.get("subject_id") or _mapping(source.get("result")).get("run_id"),
        "unknown",
    )
    root_id, route_depth = _routing_root(routing_evidence, run_id)
    content = {
        "candidates": _selection_candidates(selection),
        "missing_fields": _bounded_list(selection.get("missing_fields")),
        "selection": _bounded_content(selection.get("selection")),
        "decision": _bounded_content(selection.get("decision")),
        "evidence_action_guidance": _bounded_content(selection.get("evidence_action_guidance")),
    }
    actions = _actions_from_legacy(
        selection.get("actions"), selection.get("allowed_actions"), candidates=content["candidates"]
    )
    phase = _token(_mapping(selection.get("lifecycle")).get("phase"), 32)
    if not phase:
        phase = "planning" if state in {"candidate_selection", "facts_required", "confirmation_required", "repairable"} else "execution"
    return normalize_interaction(
        {
            "schema_version": INTERACTION_SCHEMA_VERSION,
            "available": selection.get("available") is True,
            "subject": {
                "root": {"kind": "routing_decision" if root_id != run_id else "run", "id": root_id},
                "current": {"kind": "run", "id": run_id},
                "revision": route_depth + _state_revision(state, receipt),
                **({"domain_id": _identity(source.get("domain_id"), "unknown")} if source.get("domain_id") else {}),
            },
            "kind": _interaction_kind(state),
            "state": state,
            "phase": phase,
            "status": selection.get("status") or lifecycle.get("status") or source.get("status"),
            "reason_code": selection.get("reason_code"),
            "actions": actions,
            "blocked_actions": selection.get("blocked_actions") or [],
            "content": content,
            "receipt": receipt or selection.get("action_receipt"),
            "lineage": {
                "root_subject_id": root_id,
                "current_subject_id": run_id,
                "repair_lineage": _bounded_list(selection.get("repair_lineage")),
            },
        }
    )


def _project_lifecycle(
    source: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    *,
    routing_evidence: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    state_map = {
        "awaiting_confirmation": "confirmation_required",
        "clarification_required": "facts_required",
        "planning": "processing",
        "executing": "processing",
    }
    lifecycle_state = _token(lifecycle.get("state"), 48) or "unavailable"
    state = state_map.get(lifecycle_state, lifecycle_state)
    run_id = _identity(source.get("run_id") or lifecycle.get("subject_id"), "unknown")
    root_id, route_depth = _routing_root(routing_evidence, run_id)
    actions = _actions_from_legacy(lifecycle.get("actions"), lifecycle.get("allowed_actions"))
    return normalize_interaction(
        {
            "schema_version": INTERACTION_SCHEMA_VERSION,
            "available": lifecycle_state != "unavailable",
            "subject": {
                "root": {"kind": "routing_decision" if root_id != run_id else "run", "id": root_id},
                "current": {"kind": "run", "id": run_id},
                "revision": route_depth + _state_revision(state, receipt),
            },
            "kind": _interaction_kind(state),
            "state": state,
            "phase": lifecycle.get("phase"),
            "status": lifecycle.get("status") or source.get("status"),
            "reason_code": lifecycle.get("reason_code"),
            "actions": actions,
            "blocked_actions": lifecycle.get("blocked_actions") or [],
            "content": {},
            "receipt": receipt,
            "lineage": lifecycle.get("lineage") or {},
        }
    )


def _actions_from_legacy(raw_actions: Any, allowed: Any, *, candidates: Any = None) -> list[dict[str, Any]]:
    supplied = {}
    if isinstance(raw_actions, list):
        for item in raw_actions[:_MAX_ACTIONS]:
            if isinstance(item, Mapping):
                action_id = _canonical_action_id(item.get("id"))
                if action_id:
                    supplied[action_id] = item
    ids = []
    values = allowed if isinstance(allowed, (list, tuple)) else supplied.keys()
    for raw in list(values)[:_MAX_ACTIONS]:
        action_id = _canonical_action_id(raw)
        if action_id and action_id not in ids:
            ids.append(action_id)
    result = []
    for action_id in ids:
        item = dict(supplied.get(action_id) or {})
        item["id"] = action_id
        if not item.get("input_schema"):
            item["input_schema"] = _default_input_schema(action_id, candidates=candidates)
        result.append(item)
    return result


def _default_input_schema(action_id: str, *, candidates: Any = None) -> dict[str, Any]:
    empty = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    candidate_ids = []
    for item in candidates if isinstance(candidates, list) else []:
        if isinstance(item, Mapping):
            candidate_id = _identity(item.get("id") or item.get("capability_id") or item.get("domain_id"), "")
            if candidate_id and candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
    if action_id == "select_domain":
        return {"type": "object", "properties": {"domain_id": {"type": "string", "enum": candidate_ids}}, "required": ["domain_id"], "additionalProperties": False}
    continuation = {
        "require_confirmation": {"type": "boolean"},
        "export_artifact": {"type": "boolean"},
        "export_geojson": {"type": "boolean"},
        "geojson_max_features": {"type": "integer", "minimum": 1, "maximum": 10000},
    }
    if action_id == "select_capability":
        spec: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": 96}
        if candidate_ids:
            spec["enum"] = candidate_ids
        return {"type": "object", "properties": {"capability_id": spec, **continuation}, "required": ["capability_id"], "additionalProperties": False}
    if action_id == "select_workflow":
        return {"type": "object", "properties": {"workflow": {"type": "object", "additionalProperties": True}, **continuation}, "required": ["workflow"], "additionalProperties": False}
    if action_id == "provide_facts":
        return {"type": "object", "properties": {"facts": {"type": "object", "additionalProperties": True}, "capability_id": {"type": "string", "maxLength": 96}, "workflow": {"type": "object", "additionalProperties": True}, **continuation}, "required": ["facts"], "additionalProperties": False}
    if action_id in {"preview", "repair"}:
        return {"type": "object", "properties": {"workflow": {"type": "object", "additionalProperties": True}}, "required": [], "additionalProperties": False}
    if action_id in {"confirm", "reject"}:
        return {"type": "object", "properties": {"expected_version": {"type": "integer", "minimum": 0}}, "required": [], "additionalProperties": False}
    if action_id in {"retry", "recover"}:
        return {"type": "object", "properties": {"export_artifact": {"type": "boolean"}, "export_geojson": {"type": "boolean"}, "geojson_max_features": {"type": "integer", "minimum": 1, "maximum": 10000}}, "required": [], "additionalProperties": False}
    return empty


def _normalize_subject(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InteractionContractError(
            "interaction subject is missing", code="interaction_subject_invalid"
        )
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise InteractionContractError(
            "interaction revision is invalid", code="interaction_subject_invalid"
        )
    result = {
        "root": _subject_ref(value.get("root")),
        "current": _subject_ref(value.get("current")),
        "revision": min(revision, 1_000_000),
    }
    domain_id = _identity(value.get("domain_id"), "")
    if domain_id:
        result["domain_id"] = domain_id
    return result


def _subject_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise InteractionContractError(
            "interaction subject reference is invalid", code="interaction_subject_invalid"
        )
    kind = _token(value.get("kind"), 32)
    identity = _identity(value.get("id"), "")
    if kind not in {"routing_decision", "run", "action", "unknown"} or not identity:
        raise InteractionContractError(
            "interaction subject reference is invalid", code="interaction_subject_invalid"
        )
    return {"kind": kind, "id": identity}


def _selection_candidates(selection: Mapping[str, Any]) -> list[Any]:
    detail = _mapping(selection.get("selection"))
    candidates = detail.get("candidate_details")
    if isinstance(candidates, list) and candidates:
        return _bounded_list(candidates)
    return [
        {"id": _identity(item, ""), "label": _identity(item, "")}
        for item in list(detail.get("candidate_ids") or ())[:_MAX_ITEMS]
        if _identity(item, "")
    ]


def _routing_root(value: Mapping[str, Any], fallback: str) -> tuple[str, int]:
    if not isinstance(value, Mapping) or value.get("available") is not True:
        return fallback, 0
    lineage = _mapping(value.get("lineage"))
    root = _identity(lineage.get("root_decision_id"), fallback)
    count = lineage.get("event_count")
    depth = count if isinstance(count, int) and not isinstance(count, bool) else 1
    return root, max(1, min(depth, 16))


def _state_revision(state: str, receipt: Mapping[str, Any]) -> int:
    rank = {
        "candidate_selection": 1,
        "facts_required": 1,
        "processing": 2,
        "confirmation_required": 3,
        "repairable": 3,
        "recoverable": 3,
        "completed": 4,
        "rejected": 4,
        "cancelled": 4,
        "failed": 4,
        "unavailable": 0,
    }.get(state, 0)
    lineage = _mapping(receipt.get("transition_lineage")) if isinstance(receipt, Mapping) else {}
    count = lineage.get("count")
    return rank + (min(count, 16) if isinstance(count, int) and not isinstance(count, bool) else 0)


def _interaction_kind(state: str) -> str:
    return {
        "candidate_selection": "workflow_selection",
        "facts_required": "facts_collection",
        "confirmation_required": "plan_confirmation",
        "repairable": "plan_repair",
        "recoverable": "recovery",
    }.get(state, "lifecycle")


def _action_kind(action_id: str) -> str:
    if action_id in {"select_domain", "select_capability", "select_workflow", "provide_facts", "preview"}:
        return "interaction"
    if action_id in {"confirm", "reject", "repair"}:
        return "decision"
    if action_id in {"rebuild_from_result", "start_new_run"}:
        return "evidence_recovery"
    return "lifecycle"


def _action_label(action_id: str) -> str:
    return {
        "select_domain": "选择领域",
        "select_capability": "选择能力",
        "select_workflow": "选择工作流",
        "provide_facts": "补充信息",
        "preview": "预览计划",
        "repair": "修复计划",
        "confirm": "确认执行",
        "reject": "拒绝",
        "retry": "重试",
        "recover": "恢复",
        "cancel": "取消",
        "rebuild_from_result": "从结果重建",
        "start_new_run": "开始新运行",
    }.get(action_id, action_id)


def _canonical_action_id(value: Any) -> str:
    action_id = _token(value, 48).lower()
    if action_id == "approve":
        action_id = "confirm"
    return action_id if action_id in INTERACTION_ACTION_IDS else ""


def _bounded_content(value: Any, *, _depth: int = 0) -> Any:
    if _depth > _MAX_SCHEMA_DEPTH:
        return None
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            name = _token(key, 64)
            if name:
                result[name] = _bounded_content(item, _depth=_depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_bounded_content(item, _depth=_depth + 1) for item in list(value)[:_MAX_ITEMS]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_TEXT]


def _validate_input_bounds(value: Any, *, _depth: int = 0) -> None:
    if _depth > _MAX_SCHEMA_DEPTH:
        raise InteractionContractError(
            "interaction input is too deeply nested",
            code="interaction_input_invalid",
        )
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise InteractionContractError(
                "interaction input has too many fields",
                code="interaction_input_invalid",
            )
        for key, item in value.items():
            if not _token(key, 64) or len(str(key)) > 64:
                raise InteractionContractError(
                    "interaction input field name is invalid",
                    code="interaction_input_invalid",
                )
            _validate_input_bounds(item, _depth=_depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 128:
            raise InteractionContractError(
                "interaction input has too many items",
                code="interaction_input_invalid",
            )
        for item in value:
            _validate_input_bounds(item, _depth=_depth + 1)
        return
    if isinstance(value, str) and len(value) > 10000:
        raise InteractionContractError(
            "interaction input text is too long",
            code="interaction_input_invalid",
        )
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise InteractionContractError(
            "interaction input contains an unsupported value",
            code="interaction_input_invalid",
        )


def _bounded_list(value: Any) -> list[Any]:
    return _bounded_content(value) if isinstance(value, (list, tuple)) else []


def _interaction_value(value: Mapping[str, Any]) -> Mapping[str, Any] | None:
    direct = value.get("interaction")
    if isinstance(direct, Mapping) and direct.get("schema_version") == INTERACTION_SCHEMA_VERSION:
        return direct
    nested = value.get("result")
    if isinstance(nested, Mapping):
        direct = nested.get("interaction")
        if isinstance(direct, Mapping) and direct.get("schema_version") == INTERACTION_SCHEMA_VERSION:
            return direct
    if value.get("schema_version") == INTERACTION_SCHEMA_VERSION:
        return value
    return None


def _legacy(first: Mapping[str, Any], second: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = first.get(key)
    if not isinstance(value, Mapping):
        value = second.get(key)
    return value if isinstance(value, Mapping) else {}


def _is_schema(value: Mapping[str, Any], version: str) -> bool:
    return isinstance(value, Mapping) and value.get("schema_version") == version


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity(value: Any, fallback: str) -> str:
    text = _token(value, _MAX_ID)
    return text or fallback


def _token(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    return text[:limit]


def _text(value: Any, fallback: str, limit: int) -> str:
    return _token(value, limit) or fallback


def _copy_int_bounds(source: Mapping[str, Any], target: dict[str, Any], keys: tuple[str, ...], *, maximum: int) -> None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            target[key] = max(0, min(value, maximum))


__all__ = [
    "INTERACTION_ACTION_IDS",
    "INTERACTION_STATES",
    "InteractionContractError",
    "legacy_domain_routing_interaction",
    "legacy_selection_interaction",
    "normalize_action_input_schema",
    "normalize_interaction",
    "normalize_interaction_action",
    "normalize_interaction_command",
    "project_interaction",
    "unavailable_interaction",
    "validate_action_input",
    "validate_interaction_command",
]
