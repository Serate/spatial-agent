"""Workflow template catalog: lookup, validation and legacy GIS helpers.

Depends only on the shared ``workflow_template_common`` module (acyclic);
the compiler imports ``get_workflow_template`` here.  Re-exported by the
``workflow_templates`` compatibility facade.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Mapping, Iterable
from typing import Any, Dict, List, Optional, Set

from .workflow_template_common import (
    WorkflowTemplateError,
    DEFAULT_TEMPLATE_VERSION,
    WORKFLOW_COMPOSITION_SCHEMA_VERSION,
    SUPPORTED_CONSTRAINT_TYPES,
    _TEMPLATE_KEYS, _REQUIRED_TEMPLATE_KEYS, _PLAN_KEYS, _STEP_KEYS,
    _STEP_BLUEPRINT_KEYS, _CONSTRAINT_SPEC_KEYS, _CHINESE_LABEL, _SEMVER,
    _text, _string_list, _value_set, _assert_json_safe, _assert_acyclic,
    _normalize_constraint_specs, _normalize_output_template, _normalize_step_blueprint,
)


def workflow_template_catalog(
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return an isolated catalog copy.

    The legacy GIS catalog is resolved lazily only for old callers;
    Runtime/Domain integrations should pass an explicit Domain-owned catalog.
    """

    source = _legacy_gis_catalog() if catalog is None else catalog
    if not isinstance(source, Mapping):
        raise WorkflowTemplateError("catalog must be an object")
    return copy.deepcopy(dict(source))

