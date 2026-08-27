"""Domain-neutral evidence for capability-to-workflow selection.

The selection decision belongs to a Domain Pack or an explicit caller.  This
module only defines the bounded public projection consumed by planners,
clarification responses, result contracts, artifacts and the Contract
Harness.  It intentionally knows nothing about GIS names or tool behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .evidence_contract import (
    build_capability_evidence,
    normalize_capability_evidence,
)
from .component_evidence import (
    normalize_component_evidence,
    normalize_workflow_component_evidence,
    project_workflow_component_evidence,
)
from .recovery_action import ACTION_IDS, normalize_action_ids


WORKFLOW_SELECTION_SCHEMA_VERSION = "spatial-agent.workflow-selection.v1"
WORKFLOW_SELECTION_STATES = {"selected", "ambiguous", "clarification", "unavailable"}
WORKFLOW_SELECTION_SOURCES = {
    "explicit_workflow",
    "domain_discovery",
    "domain_composition",
    "domain_policy",
    "user_confirmation",
    "none",
}
EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION = "spatial-agent.evidence-action-guidance.v1"
EVIDENCE_ACTION_GUIDANCE_STATES = frozenset(
    {"ready", "degraded", "unavailable", "unknown", "not_applicable"}
)
_MAX_ITEMS = 16
_MAX_TEXT = 96
_MAX_DESCRIPTION = 320


def build_workflow_selection_evidence(
    *,
    discovery: Mapping[str, Any] | None = None,
    domain_selection: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
    capability_catalog: Mapping[str, Any] | None = None,
    candidate_details: Any = None,
    suggested_capability_details: Any = None,
    domain_seams: Mapping[str, Any] | None = None,
    request_facts: Any = None,
    domain_id: str = "unknown",
    state: str | None = None,
    reason_code: str | None = None,
    evidence_action_guidance: Any = None,
) -> dict[str, Any]:
    """Build a bounded selection projection without selecting by domain name."""

    discovery_map = _mapping(discovery)
    selected = _mapping(domain_selection)
    explicit = _mapping(workflow)
    candidate_ids = _string_list(
        selected.get("candidate_ids")
        if "candidate_ids" in selected
        else discovery_map.get("candidate_ids")
    )
    selected_capability = _text(
        selected.get("selected_capability_id")
        or discovery_map.get("selected_capability_id")
    ) or None
    if selected_capability and selected_capability not in candidate_ids:
        candidate_ids.insert(0, selected_capability)
    candidate_ids = candidate_ids[:_MAX_ITEMS]
    template_id = _text(
        explicit.get("template_id")
        or selected.get("workflow_template_id")
    ) or None
    template_version = _text(
        explicit.get("template_version")
        or selected.get("workflow_template_version")
    ) or None
    workflow_components = _normalize_workflow_components(
        selected.get("workflow_components")
        or explicit.get("components")
        or explicit.get("workflow_components")
        or selected.get("components")
    )
    component_source = (
        explicit.get("components")
        or selected.get("workflow_components")
        or selected.get("components")
    )
    component_evidence = None
    if isinstance(component_source, (list, tuple)) and component_source:
        candidate_component_evidence = (
            selected.get("workflow_component_evidence")
            or discovery_map.get("workflow_component_evidence")
        )
        component_evidence = (
            normalize_workflow_component_evidence(candidate_component_evidence)
            if isinstance(candidate_component_evidence, Mapping)
            else project_workflow_component_evidence({"components": component_source})
        )
    candidate_templates = _string_list(
        selected.get("candidate_workflow_ids")
        or selected.get("candidate_template_ids")
    )
    candidate_detail_values = (
        selected.get("candidate_details")
        or discovery_map.get("candidate_details")
        or candidate_details
    )
    if not candidate_detail_values and isinstance(capability_catalog, Mapping):
        candidate_detail_values = _candidate_details_from_catalog(
            capability_catalog,
            candidate_ids,
        )
    discovery_guidance = _mapping(discovery_map.get("guidance"))
    suggested_detail_values = (
        selected.get("suggested_capability_details")
        or discovery_map.get("suggested_capability_details")
        or discovery_guidance.get("suggested_capability_details")
        or suggested_capability_details
    )
    guidance_value = (
        selected.get("evidence_action_guidance")
        or discovery_map.get("evidence_action_guidance")
        or discovery_guidance.get("evidence_action_guidance")
        or selected.get("action_guidance")
        or discovery_map.get("action_guidance")
        or evidence_action_guidance
    )
    source = _text(selected.get("source")) or (
        "explicit_workflow" if template_id and explicit.get("template_id") else
        "domain_discovery" if selected_capability or candidate_ids else "none"
    )
    if source not in WORKFLOW_SELECTION_SOURCES:
        source = "none"
    missing_source = (
        selected.get("missing_fields")
        if "missing_fields" in selected
        else discovery_map.get("missing_fields")
        or discovery_guidance.get("missing_fields")
    )
    missing = _normalize_missing(missing_source)
    declared_state = _text(selected.get("state"))
    if state not in WORKFLOW_SELECTION_STATES:
        if template_id:
            state = "selected"
        elif missing:
            state = "clarification"
        elif declared_state in WORKFLOW_SELECTION_STATES:
            state = declared_state
        elif template_id or selected_capability:
            state = "selected"
        elif len(candidate_ids) > 1:
            state = "ambiguous"
        else:
            state = "unavailable"
    available = bool(template_id or selected_capability or candidate_ids)
    if reason_code is None:
        reason_code = {
            "selected": "workflow_selected",
            "ambiguous": "multiple_capabilities",
            "clarification": "selection_requires_facts",
            "unavailable": "no_matching_capability",
        }.get(state, "workflow_selection_unavailable")
    facts = _facts_summary(request_facts)
    known_result_types = _normalize_result_type_index(
        selected.get("known_capability_result_types")
        or discovery_map.get("known_capability_result_types")
        or _known_capability_result_types(capability_catalog)
    )
    result = {
        "schema_version": WORKFLOW_SELECTION_SCHEMA_VERSION,
        "available": available,
        "state": state,
        "reason_code": _text(reason_code) or "workflow_selection_unavailable",
        "domain_id": _text(domain_id) or "unknown",
        "source": source,
        "selected_by": _text(selected.get("selected_by")) or (
            "user" if explicit.get("template_id") else "domain" if available else "none"
        ),
        "selected_capability_id": selected_capability,
        "candidate_ids": candidate_ids,
        "candidate_count": _bounded_int(
            selected.get("candidate_count"), 0, _MAX_ITEMS
        ) if selected.get("candidate_count") is not None else len(candidate_ids),
        "workflow_template_id": template_id,
        "workflow_template_version": template_version,
        "workflow_components": workflow_components,
        "workflow_component_ids": [item["component_id"] for item in workflow_components],
        "workflow_component_template_ids": [item["template_id"] for item in workflow_components],
        "candidate_workflow_ids": candidate_templates[:_MAX_ITEMS],
        "candidate_details": _normalize_candidate_details(candidate_detail_values),
        "suggested_capability_ids": _string_list(
            selected.get("suggested_capability_ids")
            or discovery_map.get("suggested_capability_ids")
            or discovery_guidance.get("suggested_capability_ids")
        ),
        "suggested_capability_details": _normalize_candidate_details(
            suggested_detail_values
        ),
        "evidence_action_guidance": normalize_evidence_action_guidance(
            guidance_value
        ),
        "known_capability_result_types": known_result_types,
        "domain_seams": _normalize_domain_seams(domain_seams or selected.get("domain_seams")),
        "missing_fields": missing,
        "request_facts_schema_version": facts["schema_version"],
        "fact_keys": facts["fact_keys"],
    }
    if component_evidence is not None and component_evidence.get("available"):
        result["workflow_component_evidence"] = component_evidence
    return result


def normalize_workflow_selection_evidence(value: Any) -> dict[str, Any]:
    """Normalize current and unknown persisted selection evidence safely."""

    if not isinstance(value, Mapping):
        return build_workflow_selection_evidence(
            domain_id="unknown", state="unavailable", reason_code="selection_missing"
        )
    if value.get("schema_version") != WORKFLOW_SELECTION_SCHEMA_VERSION:
        return build_workflow_selection_evidence(
            domain_id=_text(value.get("domain_id")) or "unknown",
            state="unavailable",
            reason_code="selection_unknown_schema",
        )
    return build_workflow_selection_evidence(
        discovery=value,
        domain_selection=value,
        request_facts={
            "schema_version": value.get("request_facts_schema_version"),
            **{key: True for key in (value.get("fact_keys") or [])},
        },
        domain_id=_text(value.get("domain_id")) or "unknown",
        state=_text(value.get("state")) or "unavailable",
        reason_code=_text(value.get("reason_code")) or "workflow_selection_unavailable",
        candidate_details=value.get("candidate_details"),
        suggested_capability_details=value.get("suggested_capability_details"),
        domain_seams=value.get("domain_seams"),
        evidence_action_guidance=value.get("evidence_action_guidance"),
    )


def normalize_evidence_action_guidance(value: Any) -> dict[str, Any]:
    """Normalize Domain-owned evidence advice without granting execution power.

    A Domain Pack may recommend next actions from its evidence/readiness
    semantics.  The Runtime consumes this as a bounded hint; lifecycle and
    interaction gates still decide which actions are executable.
    """

    source = value if isinstance(value, Mapping) else {}
    schema = _text(source.get("schema_version"))
    if source and schema != EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION:
        return _empty_guidance("evidence_action_guidance_unknown_schema")
    state = _text(source.get("state") or source.get("status")) or "unknown"
    if state not in EVIDENCE_ACTION_GUIDANCE_STATES:
        state = "unknown"
    recommended = normalize_action_ids(
        source.get("recommended_actions") or source.get("actions"),
        allowed=ACTION_IDS,
    )
    declared_available = source.get("available")
    available = (
        declared_available
        if isinstance(declared_available, bool)
        else bool(source)
    )
    return {
        "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
        "available": available,
        "state": state,
        "reason_code": _text(source.get("reason_code"))
        or "evidence_action_guidance_unavailable",
        "recommended_actions": recommended,
        "missing_fields": _normalize_missing(source.get("missing_fields")),
        "source": _guidance_source(source.get("source")),
    }


def _empty_guidance(reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION,
        "available": False,
        "state": "unknown",
        "reason_code": _text(reason_code),
        "recommended_actions": [],
        "missing_fields": [],
        "source": "none",
    }


def _guidance_source(value: Any) -> str:
    source = _text(value)
    return source if source in {"domain", "catalog", "runtime", "none"} else "none"


def _candidate_details_from_catalog(
    catalog: Mapping[str, Any],
    candidate_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Project Domain-owned catalog entries into bounded choice cards.

    The Runtime only understands this generic shape. Labels, descriptions,
    requirements, availability and workflow metadata come from the selected
    Domain Pack's catalog; no domain identifier or dataset vocabulary is
    interpreted here.
    """

    definitions = {
        _text(item.get("id")): item
        for item in (catalog.get("capabilities") or [])
        if isinstance(item, Mapping) and _text(item.get("id"))
    }
    templates = {
        _text(key): value
        for key, value in (catalog.get("workflow_templates") or {}).items()
        if _text(key) and isinstance(value, Mapping)
    }
    result = []
    for capability_id in candidate_ids[:_MAX_ITEMS]:
        definition = definitions.get(capability_id)
        if not definition:
            continue
        requirements = definition.get("request_requirements")
        fields = []
        if isinstance(requirements, Mapping):
            fields = requirements.get("clarification_fields") or []
        workflow = templates.get(capability_id)
        workflow_summary = None
        if isinstance(workflow, Mapping):
            workflow_summary = {
                "template_id": _text(workflow.get("id") or capability_id),
                "template_version": _text(workflow.get("version") or "1.0.0"),
                "result_types": _string_list(workflow.get("result_types")),
                "max_steps": _bounded_int(workflow.get("max_steps"), 1, 64),
            }
        result.append(
            {
                "id": capability_id,
                "label": _text(definition.get("label") or capability_id),
                "description": (
                    _text(definition.get("description"))
                    or f"提供“{_text(definition.get('label') or capability_id)}”能力。"
                )[:_MAX_DESCRIPTION],
                "available": bool(definition.get("available", True)),
                "input_facts": _normalize_input_facts(fields),
                "result_types": _string_list(definition.get("result_types")),
                "data": {
                    "dataset_gate": _text(definition.get("dataset_gate") or "unknown"),
                    "capability_status": _text(
                        definition.get("capability_status") or "unknown"
                    ),
                    "availability_mode": _text(
                        definition.get("availability_mode") or "unknown"
                    ),
                    "availability_reason": _text(
                        definition.get("availability_reason") or "unknown"
                    ),
                    "native_available": bool(definition.get("native_available", False)),
                    "demo_available": bool(definition.get("demo_available", False)),
                    "missing_datasets": _string_list(definition.get("missing_datasets")),
                    "geometry": _text(definition.get("geometry") or "unknown"),
                },
                "evidence": (
                    normalize_capability_evidence(definition.get("evidence"))
                    if isinstance(definition.get("evidence"), Mapping)
                    else build_capability_evidence(definition)
                ),
                "actions": [
                    "select_capability",
                    "select_workflow",
                ] if workflow_summary else ["select_capability"],
                "evidence_action_guidance": definition.get(
                    "evidence_action_guidance"
                ) or definition.get("action_guidance"),
                "workflow": workflow_summary,
            }
        )
    return result


