"""Domain-neutral request-fact requirements and satisfaction semantics.

Capability catalogs, discovery receipts and component handoffs all describe
the same small set of request facts.  Keeping normalization and cardinality
rules here prevents a public projection from silently dropping metadata or
giving ``any/all/one`` different meanings at another lifecycle boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


REQUEST_REQUIREMENTS_SCHEMA_VERSION = "spatial-agent.capability-requirements.v1"
REQUIREMENT_MODES = frozenset({"any", "all", "one"})
REQUIREMENT_KINDS = frozenset({"entity", "dataset", "constraint"})

_MAX_FIELDS = 16
_MAX_VALUES = 24
_MAX_TEXT = 120


def normalize_request_requirements(
    value: Any,
    *,
    max_fields: int = _MAX_FIELDS,
    max_values: int = _MAX_VALUES,
) -> dict[str, Any]:
    """Return a bounded, JSON-safe request-requirements contract.

    Unknown modes intentionally degrade to ``any`` for compatibility.  The
    contract is catalog-owned, so malformed fields are ignored rather than
    becoming implicit execution requirements.
    """

    source = value if isinstance(value, Mapping) else {}
    result: dict[str, Any] = {
        "schema_version": REQUEST_REQUIREMENTS_SCHEMA_VERSION,
        "entities": _strings(source.get("entities"), max_values),
        "datasets": _strings(source.get("datasets"), max_values),
        "constraints": _strings(source.get("constraints"), max_values),
        "clarification_fields": [],
    }
    raw_fields = source.get("clarification_fields")
    if not isinstance(raw_fields, Sequence) or isinstance(raw_fields, (str, bytes)):
        return result
    field_limit = max(1, min(_MAX_FIELDS, int(max_fields)))
    for raw in list(raw_fields)[:field_limit]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        label = _text(raw.get("label"), _MAX_TEXT)
        kind = _text(raw.get("kind"), 32)
        if not field_id or not label or kind not in REQUIREMENT_KINDS:
            continue
        mode = raw.get("mode")
        mode = mode if mode in REQUIREMENT_MODES else "any"
        field: dict[str, Any] = {
            "id": field_id,
            "label": label,
            "kind": kind,
            "required": raw.get("required")
            if isinstance(raw.get("required"), bool)
            else True,
            "mode": mode,
        }
        key = raw.get("key") or raw.get("fact")
        if key:
            field["key"] = _text(key, 80)
        keys = _strings(raw.get("keys"), max_values)
        values = _strings(raw.get("values"), max_values)
        if keys:
            field["keys"] = keys
        if values:
            field["values"] = values
        result["clarification_fields"].append(field)
    return result


def project_request_requirements(
    value: Any,
    *,
    max_fields: int = _MAX_FIELDS,
    source: str | None = "catalog",
) -> dict[str, Any]:
    """Project requirements for discovery, planner and evidence consumers."""

    normalized = normalize_request_requirements(value, max_fields=max_fields)
    fields = project_requirement_fields(
        normalized, max_fields=max_fields, source=source
    )
    return {
        "schema_version": normalized["schema_version"],
        "entities": list(normalized["entities"]),
        "datasets": list(normalized["datasets"]),
        "constraints": list(normalized["constraints"]),
        "clarification_fields": fields,
    }


def project_requirement_fields(
    value: Any,
    *,
    max_fields: int = _MAX_FIELDS,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Project field metadata without losing cardinality or choices."""

    normalized = (
        value
        if isinstance(value, Mapping)
        and value.get("schema_version") == REQUEST_REQUIREMENTS_SCHEMA_VERSION
        else normalize_request_requirements(value, max_fields=max_fields)
    )
    result: list[dict[str, Any]] = []
    for raw in list(normalized.get("clarification_fields") or [])[: max(1, int(max_fields))]:
        if not isinstance(raw, Mapping):
            continue
        field_id = _text(raw.get("id"), 80)
        label = _text(raw.get("label"), _MAX_TEXT)
        kind = _text(raw.get("kind"), 32)
        if not field_id or not label or kind not in REQUIREMENT_KINDS:
            continue
        field: dict[str, Any] = {
            "id": field_id,
            "label": label,
            "kind": kind,
            "required": raw.get("required")
            if isinstance(raw.get("required"), bool)
            else True,
            "mode": raw.get("mode") if raw.get("mode") in REQUIREMENT_MODES else "any",
        }
        key = raw.get("key") or raw.get("fact")
        if key:
            field["key"] = _text(key, 80)
        keys = _strings(raw.get("keys"), _MAX_VALUES)
        values = _strings(raw.get("values"), _MAX_VALUES)
        if keys:
            field["keys"] = keys
        if values:
            field["values"] = values
        if source:
            field["source"] = _text(source, 32)
        result.append(field)
    return result[: max(1, min(_MAX_FIELDS, int(max_fields)))]