def get_workflow_template(
    template_id: str,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return one catalog template, or raise for an unknown id."""

    if not isinstance(template_id, str) or not template_id.strip():
        raise WorkflowTemplateError("template id must be a non-empty string")
    selected_catalog = _legacy_gis_catalog() if catalog is None else catalog
    if not isinstance(selected_catalog, Mapping):
        raise WorkflowTemplateError("catalog must be an object")
    try:
        template = selected_catalog[template_id]
    except KeyError as exc:
        raise WorkflowTemplateError("unknown workflow template: " + template_id) from exc
    return copy.deepcopy(template)

def validate_workflow_template_catalog(
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Validate every entry in a keyed template directory."""

    source = _legacy_gis_catalog() if catalog is None else catalog
    _assert_json_safe(source, "catalog")
    if not isinstance(source, Mapping):
        raise WorkflowTemplateError("catalog must be an object")
    # Materialize caller-provided iterables once so generator-based allowlists
    # apply consistently to every template in the directory.
    catalog_tools = None if known_tools is None else list(known_tools)
    catalog_results = (
        None if known_result_types is None else list(known_result_types)
    )
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, item in source.items():
        if not isinstance(key, str) or not key.strip():
            raise WorkflowTemplateError("catalog keys must be non-empty strings")
        validated = validate_workflow_template(
            item,
            known_tools=catalog_tools,
            known_result_types=catalog_results,
        )
        if validated["id"] != key:
            raise WorkflowTemplateError(
                "catalog key does not match template.id: " + key
            )
        normalized[key] = validated
    return normalized

def validate_workflow_template(
    template: Mapping[str, Any],
    *,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Validate and return a normalized copy of one template definition.

    The validator rejects unknown fields as well as unknown tools and result
    types.  ``known_tools`` and ``known_result_types`` let an embedding
    application validate a versioned extension catalog explicitly.
    """

    _assert_json_safe(template, "template")
    if not isinstance(template, Mapping):
        raise WorkflowTemplateError("template must be an object")

    unknown = sorted(set(template) - _TEMPLATE_KEYS)
    if unknown:
        raise WorkflowTemplateError("template has unknown fields: " + ", ".join(unknown))

    for key in _REQUIRED_TEMPLATE_KEYS:
        if key not in template:
            raise WorkflowTemplateError("template missing required field: " + key)

    template_id = _text(template["id"], "template.id")
    version = _text(template.get("version", DEFAULT_TEMPLATE_VERSION), "template.version")
    if _SEMVER.fullmatch(version) is None:
        raise WorkflowTemplateError("template.version must use semantic versioning")
    label = _text(template["label"], "template.label")
    if _CHINESE_LABEL.search(label) is None:
        raise WorkflowTemplateError("template.label must contain Chinese text")

    tool_names = _string_list(template["allowed_tools"], "template.allowed_tools")
    result_types = _string_list(template["result_types"], "template.result_types")
    constraints = _string_list(
        template["required_constraints"], "template.required_constraints"
    )

    available_tools = _value_set(
        _legacy_known_tools() if known_tools is None else known_tools,
        "known_tools",
    )
    available_results = _value_set(
        _legacy_known_result_types() if known_result_types is None else known_result_types,
        "known_result_types",
    )
    unknown_tools = sorted(set(tool_names) - available_tools)
    if unknown_tools:
        raise WorkflowTemplateError("template contains unknown tool: " + ", ".join(unknown_tools))
    unknown_results = sorted(set(result_types) - available_results)
    if unknown_results:
        raise WorkflowTemplateError(
            "template contains unknown result type: " + ", ".join(unknown_results)
        )

    max_steps = template["max_steps"]
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise WorkflowTemplateError("template.max_steps must be a positive integer")

    raw_specs = template.get("constraint_specs")
    if raw_specs is None:
        raw_specs = [
            {"name": name, "label": name, "type": "string", "required": True}
            for name in constraints
        ]
    constraint_specs = _normalize_constraint_specs(raw_specs, constraints)
    evidence_options = _string_list(
        template.get("evidence_options", ["summary", "trace"]),
        "template.evidence_options",
    )
    default_evidence = _string_list(
        template.get("default_evidence", evidence_options),
        "template.default_evidence",
    )
    if not set(default_evidence).issubset(evidence_options):
        raise WorkflowTemplateError("template.default_evidence contains an unknown option")
    goal_template = _text(
        template.get("goal_template", "execute " + template_id),
        "template.goal_template",
    )
    step_blueprint = _normalize_step_blueprint(
        template.get("step_blueprint", []),
        tool_names,
        max_steps,
    )
    output_template = _normalize_output_template(
        template.get("output_template", {"type": result_types[0], "summary": True}),
        result_types,
    )

    return {
        "id": template_id,
        "version": version,
        "label": label,
        "goal_template": goal_template,
        "allowed_tools": tool_names,
        "result_types": result_types,
        "max_steps": max_steps,
        "required_constraints": constraints,
        "constraint_specs": constraint_specs,
        "evidence_options": evidence_options,
        "default_evidence": default_evidence,
        "step_blueprint": step_blueprint,
        "output_template": output_template,
    }

def workflow_template_context_summary(
    max_templates: Optional[int] = None,
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
    include_arg_shape: bool = True,
    compact: bool = False,
) -> Dict[str, Any]:
    """Return a compact template catalog for planner context.

    This is the public context seam for planners: it exposes the small
    interface they need (ids, constraints, result types, allowed tools, and
    blueprint shape) without requiring them to know the full template schema or
    every literal argument value. The raw catalog is owned by the caller's
    Domain Pack.
    """

    if max_templates is not None and max_templates < 1:
        raise ValueError("max_templates must be positive")
    validated_catalog = validate_workflow_template_catalog(
        catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    templates = []
    for index, template_id in enumerate(sorted(validated_catalog)):
        if max_templates is not None and index >= max_templates:
            break
        template = validated_catalog[template_id]
        steps = template.get("step_blueprint", [])
        step_summary = [
            {
                "id": step["id"],
                "tool": step["tool"],
                "depends_on": list(step.get("depends_on", [])),
                "arg_keys": sorted(step.get("args", {}).keys()),
            }
            for step in steps
        ]
        if include_arg_shape:
            for item, step in zip(step_summary, steps):
                item["arg_shape"] = _argument_context_shape(step.get("args", {}))
        template_summary = {
            "id": template["id"],
            "goal_template": template.get("goal_template"),
            "allowed_tools": list(template["allowed_tools"]),
            "result_types": list(template["result_types"]),
            "required_constraints": list(template["required_constraints"]),
            "evidence_options": list(template.get("evidence_options", [])),
            "max_steps": template["max_steps"],
            "has_blueprint": bool(steps),
            "step_blueprint": step_summary,
            "output_type": (template.get("output_template") or {}).get("type"),
        }
        if not compact:
            template_summary.update(
                {
                    "version": template["version"],
                    "label": template["label"],
                    "constraint_specs": [
                        _constraint_context_summary(spec)
                        for spec in template.get("constraint_specs", [])
                    ],
                    "default_evidence": list(template.get("default_evidence", [])),
                }
            )
        templates.append(template_summary)
    return {
        "schema_version": "spatial-agent.workflow_templates.v1",
        "template_count": len(validated_catalog),
        "returned_count": len(templates),
        "omitted_count": max(0, len(validated_catalog) - len(templates)),
        "templates": templates,
    }

def _argument_context_shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {"$constraint"}:
            return {"binds_constraint": str(value.get("$constraint"))}
        if set(value) == {"$result_ref"}:
            ref = value.get("$result_ref") if isinstance(value.get("$result_ref"), Mapping) else {}
            return {
                "binds_result": str(ref.get("step") or ""),
                "path": str(ref.get("path") or ""),
            }
        return {str(key): _argument_context_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_argument_context_shape(item) for item in value[:4]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def _constraint_context_summary(spec: Mapping[str, Any]) -> Dict[str, Any]:
    summary = {
        "name": spec["name"],
        "label": spec.get("label", spec["name"]),
        "type": spec["type"],
        "required": bool(spec.get("required")),
    }
    for key in ("choices", "default", "min", "max", "min_length", "max_length"):
        if key in spec:
            summary[key] = copy.deepcopy(spec[key])
    return summary

def _legacy_gis_catalog():
    from domains.gis.workflow_templates import workflow_template_catalog

    return workflow_template_catalog()

def _legacy_known_result_types():
    from domains.gis.workflow_templates import KNOWN_RESULT_TYPES

    return KNOWN_RESULT_TYPES

def _legacy_known_tools():
    from domains.gis.workflow_templates import KNOWN_TOOL_NAMES

    return KNOWN_TOOL_NAMES

def __getattr__(name: str):
    if name in {"KNOWN_TOOL_NAMES", "KNOWN_TOOLS", "KNOWN_RESULT_TYPES", "WORKFLOW_TEMPLATE_CATALOG"}:
        from domains.gis import workflow_templates as gis_templates

        return getattr(gis_templates, name)
    raise AttributeError(name)