def _known_capability_result_types(catalog: Any) -> list[dict[str, Any]]:
    """Return a small Domain-owned result-type index for planner alignment.

    This is deliberately separate from candidate cards.  Context compaction
    may show only the selected card, but a generated plan can still name a
    different known capability.  The Runtime should then report a clear
    mismatch; it should reserve ``unresolved`` for result types absent from
    the Domain catalog altogether.
    """

    if not isinstance(catalog, Mapping):
        return []
    definitions = catalog.get("capabilities")
    definitions = definitions if isinstance(definitions, list) else []
    result = []
    seen = set()
    for definition in definitions[:_MAX_ITEMS]:
        if not isinstance(definition, Mapping):
            continue
        capability_id = _text(definition.get("id"))
        if not capability_id or capability_id in seen:
            continue
        seen.add(capability_id)
        result_types = _string_list(definition.get("result_types"))
        workflow = (catalog.get("workflow_templates") or {}).get(capability_id)
        if isinstance(workflow, Mapping):
            result_types.extend(_string_list(workflow.get("result_types")))
        result_types = list(dict.fromkeys(result_types))[:8]
        if result_types:
            result.append({"id": capability_id, "result_types": result_types})
    return result[:_MAX_ITEMS]


def _normalize_result_type_index(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    seen = set()
    for item in values[:_MAX_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        capability_id = _text(item.get("id") or item.get("capability_id"))
        if not capability_id or capability_id in seen:
            continue
        result_types = _string_list(item.get("result_types"))[:8]
        if not result_types:
            continue
        seen.add(capability_id)
        result.append({"id": capability_id, "result_types": result_types})
    return result


def _normalize_candidate_details(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    seen = set()
    for item in values[:_MAX_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        capability_id = _text(item.get("id") or item.get("capability_id"))
        if not capability_id or capability_id in seen:
            continue
        seen.add(capability_id)
        actions = [
            action
            for action in _string_list(item.get("actions"))[:8]
            if action in {"select_capability", "select_workflow", "preview"}
        ]
        workflow = item.get("workflow")
        workflow_summary = None
        if isinstance(workflow, Mapping) and _text(workflow.get("template_id")):
            workflow_summary = {
                "template_id": _text(workflow.get("template_id")),
                "template_version": _text(workflow.get("template_version") or "1.0.0"),
                "result_types": _string_list(workflow.get("result_types")),
                "max_steps": _bounded_int(workflow.get("max_steps"), 1, 64),
            }
        data = item.get("data")
        data_summary = {}
        if isinstance(data, Mapping):
            data_summary = {
                "dataset_gate": _text(data.get("dataset_gate") or "unknown"),
                "capability_status": _text(data.get("capability_status") or "unknown"),
                "availability_mode": _text(data.get("availability_mode") or "unknown"),
                "availability_reason": _text(data.get("availability_reason") or "unknown"),
                "native_available": bool(data.get("native_available", False)),
                "demo_available": bool(data.get("demo_available", False)),
                "missing_datasets": _string_list(data.get("missing_datasets")),
                "geometry": _text(data.get("geometry") or "unknown"),
            }
        evidence = normalize_capability_evidence(item.get("evidence"))
        guidance = normalize_evidence_action_guidance(
            item.get("evidence_action_guidance") or item.get("action_guidance")
        )
        result.append(
            {
                "id": capability_id,
                "label": _text(item.get("label") or capability_id),
                "description": _text(item.get("description"))[:_MAX_DESCRIPTION],
                "available": item.get("available") is not False,
                "input_facts": _normalize_input_facts(item.get("input_facts")),
                "result_types": _string_list(item.get("result_types")),
                "data": data_summary,
                "evidence": evidence,
                "evidence_action_guidance": guidance,
                "actions": actions or ["select_capability"],
                "workflow": workflow_summary,
            }
        )
    return result


def _normalize_domain_seams(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    result = {
        "schema_version": _text(source.get("schema_version"))
        or "spatial-agent.domain-workflow-seam.v1",
        "selection": bool(source.get("selection", False)),
        "workflow_normalization": bool(source.get("workflow_normalization", False)),
        "plan_validation": bool(source.get("plan_validation", False)),
        "capability_resolution": bool(source.get("capability_resolution", False)),
    }
    return result


def _normalize_workflow_components(value: Any) -> list[dict[str, Any]]:
    """Project component identity without copying arbitrary constraints."""

    values = value if isinstance(value, (list, tuple)) else []
    result = []
    seen = set()
    for index, item in enumerate(values[:8]):
        if not isinstance(item, Mapping):
            continue
        template_id = _text(item.get("template_id"))
        component_id = _text(item.get("component_id") or template_id or f"component-{index + 1}")
        if not template_id or not component_id or component_id in seen:
            continue
        seen.add(component_id)
        dependencies = _string_list(
            item.get("depends_on_components") or item.get("depends_on")
        )
        constraints = item.get("constraints")
        constraint_keys = (
            sorted(_text(key) for key in constraints.keys() if _text(key))[:16]
            if isinstance(constraints, Mapping)
            else _string_list(item.get("constraint_keys"))[:16]
        )
        evidence_keys = _string_list(
            item.get("evidence_keys") or item.get("evidence")
        )[:16]
        evidence_summary = item.get("evidence_summary") or item.get("evidence_state")
        component = {
                "component_id": component_id,
                "template_id": template_id,
                "template_version": _text(item.get("template_version")) or "1.0.0",
                "depends_on_components": dependencies,
                "constraint_keys": constraint_keys,
                "evidence_keys": evidence_keys,
                "component_evidence": normalize_component_evidence(evidence_summary),
            }
        if isinstance(evidence_summary, Mapping):
            component["evidence_summary"] = normalize_capability_evidence(evidence_summary)
        result.append(component)
    return result


def _normalize_input_facts(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    for item in values[:_MAX_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        field_id = _text(item.get("id"))
        label = _text(item.get("label") or field_id)
        kind = _text(item.get("kind") or "fact")
        if field_id and label:
            field: dict[str, Any] = {
                "id": field_id,
                "label": label,
                "kind": kind,
            }
            if isinstance(item.get("required"), bool):
                field["required"] = item["required"]
            if item.get("mode") in {"any", "all", "one"}:
                field["mode"] = item["mode"]
            for key in ("key", "fact"):
                if item.get(key):
                    field["key"] = _text(item[key])
                    break
            for key in ("keys", "values"):
                values = _string_list(item.get(key))
                if values:
                    field[key] = values[:_MAX_ITEMS]
            result.append(field)
    return result


def _facts_summary(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    if not source and value is not None:
        method = getattr(value, "as_context_dict", None)
        candidate = method() if callable(method) else None
        source = candidate if isinstance(candidate, Mapping) else {}
    keys = []
    for key in ("admin_name", "region", "entity", "place", "tasks", "datasets", "constraints", "evidence"):
        raw = source.get(key)
        if raw:
            keys.append(key)
    return {
        "schema_version": _text(source.get("schema_version")) or "spatial-agent.request-facts.v1",
        "fact_keys": keys[:_MAX_ITEMS],
    }


def _normalize_missing(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, (list, tuple)) else []
    result = []
    for item in values[:_MAX_ITEMS]:
        if isinstance(item, Mapping):
            field_id = _text(item.get("id"))
            label = _text(item.get("label"))
            kind = _text(item.get("kind"))
            if field_id and label:
                field: dict[str, Any] = {
                    "id": field_id,
                    "label": label,
                    "kind": kind or "fact",
                }
                if isinstance(item.get("required"), bool):
                    field["required"] = item["required"]
                if item.get("mode") in {"any", "all", "one"}:
                    field["mode"] = item["mode"]
                for key in ("key", "fact"):
                    if item.get(key):
                        field["key"] = _text(item[key])
                        break
                for key in ("keys", "values"):
                    values = _string_list(item.get(key))
                    if values:
                        field[key] = values[:_MAX_ITEMS]
                result.append(field)
        elif _text(item):
            result.append({"id": _text(item), "label": _text(item), "kind": "fact"})
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result = []
    for item in values:
        value = _text(item)
        if value and value not in result:
            result.append(value)
        if len(result) >= _MAX_ITEMS:
            break
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


__all__ = [
    "EVIDENCE_ACTION_GUIDANCE_SCHEMA_VERSION",
    "EVIDENCE_ACTION_GUIDANCE_STATES",
    "WORKFLOW_SELECTION_SCHEMA_VERSION",
    "WORKFLOW_SELECTION_SOURCES",
    "WORKFLOW_SELECTION_STATES",
    "build_workflow_selection_evidence",
    "normalize_evidence_action_guidance",
    "normalize_workflow_selection_evidence",
]
