"""Controlled, JSON-safe workflow template contracts.

This module is intentionally independent from the planner and runtime.  A
caller can validate a template before registering it and validate a plan
against that template before execution without changing the existing plan
parser contract.
"""

import copy
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Optional, Set


class WorkflowTemplateError(ValueError):
    """Raised when a workflow template or a plan violates its contract."""


# These are the tools currently exposed by SpatialToolAdapter.  They are kept
# here as a small boundary for template validation rather than importing the
# adapter, which would make this declarative module depend on GIS backends.
KNOWN_TOOL_NAMES = [
    "get_dataset_health_report",
    "get_dataset_schema",
    "range_query",
    "spatial_join",
    "get_raster_metadata",
    "get_raster_statistics",
    "get_zonal_raster_statistics",
    "get_zonal_slope_statistics",
    "get_zonal_land_use_distribution",
    "get_zonal_buildability_analysis",
    "get_zonal_vector_summary",
    "get_zonal_constrained_buildability_analysis",
]

KNOWN_TOOLS = KNOWN_TOOL_NAMES

# Include both the dedicated result contracts and the legacy generic result
# contracts so validating an old plan remains possible.
KNOWN_RESULT_TYPES = [
    "direct_answer",
    "spatial_overview_result",
    "spatial_analysis_result",
    "admin_area_result",
    "raster_metadata_result",
    "raster_statistics_result",
    "zonal_raster_statistics_result",
    "terrain_land_use_analysis_result",
    "buildability_result",
    "buildability_comparison",
    "constrained_buildability_result",
    "zonal_vector_summary_result",
    "dataset_health_result",
    "spatial_relation_result",
    "spatial_result",
    "vector_result",
    "zonal_vector_result",
]

DEFAULT_TEMPLATE_VERSION = "1.0.0"
SUPPORTED_CONSTRAINT_TYPES = {"string", "number", "integer", "boolean", "enum"}


