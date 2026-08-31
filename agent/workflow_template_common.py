"""Shared workflow-template contract types, constants and low-level helpers.

Used by both the catalog and the compiler so their split stays acyclic.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Optional, Set


class WorkflowTemplateError(ValueError):
    """Raised when a workflow template or a plan violates its contract."""


DEFAULT_TEMPLATE_VERSION = "1.0.0"
WORKFLOW_COMPOSITION_SCHEMA_VERSION = "spatial-agent.workflow-composition.v1"
SUPPORTED_CONSTRAINT_TYPES = {"string", "number", "integer", "boolean", "enum", "array"}


# GIS catalog data lives in domains.gis.workflow_templates. The lazy compatibility
# helpers below preserve old imports without making Runtime depend on that data.
def _legacy_gis_catalog():
    from domains.gis.workflow_templates import workflow_template_catalog

    return workflow_template_catalog()


def _legacy_known_tools():
    from domains.gis.workflow_templates import KNOWN_TOOL_NAMES

    return KNOWN_TOOL_NAMES


def _legacy_known_result_types():
    from domains.gis.workflow_templates import KNOWN_RESULT_TYPES

    return KNOWN_RESULT_TYPES


def __getattr__(name: str):
    if name in {"KNOWN_TOOL_NAMES", "KNOWN_TOOLS", "KNOWN_RESULT_TYPES", "WORKFLOW_TEMPLATE_CATALOG"}:
        from domains.gis import workflow_templates as gis_templates

        return getattr(gis_templates, name)
    raise AttributeError(name)


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
_CONSTRAINT_SPEC_KEYS = {"name", "label", "type", "required", "min", "max", "min_length", "max_length", "min_items", "max_items", "choices", "default"}
_CHINESE_LABEL = re.compile(r"[\u3400-\u9fff]")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

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
        for key in ("min", "max", "min_length", "max_length", "min_items", "max_items"):
            if key in raw:
                value = raw[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise WorkflowTemplateError(path + "." + key + " must be a finite number")
                item[key] = int(value) if key.endswith(("length", "items")) else float(value)
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
