"""Bounded, domain-neutral descriptors for capability discovery.

Domain Packs declare capabilities in their own catalogs.  This module exposes
the small stable interface consumed by catalog/API callers: build a safe
descriptor, project a collection, or normalize a persisted descriptor.  It
does not select a capability, resolve a workflow, or authorize execution.
Those decisions remain behind the Runtime and ToolRegistry seams.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .request_requirements import normalize_request_requirements


CAPABILITY_DESCRIPTOR_SCHEMA_VERSION = "spatial-agent.capability-descriptor.v1"
MAX_CAPABILITY_DESCRIPTORS = 64
MAX_DESCRIPTOR_LIST_ITEMS = 16
MAX_DESCRIPTOR_TEXT = 320
_COST_CLASSES = frozenset({"low", "medium", "high", "unknown"})
_AVAILABILITY_MODES = frozenset({"native", "demo", "unavailable", "unknown"})


def project_capability_descriptors(
    definitions: Iterable[Mapping[str, Any]] | None,
    *,
    domain_id: str = "unknown",
    catalog_version: str = "unknown",
    max_items: int = MAX_CAPABILITY_DESCRIPTORS,
) -> list[dict[str, Any]]:
    """Project Domain declarations into bounded, JSON-safe descriptors.

    Invalid declarations are omitted rather than exposed to a Planner.  The
    catalog validator remains responsible for reporting malformed Domain
    declarations during Runtime construction; this projection is a fail-closed
    read seam for compatibility callers.
    """

    limit = _bounded_limit(max_items, MAX_CAPABILITY_DESCRIPTORS)
    result: list[dict[str, Any]] = []
    for item in list(definitions or ())[:MAX_CAPABILITY_DESCRIPTORS]:
        descriptor = build_capability_descriptor(
            item,
            domain_id=domain_id,
            catalog_version=catalog_version,
        )
        if descriptor is not None:
            result.append(descriptor)
        if len(result) >= limit:
            break
    return result


def build_capability_descriptor(
    definition: Mapping[str, Any] | None,
    *,
    domain_id: str = "unknown",
    catalog_version: str = "unknown",
) -> dict[str, Any] | None:
    """Build one versioned descriptor from a Domain-owned declaration."""

    if not isinstance(definition, Mapping):
        return None
    capability_id = _text(definition.get("id"), 96)
    if not capability_id:
        return None

    requirements = normalize_request_requirements(definition.get("request_requirements"))
    fields = requirements.get("clarification_fields")
    fields = fields if isinstance(fields, list) else []
    required_facts = _unique_strings(
        [
            *(requirements.get("entities") or []),
            *(requirements.get("constraints") or []),
            *[
                field.get("id")
                for field in fields
                if isinstance(field, Mapping) and field.get("id")
            ],
        ],
        24,
    )
    datasets = _strings(definition.get("datasets"), 16, 96)
    tools = _strings(definition.get("tools"), 16, 96)
    result_types = _strings(definition.get("result_types"), 16, 96)
    operations = _strings(definition.get("analysis_operations"), 16, 64)
    environments = _strings(definition.get("environments"), 8, 32)
    geometry = _text(definition.get("geometry"), 32) or "unknown"
    label = _text(definition.get("label"), 96) or capability_id
    description = _text(definition.get("description"), MAX_DESCRIPTOR_TEXT)

    explicit_evidence = _evidence_requirements(definition.get("evidence_requirements"))
    descriptor = {
        "schema_version": CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
        "catalog_version": _text(catalog_version, 64) or "unknown",
        "domain_id": _text(domain_id, 80) or "unknown",
        "capability_id": capability_id,
        "label": label,
        "summary": description or f"提供“{label}”能力。",
        "inputs": {
            "facts": required_facts,
            "datasets": datasets,
        },
        "outputs": {
            "result_types": result_types,
            "geometry": geometry,
        },
        "preconditions": {
            "environments": environments,
            "datasets": datasets,
            "required_facts": required_facts,
            "data_readiness": "required" if datasets else "not_required",
        },
        "evidence_requirements": {
            "required": explicit_evidence,
            "dataset_provenance": bool(datasets),
            "result_profiles": result_types,
            "geometry": geometry,
            "declared_by_domain": definition.get("evidence_requirements") is not None,
        },
        "execution": {
            "tools": tools,
            "operations": operations,
        },
        "cost_hint": _cost_hint(definition.get("cost_hint"), tools, operations),
        "availability": {
            "available": bool(definition.get("available", False)),
            "mode": _availability_mode(definition.get("availability_mode")),
            "status": _text(definition.get("capability_status"), 32) or "unknown",
            "reason": _text(definition.get("availability_reason"), 96) or "unknown",
        },
    }
    return normalize_capability_descriptor(descriptor)


def normalize_capability_descriptor(value: Any) -> dict[str, Any] | None:
    """Normalize one current-version descriptor and reject unknown versions.

    Unknown top-level fields are ignored so a newer producer can be read by an
    older consumer.  Unknown schema versions, missing identity, and malformed
    required sections return ``None``; callers must not execute such data.
    """

    if not isinstance(value, Mapping):
        return None
    if _text(value.get("schema_version"), 96) != CAPABILITY_DESCRIPTOR_SCHEMA_VERSION:
        return None
    capability_id = _text(value.get("capability_id"), 96)
    domain_id = _text(value.get("domain_id"), 80)
    if not capability_id or not domain_id:
        return None
    inputs = value.get("inputs")
    outputs = value.get("outputs")
    preconditions = value.get("preconditions")
    evidence = value.get("evidence_requirements")
    execution = value.get("execution")
    if not all(isinstance(item, Mapping) for item in (inputs, outputs, preconditions, evidence, execution)):
        return None

    facts = _strings(inputs.get("facts"), 24, 96)
    datasets = _strings(inputs.get("datasets"), 16, 96)
    result_types = _strings(outputs.get("result_types"), 16, 96)
    geometry = _text(outputs.get("geometry"), 32) or "unknown"
    environments = _strings(preconditions.get("environments"), 8, 32)
    required_facts = _unique_strings(
        [*facts, *(_strings(preconditions.get("required_facts"), 24, 96))],
        24,
    )
    tools = _strings(execution.get("tools"), 16, 96)
    operations = _strings(execution.get("operations"), 16, 64)
    required_evidence = _strings(evidence.get("required"), 8, 96) or ["execution_receipt"]
    return {
        "schema_version": CAPABILITY_DESCRIPTOR_SCHEMA_VERSION,
        "catalog_version": _text(value.get("catalog_version"), 64) or "unknown",
        "domain_id": domain_id,
        "capability_id": capability_id,
        "label": _text(value.get("label"), 96) or capability_id,
        "summary": _text(value.get("summary"), MAX_DESCRIPTOR_TEXT) or "",
        "inputs": {"facts": facts, "datasets": datasets},
        "outputs": {"result_types": result_types, "geometry": geometry},
        "preconditions": {
            "environments": environments,
            "datasets": _strings(preconditions.get("datasets"), 16, 96) or datasets,
            "required_facts": required_facts,
            "data_readiness": (
                "required" if _text(preconditions.get("data_readiness"), 32) == "required" else "not_required"
            ),
        },
        "evidence_requirements": {
            "required": required_evidence,
            "dataset_provenance": bool(evidence.get("dataset_provenance")),
            "result_profiles": _strings(evidence.get("result_profiles"), 16, 96) or result_types,
            "geometry": _text(evidence.get("geometry"), 32) or geometry,
            "declared_by_domain": bool(evidence.get("declared_by_domain")),
        },
        "execution": {"tools": tools, "operations": operations},
        "cost_hint": _cost_hint(value.get("cost_hint"), tools, operations),
        "availability": {
            "available": bool((value.get("availability") or {}).get("available", False)),
            "mode": _availability_mode((value.get("availability") or {}).get("mode")),
            "status": _text((value.get("availability") or {}).get("status"), 32) or "unknown",
            "reason": _text((value.get("availability") or {}).get("reason"), 96) or "unknown",
        },
    }


def _cost_hint(value: Any, tools: list[str], operations: list[str]) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    cost_class = _text(source.get("class") or source.get("level"), 16).lower()
    if cost_class not in _COST_CLASSES:
        cost_class = "unknown"
    estimated_steps = source.get("estimated_step_count")
    if isinstance(estimated_steps, bool) or not isinstance(estimated_steps, int):
        estimated_steps = len(tools) or len(operations)
    return {
        "class": cost_class,
        "estimated_tool_count": min(len(tools), MAX_DESCRIPTOR_LIST_ITEMS),
        "estimated_step_count": max(0, min(estimated_steps, 32)),
    }


def _evidence_requirements(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        value = value.get("required") or value.get("items")
    return _strings(value, 8, 96) or ["execution_receipt"]


def _availability_mode(value: Any) -> str:
    mode = _text(value, 32).lower()
    return mode if mode in _AVAILABILITY_MODES else "unknown"


def _strings(value: Any, limit: int, item_limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return _unique_strings([_text(item, item_limit) for item in value], limit)


def _unique_strings(values: Iterable[Any], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_limit(value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return maximum
    return max(1, min(value, maximum))


__all__ = [
    "CAPABILITY_DESCRIPTOR_SCHEMA_VERSION",
    "MAX_CAPABILITY_DESCRIPTORS",
    "build_capability_descriptor",
    "normalize_capability_descriptor",
    "project_capability_descriptors",
]