# The values use only JSON-native objects, arrays, strings, numbers, booleans,
# and null.  Keep this directory declarative so it can later be loaded from a
# signed configuration without changing the validation API.
WORKFLOW_TEMPLATE_CATALOG = {
    "admin_boundary_query": {
        "id": "admin_boundary_query",
        "version": "1.0.0",
        "label": "行政区边界查询",
        "goal_template": "query admin area boundary by name",
        "allowed_tools": ["get_dataset_schema", "range_query"],
        "result_types": ["admin_area_result"],
        "max_steps": 2,
        "required_constraints": ["admin_name"],
        "constraint_specs": [
            {"name": "admin_name", "label": "行政区", "type": "string", "required": True, "min_length": 1}
        ],
        "evidence_options": ["summary", "geometry", "trace"],
        "default_evidence": ["summary", "geometry", "trace"],
        "step_blueprint": [
            {
                "id": "schema-admin",
                "tool": "get_dataset_schema",
                "args": {"dataset": "admin_areas"},
                "depends_on": [],
            },
            {
                "id": "filter-admin",
                "tool": "range_query",
                "args": {
                    "dataset": "admin_areas",
                    "conditions": [
                        {"field": "name", "operator": "eq", "value": {"$constraint": "admin_name"}}
                    ],
                    "limit": 100,
                },
                "depends_on": ["schema-admin"],
            },
        ],
        "output_template": {"type": "admin_area_result", "summary": True},
    },
    "raster_metadata": {
        "id": "raster_metadata",
        "version": "1.0.0",
        "label": "栅格元数据查询",
        "goal_template": "inspect raster dataset metadata",
        "allowed_tools": ["get_raster_metadata"],
        "result_types": ["raster_metadata_result"],
        "max_steps": 1,
        "required_constraints": ["dataset"],
        "constraint_specs": [
            {"name": "dataset", "label": "数据集", "type": "enum", "required": True, "choices": ["dem", "land_use", "slope"]}
        ],
        "evidence_options": ["summary", "metadata", "trace"],
        "default_evidence": ["summary", "metadata", "trace"],
        "step_blueprint": [
            {
                "id": "raster-metadata",
                "tool": "get_raster_metadata",
                "args": {"dataset": {"$constraint": "dataset"}, "max_files": 3},
                "depends_on": [],
            },
        ],
        "output_template": {"type": "raster_metadata_result", "summary": True},
    },
    "spatial_overview": {
        "id": "spatial_overview",
        "version": "1.0.0",
        "label": "区域空间总览",
        "goal_template": "build a cross-source spatial overview for an administrative area",
        "allowed_tools": [
            "get_dataset_health_report",
            "get_dataset_schema",
            "range_query",
            "get_zonal_raster_statistics",
            "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
            "get_zonal_vector_summary",
        ],
        "result_types": ["spatial_overview_result"],
        "max_steps": 8,
        "required_constraints": ["admin_name"],
        "constraint_specs": [
            {"name": "admin_name", "label": "行政区", "type": "string", "required": True, "min_length": 1},
            {"name": "include_geometry", "label": "包含空间几何", "type": "boolean", "required": False, "default": True},
        ],
        "evidence_options": ["summary", "geometry", "data_health", "trace"],
        "default_evidence": ["summary", "geometry", "data_health", "trace"],
        "step_blueprint": [
            {
                "id": "dataset-health",
                "tool": "get_dataset_health_report",
                "args": {"dataset": "all", "max_files": 10},
                "depends_on": [],
            },
            {
                "id": "schema-admin",
                "tool": "get_dataset_schema",
                "args": {"dataset": "admin_areas"},
                "depends_on": ["dataset-health"],
            },
            {
                "id": "filter-admin",
                "tool": "range_query",
                "args": {
                    "dataset": "admin_areas",
                    "conditions": [
                        {"field": "name", "operator": "eq", "value": {"$constraint": "admin_name"}}
                    ],
                    "limit": 100,
                },
                "depends_on": ["schema-admin"],
            },
            {
                "id": "overview-elevation",
                "tool": "get_zonal_raster_statistics",
                "args": {"dataset": "dem", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "overview-slope",
                "tool": "get_zonal_slope_statistics",
                "args": {"admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "overview-land-use",
                "tool": "get_zonal_land_use_distribution",
                "args": {"admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "overview-roads",
                "tool": "get_zonal_vector_summary",
                "args": {"dataset": "roads", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_features": 10000},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "overview-water",
                "tool": "get_zonal_vector_summary",
                "args": {"dataset": "water", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_features": 10000},
                "depends_on": ["filter-admin"],
            },
        ],
        "output_template": {"type": "spatial_overview_result", "summary": True},
    },
    "spatial_analysis": {
        "id": "spatial_analysis",
        "version": "1.0.0",
        "label": "组合式空间分析",
        "goal_template": "compose a multi-task spatial analysis DAG from request facts",
        "allowed_tools": [
            "get_dataset_health_report",
            "get_dataset_schema",
            "range_query",
            "get_zonal_raster_statistics",
            "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
            "get_zonal_vector_summary",
            "get_zonal_buildability_analysis",
            "get_zonal_constrained_buildability_analysis",
        ],
        "result_types": ["spatial_analysis_result"],
        "max_steps": 12,
        "required_constraints": ["admin_name"],
        "constraint_specs": [
            {"name": "admin_name", "label": "行政区", "type": "string", "required": True, "min_length": 1},
            {"name": "slope_limit_degrees", "label": "坡度上限（度）", "type": "number", "required": False, "min": 0, "max": 90, "default": 15},
            {"name": "road_distance_m", "label": "道路距离（米）", "type": "number", "required": False, "min": 0, "default": 1000},
            {"name": "exclude_water", "label": "排除水体", "type": "boolean", "required": False, "default": False},
        ],
        "evidence_options": ["summary", "geometry", "data_health", "trace"],
        "default_evidence": ["summary", "geometry", "data_health", "trace"],
        "step_blueprint": [
            {
                "id": "dataset-health",
                "tool": "get_dataset_health_report",
                "args": {"dataset": "all", "max_files": 10},
                "depends_on": [],
            },
            {
                "id": "schema-admin",
                "tool": "get_dataset_schema",
                "args": {"dataset": "admin_areas"},
                "depends_on": ["dataset-health"],
            },
            {
                "id": "filter-admin",
                "tool": "range_query",
                "args": {
                    "dataset": "admin_areas",
                    "conditions": [
                        {"field": "name", "operator": "eq", "value": {"$constraint": "admin_name"}}
                    ],
                    "limit": 100,
                },
                "depends_on": ["schema-admin"],
            },
            {
                "id": "composed-elevation",
                "tool": "get_zonal_raster_statistics",
                "args": {"dataset": "dem", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "composed-slope",
                "tool": "get_zonal_slope_statistics",
                "args": {"admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "composed-land-use",
                "tool": "get_zonal_land_use_distribution",
                "args": {"admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_files": 10},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "composed-roads",
                "tool": "get_zonal_vector_summary",
                "args": {"dataset": "roads", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_features": 10000},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "composed-water",
                "tool": "get_zonal_vector_summary",
                "args": {"dataset": "water", "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}}, "max_features": 10000},
                "depends_on": ["filter-admin"],
            },
            {
                "id": "composed-buildability",
                "tool": "get_zonal_constrained_buildability_analysis",
                "args": {
                    "admin_name": {"$result_ref": {"step": "filter-admin", "path": "first_name"}},
                    "slope_limit_degrees": {"$constraint": "slope_limit_degrees"},
                    "road_distance_m": {"$constraint": "road_distance_m"},
                    "exclude_water": {"$constraint": "exclude_water"},
                    "max_files": 10,
                },
                "depends_on": ["filter-admin"],
            },
        ],
        "output_template": {"type": "spatial_analysis_result", "summary": True},
    },
    "constrained_buildability": {
        "id": "constrained_buildability",
        "version": "1.0.0",
        "label": "道路与水体约束筛选",
        "goal_template": "screen construction candidates with raster and vector constraints",
        "allowed_tools": [
            "get_dataset_health_report",
            "get_zonal_constrained_buildability_analysis",
        ],
        "result_types": ["constrained_buildability_result"],
        "max_steps": 2,
        "required_constraints": ["admin_name", "slope_limit_degrees"],
        "constraint_specs": [
            {"name": "admin_name", "label": "行政区", "type": "string", "required": True, "min_length": 1},
            {"name": "slope_limit_degrees", "label": "坡度上限（度）", "type": "number", "required": True, "min": 0, "max": 90},
            {"name": "road_distance_m", "label": "道路距离（米）", "type": "number", "required": False, "min": 0, "default": 1000},
            {"name": "exclude_water", "label": "排除水体", "type": "boolean", "required": False, "default": True},
        ],
        "evidence_options": ["summary", "geometry", "data_health", "trace"],
        "default_evidence": ["summary", "geometry", "data_health", "trace"],
        "step_blueprint": [
            {
                "id": "dataset-health",
                "tool": "get_dataset_health_report",
                "args": {"dataset": "all", "max_files": 10},
                "depends_on": [],
            },
            {
                "id": "constrained-buildability",
                "tool": "get_zonal_constrained_buildability_analysis",
                "args": {
                    "admin_name": {"$constraint": "admin_name"},
                    "slope_limit_degrees": {"$constraint": "slope_limit_degrees"},
                    "road_distance_m": {"$constraint": "road_distance_m"},
                    "exclude_water": {"$constraint": "exclude_water"},
                    "max_files": 10,
                },
                "depends_on": ["dataset-health"],
            },
        ],
        "output_template": {"type": "constrained_buildability_result", "summary": True},
    },
}


_TEMPLATE_KEYS = {
    "id",
    "version",
    "label",
    "allowed_tools",
    "result_types",
    "max_steps",
    "required_constraints",
    "constraint_specs",
    "evidence_options",
    "default_evidence",
    "goal_template",
    "step_blueprint",
    "output_template",
}
_REQUIRED_TEMPLATE_KEYS = {
    "id",
    "label",
    "allowed_tools",
    "result_types",
    "max_steps",
    "required_constraints",
}
_PLAN_KEYS = {"template_id", "template_version", "goal", "constraints", "evidence", "steps", "output", "assumptions"}
_STEP_KEYS = {"id", "tool", "args", "depends_on"}
_STEP_BLUEPRINT_KEYS = _STEP_KEYS
_CONSTRAINT_SPEC_KEYS = {"name", "label", "type", "required", "min", "max", "min_length", "max_length", "choices", "default"}
_CHINESE_LABEL = re.compile(r"[\u3400-\u9fff]")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def workflow_template_catalog() -> Dict[str, Dict[str, Any]]:
    """Return an isolated JSON-safe copy of the built-in template directory."""

    return copy.deepcopy(WORKFLOW_TEMPLATE_CATALOG)


def workflow_template_context_summary(
    max_templates: Optional[int] = None,
    *,
    include_arg_shape: bool = True,
    compact: bool = False,
) -> Dict[str, Any]:
    """Return a compact template catalog for planner context.

    This is the public context seam for planners: it exposes the small
    interface they need (ids, constraints, result types, allowed tools, and
    blueprint shape) without requiring them to know the full template schema or
    every literal argument value. The raw catalog remains owned by this module.
    """

    if max_templates is not None and max_templates < 1:
        raise ValueError("max_templates must be positive")
    catalog = validate_workflow_template_catalog()
    templates = []
    for index, template_id in enumerate(sorted(catalog)):
        if max_templates is not None and index >= max_templates:
            break
        template = catalog[template_id]
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
        "template_count": len(catalog),
        "returned_count": len(templates),
        "omitted_count": max(0, len(catalog) - len(templates)),
        "templates": templates,
    }


def validate_workflow_template_catalog(
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Validate every entry in a keyed template directory."""

    source = WORKFLOW_TEMPLATE_CATALOG if catalog is None else catalog
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


def get_workflow_template(template_id: str) -> Dict[str, Any]:
    """Return one built-in template, or raise for an unknown id."""

    if not isinstance(template_id, str) or not template_id.strip():
        raise WorkflowTemplateError("template id must be a non-empty string")
    try:
        template = WORKFLOW_TEMPLATE_CATALOG[template_id]
    except KeyError as exc:
        raise WorkflowTemplateError("unknown workflow template: " + template_id) from exc
    return copy.deepcopy(template)


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
        KNOWN_TOOL_NAMES if known_tools is None else known_tools,
        "known_tools",
    )
    available_results = _value_set(
        KNOWN_RESULT_TYPES if known_result_types is None else known_result_types,
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


def compile_workflow_plan(
    template: str | Mapping[str, Any],
    constraints: Mapping[str, Any],
    *,
    evidence: Optional[Iterable[str]] = None,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    goal: Optional[str] = None,
    output_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Render a declarative workflow template into a validated plan object.

    The compiler is intentionally small: natural-language interpretation remains
    in request_model, routing remains in capability_routing, and Runtime still
    validates and dispatches every tool.  This function only binds structured
    constraints to a template-owned DAG blueprint.
    """

    template_definition = _resolve_template(template, catalog)
    normalized_template = validate_workflow_template(template_definition)
    normalized_constraints = normalize_workflow_constraints(
        normalized_template, constraints
    )
    step_blueprint = normalized_template.get("step_blueprint", [])
    if not step_blueprint:
        raise WorkflowTemplateError(
            "template does not define a step_blueprint: " + normalized_template["id"]
        )
    steps = [
        {
            "id": step["id"],
            "tool": step["tool"],
            "args": _render_template_value(step["args"], normalized_constraints),
            "depends_on": list(step.get("depends_on", [])),
        }
        for step in step_blueprint
    ]
    output = _render_template_value(
        normalized_template["output_template"], normalized_constraints
    )
    if output_overrides:
        output.update(copy.deepcopy(dict(output_overrides)))
    plan = {
        "template_id": normalized_template["id"],
        "template_version": normalized_template["version"],
        "goal": goal or normalized_template["goal_template"],
        "constraints": normalized_constraints,
        "evidence": normalize_workflow_evidence(normalized_template, evidence),
        "steps": steps,
        "output": output,
    }
    return validate_workflow_plan(normalized_template, plan)


def normalize_workflow_constraints(
    template: str | Mapping[str, Any],
    constraints: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Validate and normalize user-editable structured workflow constraints."""

    normalized_template = validate_workflow_template(
        _resolve_template(template, catalog),
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    if not isinstance(constraints, Mapping):
        raise WorkflowTemplateError("constraints must be an object")
    specs = {item["name"]: item for item in normalized_template["constraint_specs"]}
    unknown = sorted(set(constraints) - set(specs))
    if unknown:
        raise WorkflowTemplateError("unknown constraints: " + ", ".join(unknown))
    result: Dict[str, Any] = {}
    for name, spec in specs.items():
        if name not in constraints:
            if "default" in spec:
                result[name] = copy.deepcopy(spec["default"])
            elif spec["required"]:
                raise WorkflowTemplateError("plan is missing required constraints: " + name)
            continue
        if _is_empty_constraint(constraints[name]):
            if spec["required"]:
                raise WorkflowTemplateError("plan is missing required constraints: " + name)
            continue
        result[name] = _normalize_constraint_value(constraints[name], spec)
    return result


def normalize_workflow_evidence(
    template: str | Mapping[str, Any],
    evidence: Optional[Iterable[str]] = None,
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> List[str]:
    """Validate the evidence views selected by a user or a plan."""

    normalized_template = validate_workflow_template(
        _resolve_template(template, catalog),
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    selected = normalized_template["default_evidence"] if evidence is None else evidence
    values = _string_list(list(selected), "evidence")
    unknown = sorted(set(values) - set(normalized_template["evidence_options"]))
    if unknown:
        raise WorkflowTemplateError("unknown evidence options: " + ", ".join(unknown))
    return values


def normalize_workflow_selection(
    template_id: str,
    constraints: Optional[Mapping[str, Any]] = None,
    evidence: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Normalize the user-selected template before a run is queued."""

    template = get_workflow_template(template_id)
    normalized_constraints = normalize_workflow_constraints(
        template, {} if constraints is None else constraints
    )
    return {
        "template_id": template["id"],
        "template_version": template["version"],
        "constraints": normalized_constraints,
        "evidence": normalize_workflow_evidence(template, evidence),
    }


def workflow_request_hint(request: str, workflow: Optional[Mapping[str, Any]]) -> str:
    """Add bounded, human-readable workflow context to the planner input."""

    if not workflow:
        return request
    if not isinstance(workflow, Mapping):
        raise WorkflowTemplateError("workflow must be an object")
    constraints = workflow.get("constraints", {})
    if not isinstance(constraints, Mapping):
        raise WorkflowTemplateError("workflow.constraints must be an object")
    template_id = workflow.get("template_id", "")
    parts = []
    if constraints.get("admin_name"):
        parts.append("行政区=" + str(constraints["admin_name"]))
    if constraints.get("dataset"):
        parts.append("数据集=" + str(constraints["dataset"]))
    if constraints.get("slope_limit_degrees") is not None:
        parts.append("坡度不超过{}度".format(constraints["slope_limit_degrees"]))
    if constraints.get("road_distance_m") is not None:
        parts.append("道路距离{}米".format(constraints["road_distance_m"]))
    if constraints.get("exclude_water"):
        parts.append("排除水体")
    if constraints.get("include_geometry") is False:
        parts.append("不需要空间几何导出")
    known_keys = {
        "admin_name",
        "dataset",
        "slope_limit_degrees",
        "road_distance_m",
        "exclude_water",
        "include_geometry",
    }
    for key, value in constraints.items():
        key_text = str(key or "").strip()[:64]
        if (
            not key_text
            or key_text in known_keys
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", key_text)
            or any(token in key_text.lower() for token in ("password", "secret", "token", "credential", "api_key"))
        ):
            continue
        safe_value = _workflow_hint_value(value)
        if safe_value is not None:
            parts.append("{}={}".format(key_text, safe_value))
    if not parts:
        return request
    label = {
        "admin_boundary_query": "行政区边界查询",
        "raster_metadata": "栅格元数据查询",
        "spatial_overview": "区域空间总览",
        "constrained_buildability": "道路与水体约束筛选",
    }.get(str(template_id), "受控空间工作流")
    return "{}\n[{}参数：{}]".format(request.strip(), label, "；".join(parts))


def _workflow_hint_value(value: Any) -> str | None:
    """Render custom Domain constraints without copying unbounded input."""

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)[:64]
    if isinstance(value, str) and value.strip():
        return value.strip()[:160]
    if isinstance(value, (list, tuple)):
        values = [
            item
            for item in value[:8]
            if isinstance(item, (str, int, float, bool))
        ]
        if values:
            return json.dumps(values, ensure_ascii=False, separators=(",", ":"))[:240]
    return None


def validate_workflow_plan(
    template: str | Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Validate a JSON plan against a template and return a safe copy.

    Required constraint names must be present in ``plan["constraints"]`` with
    a non-empty value.  Dependencies are checked as a directed graph, so
    unknown references, self references, duplicate dependencies, and cycles
    are rejected before a caller can execute the plan.
    """

    template_definition = _resolve_template(template, catalog)
    available_tools = _value_set(
        KNOWN_TOOL_NAMES if known_tools is None else known_tools,
        "known_tools",
    )
    available_results = _value_set(
        KNOWN_RESULT_TYPES if known_result_types is None else known_result_types,
        "known_result_types",
    )
    normalized_template = validate_workflow_template(
        template_definition,
        known_tools=available_tools,
        known_result_types=available_results,
    )

    _assert_json_safe(plan, "plan")
    if not isinstance(plan, Mapping):
        raise WorkflowTemplateError("plan must be an object")
    unknown = sorted(set(plan) - _PLAN_KEYS)
    if unknown:
        raise WorkflowTemplateError("plan has unknown fields: " + ", ".join(unknown))

    declared_template_id = plan.get("template_id")
    if declared_template_id is not None:
        declared_template_id = _text(declared_template_id, "plan.template_id")
        if declared_template_id != normalized_template["id"]:
            raise WorkflowTemplateError("plan.template_id does not match template.id")

    constraints = normalize_workflow_constraints(
        normalized_template,
        plan.get("constraints", {}),
        known_tools=available_tools,
        known_result_types=available_results,
    )

    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise WorkflowTemplateError("plan.steps must be an array")
    if len(steps) > normalized_template["max_steps"]:
        raise WorkflowTemplateError(
            "plan exceeds template max_steps: {} > {}".format(
                len(steps), normalized_template["max_steps"]
            )
        )

    normalized_steps: List[Dict[str, Any]] = []
    step_ids: Set[str] = set()
    for index, raw_step in enumerate(steps):
        path = "plan.steps[{}]".format(index)
        if not isinstance(raw_step, Mapping):
            raise WorkflowTemplateError(path + " must be an object")
        unknown_step_fields = sorted(set(raw_step) - _STEP_KEYS)
        if unknown_step_fields:
            raise WorkflowTemplateError(
                path + " has unknown fields: " + ", ".join(unknown_step_fields)
            )
        for key in ("id", "tool", "args"):
            if key not in raw_step:
                raise WorkflowTemplateError(path + " missing required field: " + key)
        step_id = _text(raw_step["id"], path + ".id")
        if step_id in step_ids:
            raise WorkflowTemplateError("duplicate step id: " + step_id)
        step_ids.add(step_id)
        tool = _text(raw_step["tool"], path + ".tool")
        if tool not in available_tools:
            raise WorkflowTemplateError("unknown tool: " + tool)
        if tool not in normalized_template["allowed_tools"]:
            raise WorkflowTemplateError(
                "tool is not allowed by template: " + tool
            )
        args = raw_step["args"]
        if not isinstance(args, dict):
            raise WorkflowTemplateError(path + ".args must be an object")
        depends_on = raw_step.get("depends_on", [])
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) and item.strip() for item in depends_on
        ):
            raise WorkflowTemplateError(path + ".depends_on must be an array of strings")
        if len(set(depends_on)) != len(depends_on):
            raise WorkflowTemplateError(path + ".depends_on contains duplicate ids")
        normalized_steps.append(
            {
                "id": step_id,
                "tool": tool,
                "args": copy.deepcopy(args),
                "depends_on": list(depends_on),
            }
        )

    known_step_ids = set(step_ids)
    graph: Dict[str, List[str]] = {}
    for step in normalized_steps:
        dependencies = step["depends_on"]
        unknown_dependencies = sorted(set(dependencies) - known_step_ids)
        if unknown_dependencies:
            raise WorkflowTemplateError(
                "step {} depends on unknown step: {}".format(
                    step["id"], ", ".join(unknown_dependencies)
                )
            )
        if step["id"] in dependencies:
            raise WorkflowTemplateError("step cannot depend on itself: " + step["id"])
        graph[step["id"]] = dependencies
    _assert_acyclic(graph)

    output = plan.get("output")
    if not isinstance(output, dict):
        raise WorkflowTemplateError("plan.output must be an object")
    result_type = output.get("type")
    if not isinstance(result_type, str) or not result_type.strip():
        raise WorkflowTemplateError("plan.output.type must be a non-empty string")
    if result_type not in available_results:
        raise WorkflowTemplateError("unknown result type: " + result_type)
    if result_type not in normalized_template["result_types"]:
        raise WorkflowTemplateError(
            "result type is not allowed by template: " + result_type
        )

    normalized_plan = copy.deepcopy(dict(plan))
    normalized_plan["template_id"] = normalized_template["id"]
    normalized_plan["template_version"] = normalized_template["version"]
    normalized_plan["steps"] = normalized_steps
    normalized_plan["constraints"] = constraints
    normalized_plan["evidence"] = normalize_workflow_evidence(
        normalized_template,
        plan.get("evidence"),
        known_tools=available_tools,
        known_result_types=available_results,
    )
    normalized_plan["output"] = copy.deepcopy(dict(output))
    return normalized_plan


def revise_workflow_plan(
    template: str | Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    constraints: Optional[Mapping[str, Any]] = None,
    evidence: Optional[Iterable[str]] = None,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Apply a bounded user revision and revalidate the complete plan."""

    current = validate_workflow_plan(template, plan, catalog=catalog)
    merged_constraints = dict(current["constraints"])
    if constraints is not None:
        if not isinstance(constraints, Mapping):
            raise WorkflowTemplateError("constraints must be an object")
        merged_constraints.update(constraints)
    revised = copy.deepcopy(dict(current))
    revised["constraints"] = merged_constraints
    if evidence is not None:
        revised["evidence"] = list(evidence)
    return validate_workflow_plan(template, revised, catalog=catalog)


def validate_template(
    template: Mapping[str, Any],
    *,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Short alias for callers that use the generic validation name."""

    return validate_workflow_template(
        template,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )


def _resolve_template(
    template: str | Mapping[str, Any],
    catalog: Optional[Mapping[str, Mapping[str, Any]]],
) -> Mapping[str, Any]:
    if isinstance(template, str):
        selected_catalog = WORKFLOW_TEMPLATE_CATALOG if catalog is None else catalog
        if not isinstance(selected_catalog, Mapping):
            raise WorkflowTemplateError("catalog must be an object")
        try:
            return selected_catalog[template]
        except KeyError as exc:
            raise WorkflowTemplateError("unknown workflow template: " + template) from exc
    if isinstance(template, Mapping):
        return template
    raise WorkflowTemplateError("template must be an id or an object")


def _assert_acyclic(graph: Mapping[str, List[str]]) -> None:
    states: Dict[str, int] = {}

    def visit(node: str) -> None:
        state = states.get(node, 0)
        if state == 1:
            raise WorkflowTemplateError("workflow dependencies contain a cycle at: " + node)
        if state == 2:
            return
        states[node] = 1
        for dependency in graph[node]:
            visit(dependency)
        states[node] = 2

    for node in graph:
        visit(node)


def _assert_json_safe(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkflowTemplateError(path + " contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_safe(item, path + "[{}]".format(index))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorkflowTemplateError(path + " contains a non-string object key")
            _assert_json_safe(item, path + "." + key)
        return
    raise WorkflowTemplateError(path + " is not JSON-safe")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowTemplateError(path + " must be a non-empty string")
    return value.strip()


def _string_list(value: Any, path: str) -> List[str]:
    if not isinstance(value, list):
        raise WorkflowTemplateError(path + " must be an array of strings")
    result = []
    for index, item in enumerate(value):
        result.append(_text(item, path + "[{}]".format(index)))
    if len(set(result)) != len(result):
        raise WorkflowTemplateError(path + " contains duplicate values")
    return result


def _value_set(values: Iterable[str], path: str) -> Set[str]:
    if isinstance(values, (str, bytes)):
        raise WorkflowTemplateError(path + " must be an iterable of strings")
    try:
        result = set(values)
    except (TypeError, ValueError) as exc:
        raise WorkflowTemplateError(path + " must be an iterable of strings") from exc
    if not all(isinstance(value, str) and value.strip() for value in result):
        raise WorkflowTemplateError(path + " must contain non-empty strings")
    return result


def _is_empty_constraint(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_constraint_specs(
    raw_specs: Any,
    required_constraints: List[str],
) -> List[Dict[str, Any]]:
    if not isinstance(raw_specs, list):
        raise WorkflowTemplateError("template.constraint_specs must be an array")
    normalized = []
    names = set()
    for index, raw in enumerate(raw_specs):
        path = "template.constraint_specs[{}]".format(index)
        if not isinstance(raw, Mapping):
            raise WorkflowTemplateError(path + " must be an object")
        unknown = sorted(set(raw) - _CONSTRAINT_SPEC_KEYS)
        if unknown:
            raise WorkflowTemplateError(path + " has unknown fields: " + ", ".join(unknown))
        name = _text(raw.get("name"), path + ".name")
        if name in names:
            raise WorkflowTemplateError("duplicate constraint spec: " + name)
        names.add(name)
        label = _text(raw.get("label", name), path + ".label")
        kind = _text(raw.get("type", "string"), path + ".type")
        if kind not in SUPPORTED_CONSTRAINT_TYPES:
            raise WorkflowTemplateError("unsupported constraint type: " + kind)
        required = raw.get("required", name in required_constraints)
        if not isinstance(required, bool):
            raise WorkflowTemplateError(path + ".required must be boolean")
        item = {"name": name, "label": label, "type": kind, "required": required}
        for key in ("min", "max", "min_length", "max_length"):
            if key in raw:
                value = raw[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise WorkflowTemplateError(path + "." + key + " must be a finite number")
                item[key] = int(value) if key.endswith("length") else float(value)
        if "choices" in raw:
            item["choices"] = _string_list(raw["choices"], path + ".choices")
        if kind == "enum" and not item.get("choices"):
            raise WorkflowTemplateError(path + ".choices is required for enum")
        if "default" in raw:
            item["default"] = copy.deepcopy(raw["default"])
        normalized.append(item)
    missing_specs = sorted(set(required_constraints) - names)
    if missing_specs:
        raise WorkflowTemplateError("required constraints missing specs: " + ", ".join(missing_specs))
    return normalized


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


def _normalize_step_blueprint(
    raw_steps: Any,
    allowed_tools: List[str],
    max_steps: int,
) -> List[Dict[str, Any]]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, list):
        raise WorkflowTemplateError("template.step_blueprint must be an array")
    if len(raw_steps) > max_steps:
        raise WorkflowTemplateError("template.step_blueprint exceeds template.max_steps")
    normalized: List[Dict[str, Any]] = []
    step_ids: Set[str] = set()
    for index, raw_step in enumerate(raw_steps):
        path = "template.step_blueprint[{}]".format(index)
        if not isinstance(raw_step, Mapping):
            raise WorkflowTemplateError(path + " must be an object")
        unknown = sorted(set(raw_step) - _STEP_BLUEPRINT_KEYS)
        if unknown:
            raise WorkflowTemplateError(path + " has unknown fields: " + ", ".join(unknown))
        for key in ("id", "tool", "args"):
            if key not in raw_step:
                raise WorkflowTemplateError(path + " missing required field: " + key)
        step_id = _text(raw_step["id"], path + ".id")
        if step_id in step_ids:
            raise WorkflowTemplateError("duplicate step id: " + step_id)
        step_ids.add(step_id)
        tool = _text(raw_step["tool"], path + ".tool")
        if tool not in allowed_tools:
            raise WorkflowTemplateError("template step uses a tool outside allowed_tools: " + tool)
        args = raw_step["args"]
        if not isinstance(args, Mapping):
            raise WorkflowTemplateError(path + ".args must be an object")
        depends_on = raw_step.get("depends_on", [])
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) and item.strip() for item in depends_on
        ):
            raise WorkflowTemplateError(path + ".depends_on must be an array of strings")
        if len(set(depends_on)) != len(depends_on):
            raise WorkflowTemplateError(path + ".depends_on contains duplicate ids")
        normalized.append(
            {
                "id": step_id,
                "tool": tool,
                "args": copy.deepcopy(dict(args)),
                "depends_on": list(depends_on),
            }
        )
    graph: Dict[str, List[str]] = {}
    for step in normalized:
        dependencies = step["depends_on"]
        unknown_dependencies = sorted(set(dependencies) - step_ids)
        if unknown_dependencies:
            raise WorkflowTemplateError(
                "template step {} depends on unknown step: {}".format(
                    step["id"], ", ".join(unknown_dependencies)
                )
            )
        if step["id"] in dependencies:
            raise WorkflowTemplateError("template step cannot depend on itself: " + step["id"])
        graph[step["id"]] = dependencies
    _assert_acyclic(graph)
    return normalized


def _normalize_output_template(
    raw_output: Any,
    result_types: List[str],
) -> Dict[str, Any]:
    if not isinstance(raw_output, Mapping):
        raise WorkflowTemplateError("template.output_template must be an object")
    output = copy.deepcopy(dict(raw_output))
    result_type = output.get("type")
    if not isinstance(result_type, str) or not result_type.strip():
        raise WorkflowTemplateError("template.output_template.type must be a non-empty string")
    if result_type not in result_types:
        raise WorkflowTemplateError("template.output_template.type is not allowed by template")
    return output


def _render_template_value(value: Any, constraints: Mapping[str, Any]) -> Any:
    if isinstance(value, list):
        return [_render_template_value(item, constraints) for item in value]
    if isinstance(value, Mapping):
        if set(value) == {"$constraint"}:
            name = value["$constraint"]
            if not isinstance(name, str) or not name:
                raise WorkflowTemplateError("$constraint placeholder requires a name")
            if name not in constraints:
                raise WorkflowTemplateError("missing compiled workflow constraint: " + name)
            return copy.deepcopy(constraints[name])
        if set(value) == {"$result_ref"}:
            ref = value["$result_ref"]
            if not isinstance(ref, Mapping):
                raise WorkflowTemplateError("$result_ref placeholder must be an object")
            step = ref.get("step")
            path = ref.get("path")
            if not isinstance(step, str) or not step.strip():
                raise WorkflowTemplateError("$result_ref.step must be a non-empty string")
            if not isinstance(path, str) or not path.strip():
                raise WorkflowTemplateError("$result_ref.path must be a non-empty string")
            return {"$from": step.strip(), "path": path.strip()}
        return {
            key: _render_template_value(item, constraints)
            for key, item in value.items()
        }
    return copy.deepcopy(value)


def _normalize_constraint_value(value: Any, spec: Mapping[str, Any]) -> Any:
    name = spec["name"]
    kind = spec["type"]
    if kind == "string":
        if not isinstance(value, str) or not value.strip():
            raise WorkflowTemplateError("constraint {} must be a non-empty string".format(name))
        value = value.strip()
        if "min_length" in spec and len(value) < spec["min_length"]:
            raise WorkflowTemplateError("constraint {} is shorter than minimum length".format(name))
        if "max_length" in spec and len(value) > spec["max_length"]:
            raise WorkflowTemplateError("constraint {} exceeds maximum length".format(name))
        return value
    if kind in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkflowTemplateError("constraint {} must be a number".format(name))
        number = float(value)
        if not math.isfinite(number):
            raise WorkflowTemplateError("constraint {} must be finite".format(name))
        if kind == "integer" and number != int(number):
            raise WorkflowTemplateError("constraint {} must be an integer".format(name))
        if "min" in spec and number < spec["min"]:
            raise WorkflowTemplateError("constraint {} is below minimum".format(name))
        if "max" in spec and number > spec["max"]:
            raise WorkflowTemplateError("constraint {} exceeds maximum".format(name))
        return int(number) if kind == "integer" else number
    if kind == "boolean":
        if not isinstance(value, bool):
            raise WorkflowTemplateError("constraint {} must be boolean".format(name))
        return value
    if kind == "enum":
        if value not in spec["choices"]:
            raise WorkflowTemplateError("constraint {} must be one of: {}".format(name, ", ".join(spec["choices"])))
        return value
    raise WorkflowTemplateError("unsupported constraint type: " + kind)
