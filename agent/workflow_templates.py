"""Controlled, JSON-safe workflow template contracts.

This module is intentionally independent from the planner and runtime.  A
caller can validate a template before registering it and validate a plan
against that template before execution without changing the existing plan
parser contract.
"""

import copy
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


# The values use only JSON-native objects, arrays, strings, numbers, booleans,
# and null.  Keep this directory declarative so it can later be loaded from a
# signed configuration without changing the validation API.
WORKFLOW_TEMPLATE_CATALOG = {
    "admin_boundary_query": {
        "id": "admin_boundary_query",
        "label": "行政区边界查询",
        "allowed_tools": ["get_dataset_schema", "range_query"],
        "result_types": ["admin_area_result"],
        "max_steps": 2,
        "required_constraints": ["admin_name"],
    },
    "raster_metadata": {
        "id": "raster_metadata",
        "label": "栅格元数据查询",
        "allowed_tools": ["get_raster_metadata"],
        "result_types": ["raster_metadata_result"],
        "max_steps": 1,
        "required_constraints": ["dataset"],
    },
    "spatial_overview": {
        "id": "spatial_overview",
        "label": "区域空间总览",
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
    },
    "constrained_buildability": {
        "id": "constrained_buildability",
        "label": "道路与水体约束筛选",
        "allowed_tools": [
            "get_dataset_health_report",
            "get_zonal_constrained_buildability_analysis",
        ],
        "result_types": ["constrained_buildability_result"],
        "max_steps": 2,
        "required_constraints": ["admin_name", "slope_limit_degrees"],
    },
}


_TEMPLATE_KEYS = {
    "id",
    "label",
    "allowed_tools",
    "result_types",
    "max_steps",
    "required_constraints",
}
_PLAN_KEYS = {"template_id", "goal", "constraints", "steps", "output", "assumptions"}
_STEP_KEYS = {"id", "tool", "args", "depends_on"}
_CHINESE_LABEL = re.compile(r"[\u3400-\u9fff]")


def workflow_template_catalog() -> Dict[str, Dict[str, Any]]:
    """Return an isolated JSON-safe copy of the built-in template directory."""

    return copy.deepcopy(WORKFLOW_TEMPLATE_CATALOG)


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

    for key in _TEMPLATE_KEYS:
        if key not in template:
            raise WorkflowTemplateError("template missing required field: " + key)

    template_id = _text(template["id"], "template.id")
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

    return {
        "id": template_id,
        "label": label,
        "allowed_tools": tool_names,
        "result_types": result_types,
        "max_steps": max_steps,
        "required_constraints": constraints,
    }


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

    constraints = plan.get("constraints", {})
    if not isinstance(constraints, dict):
        raise WorkflowTemplateError("plan.constraints must be an object")
    missing_constraints = [
        name
        for name in normalized_template["required_constraints"]
        if name not in constraints or _is_empty_constraint(constraints[name])
    ]
    if missing_constraints:
        raise WorkflowTemplateError(
            "plan is missing required constraints: " + ", ".join(missing_constraints)
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
    normalized_plan["steps"] = normalized_steps
    normalized_plan["constraints"] = copy.deepcopy(constraints)
    normalized_plan["output"] = copy.deepcopy(dict(output))
    return normalized_plan


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