def request_facts_snapshot(value: Any) -> dict[str, Any]:
    """Normalize RequestFacts-like input for requirement evaluation."""

    source = value if isinstance(value, Mapping) else None
    if source is None:
        method = getattr(value, "as_context_dict", None)
        candidate = method() if callable(method) else None
        source = candidate if isinstance(candidate, Mapping) else {}
    raw_entities = source.get("entities")
    entities = {
        _text(key, 80): item
        for key, item in (
            raw_entities.items() if isinstance(raw_entities, Mapping) else ()
        )
        if _text(key, 80) and item is not None
    }
    for key in ("admin_name", "region", "entity", "place"):
        if source.get(key) is not None and key not in entities:
            entities[key] = source.get(key)
    datasets = source.get("datasets")
    if isinstance(datasets, str):
        datasets = [datasets]
    constraints = source.get("constraints")
    return {
        "entities": entities,
        "datasets": {
            _text(item, 96)
            for item in (datasets or [])
            if _text(item, 96)
        },
        "constraints": dict(constraints) if isinstance(constraints, Mapping) else {},
    }


def requirement_satisfied(
    field: Mapping[str, Any],
    requirements: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    workflow_constraints: Mapping[str, Any] | None = None,
) -> bool:
    """Evaluate one declared field using the shared cardinality semantics."""

    if field.get("required") is False:
        return True
    kind = field.get("kind")
    if kind == "entity":
        key = _text(field.get("key") or "admin_name", 80)
        return _present((facts.get("entities") or {}).get(key))
    constraints = dict(facts.get("constraints") or {})
    if isinstance(workflow_constraints, Mapping):
        constraints.update(workflow_constraints)
    if kind == "dataset":
        expected = set(field.get("values") or requirements.get("datasets") or ())
        observed = set(facts.get("datasets") or ())
    elif kind == "constraint":
        expected = set(field.get("keys") or requirements.get("constraints") or ())
        observed = {key for key, item in constraints.items() if _present(item)}
    else:
        return True
    mode = field.get("mode") if field.get("mode") in REQUIREMENT_MODES else "any"
    if not expected:
        return len(observed) == 1 if mode == "one" else bool(observed)
    matched = expected & observed
    if mode == "all":
        return expected.issubset(observed)
    if mode == "one":
        return len(matched) == 1
    return bool(matched)


def missing_requirement_fields(
    requirements: Mapping[str, Any],
    facts: Any,
    *,
    workflow_constraints: Mapping[str, Any] | None = None,
    max_fields: int = 8,
    identity: Mapping[str, Any] | None = None,
    source: str = "user",
) -> list[dict[str, Any]]:
    """Return missing fields with enough metadata for a safe continuation."""

    normalized = normalize_request_requirements(requirements, max_fields=_MAX_FIELDS)
    snapshot = request_facts_snapshot(facts)
    result: list[dict[str, Any]] = []
    for field in normalized["clarification_fields"]:
        if requirement_satisfied(
            field,
            normalized,
            snapshot,
            workflow_constraints=workflow_constraints,
        ):
            continue
        item = project_requirement_fields(
            {"clarification_fields": [field]}, max_fields=1, source=source
        )
        if not item:
            continue
        projected = item[0]
        if isinstance(identity, Mapping):
            for key, value in identity.items():
                if value not in (None, ""):
                    projected[str(key)] = value
        result.append(projected)
        if len(result) >= max(1, min(_MAX_FIELDS, int(max_fields))):
            break
    return result


def _strings(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, 96)
        if text and text not in result:
            result.append(text)
        if len(result) >= max(1, int(limit)):
            break
    return result


def _text(value: Any, limit: int) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != ()


__all__ = [
    "REQUEST_REQUIREMENTS_SCHEMA_VERSION",
    "REQUIREMENT_KINDS",
    "REQUIREMENT_MODES",
    "missing_requirement_fields",
    "normalize_request_requirements",
    "project_request_requirements",
    "project_requirement_fields",
    "request_facts_snapshot",
    "requirement_satisfied",
]
