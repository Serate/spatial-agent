"""Workflow template compiler: validate, compile and revise workflow plans.

Depends only on ``workflow_template_common`` and ``workflow_template_catalog``
(acyclic).  Re-exported by the ``workflow_templates`` compatibility facade.
"""

from __future__ import annotations

import copy
import json
import math
import re
from itertools import count
from collections.abc import Mapping, Iterable
from typing import Any, Dict, List, Optional, Set

from .common import (
    WorkflowTemplateError,
    DEFAULT_TEMPLATE_VERSION,
    WORKFLOW_COMPOSITION_SCHEMA_VERSION,
    SUPPORTED_CONSTRAINT_TYPES,
    _TEMPLATE_KEYS, _REQUIRED_TEMPLATE_KEYS, _PLAN_KEYS, _STEP_KEYS,
    _STEP_BLUEPRINT_KEYS, _CONSTRAINT_SPEC_KEYS, _CHINESE_LABEL, _SEMVER,
    _text, _string_list, _value_set, _assert_json_safe, _assert_acyclic,
    _normalize_constraint_specs, _normalize_output_template, _normalize_step_blueprint,
)
from .catalog import (
    get_workflow_template,
    workflow_template_catalog,
    validate_workflow_template,
    validate_workflow_template_catalog,
    workflow_template_context_summary,
    _legacy_gis_catalog,
    _legacy_known_tools,
    _legacy_known_result_types,
    _argument_context_shape,
    _constraint_context_summary,
)


def compile_workflow_plan(
    template: str | Mapping[str, Any],
    constraints: Mapping[str, Any],
    *,
    evidence: Optional[Iterable[str]] = None,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
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
    normalized_template = validate_workflow_template(
        template_definition,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    normalized_constraints = normalize_workflow_constraints(
        normalized_template,
        constraints,
        catalog=catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
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
        "evidence": normalize_workflow_evidence(
            normalized_template,
            evidence,
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        ),
        "steps": steps,
        "output": output,
    }
    return validate_workflow_plan(
        normalized_template,
        plan,
        catalog=catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )

def compile_workflow_composition(
    components: Iterable[Mapping[str, Any]],
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
    output_type: str = "workflow_composition_result",
    goal: str = "compose selected workflow components",
    output_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile selected templates into one isolated, dependency-safe DAG."""

    values = list(components) if isinstance(components, Iterable) and not isinstance(components, (str, bytes, Mapping)) else []
    if not values:
        raise WorkflowTemplateError("workflow composition requires components")
    def normalize_component(component: Mapping[str, Any]) -> Mapping[str, Any]:
        return normalize_workflow_selection(
            str(component.get("template_id") or ""),
            component.get("constraints")
            if isinstance(component.get("constraints"), Mapping)
            else {},
            component.get("evidence"),
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        )

    normalized = normalize_workflow_composition(
        {"components": values},
        component_normalizer=normalize_component,
    )
    compiled: list[Dict[str, Any]] = []
    component_steps: Dict[str, list[Dict[str, Any]]] = {}
    for component in normalized["components"]:
        component_id = str(component["component_id"])
        prefix = _safe_component_prefix(component_id)
        plan = compile_workflow_plan(
            str(component["template_id"]),
            component.get("constraints") if isinstance(component.get("constraints"), Mapping) else {},
            evidence=component.get("evidence"),
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        )
        steps = []
        old_ids = {str(item["id"]): f"{prefix}--{item['id']}" for item in plan["steps"]}
        for item in plan["steps"]:
            step = {
                "id": old_ids[str(item["id"])],
                "tool": item["tool"],
                "args": _rewrite_component_references(item.get("args", {}), old_ids),
                "depends_on": [old_ids.get(str(dep), f"{prefix}--{dep}") for dep in item.get("depends_on", [])],
            }
            steps.append(step)
        depended_on = set(dep for step in steps for dep in step["depends_on"])
        roots = [step for step in steps if step["id"] not in depended_on]
        component_steps[component_id] = steps
        compiled.extend(steps)

    for component in normalized["components"]:
        dependencies = component.get("depends_on_components") or []
        if not dependencies:
            continue
        component_id = str(component["component_id"])
        own_steps = component_steps[component_id]
        depended_on = {dep for step in own_steps for dep in step["depends_on"]}
        roots = [step for step in own_steps if step["id"] not in depended_on]
        terminals = []
        for dependency in dependencies:
            dependency_steps = component_steps[str(dependency)]
            dependency_ids = {step["id"] for step in dependency_steps}
            dependency_inputs = {item for step in dependency_steps for item in step["depends_on"]}
            terminals.extend(step for step in dependency_steps if step["id"] not in dependency_inputs and step["id"] in dependency_ids)
        for root in roots:
            root["depends_on"] = list(dict.fromkeys(root["depends_on"] + [item["id"] for item in terminals]))

    return {
        "schema_version": WORKFLOW_COMPOSITION_SCHEMA_VERSION,
        "goal": goal,
        "steps": compiled,
        "output": {
            "type": output_type,
            "summary": True,
            "component_template_ids": normalized["component_template_ids"],
        } | (dict(output_overrides) if output_overrides else {}),
        "assumptions": [
            "workflow components are Domain-owned and each component remains independently schema-validated",
        ],
        "components": normalized["components"],
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
        _legacy_known_tools() if known_tools is None else known_tools,
        "known_tools",
    )
    available_results = _value_set(
        _legacy_known_result_types() if known_result_types is None else known_result_types,
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
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Apply a bounded user revision and revalidate the complete plan."""

    current = validate_workflow_plan(
        template,
        plan,
        catalog=catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    merged_constraints = dict(current["constraints"])
    if constraints is not None:
        if not isinstance(constraints, Mapping):
            raise WorkflowTemplateError("constraints must be an object")
        merged_constraints.update(constraints)
    revised = copy.deepcopy(dict(current))
    revised["constraints"] = merged_constraints
    if evidence is not None:
        revised["evidence"] = list(evidence)
    return validate_workflow_plan(
        template,
        revised,
        catalog=catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )

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
        selected_catalog = _legacy_gis_catalog() if catalog is None else catalog
        if not isinstance(selected_catalog, Mapping):
            raise WorkflowTemplateError("catalog must be an object")
        try:
            return selected_catalog[template]
        except KeyError as exc:
            raise WorkflowTemplateError("unknown workflow template: " + template) from exc
    if isinstance(template, Mapping):
        return template
    raise WorkflowTemplateError("template must be an id or an object")

def normalize_workflow_composition(
    workflow: Mapping[str, Any],
    *,
    component_normalizer: Any = None,
    composition_template_id: str | None = None,
) -> Dict[str, Any]:
    """Normalize a bounded list of Domain-owned workflow components.

    The public interface is deliberately small: each component names one
    template, its constraints/evidence, and optional component dependencies.
    Domain Packs may inject their existing single-template normalizer; the
    compiler itself never interprets domain fields or tool names.
    """

    if not isinstance(workflow, Mapping):
        raise WorkflowTemplateError("workflow must be an object")
    raw_components = workflow.get("components")
    if not isinstance(raw_components, (list, tuple)) or not raw_components:
        raise WorkflowTemplateError("workflow.components must be a non-empty array")
    if len(raw_components) > 8:
        raise WorkflowTemplateError("workflow.components may contain at most 8 items")

    components: list[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(raw_components):
        if not isinstance(raw, Mapping):
            raise WorkflowTemplateError("workflow component must be an object")
        template_id = str(raw.get("template_id") or "").strip()
        if not template_id:
            raise WorkflowTemplateError("workflow component.template_id is required")
        component_id = str(raw.get("component_id") or template_id or f"component-{index + 1}").strip()
        if not component_id or component_id in seen:
            raise WorkflowTemplateError("workflow component IDs must be unique")
        seen.add(component_id)
        normalizer = component_normalizer
        normalized = (
            normalizer(dict(raw))
            if callable(normalizer)
            else normalize_workflow_selection(
                template_id,
                raw.get("constraints") if isinstance(raw.get("constraints"), Mapping) else {},
                raw.get("evidence"),
            )
        )
        if not isinstance(normalized, Mapping):
            raise WorkflowTemplateError("component normalizer must return an object")
        normalized = dict(normalized)
        for evidence_key in ("evidence_summary", "evidence_state"):
            if isinstance(raw.get(evidence_key), Mapping):
                normalized[evidence_key] = copy.deepcopy(dict(raw[evidence_key]))
        dependencies = raw.get("depends_on_components", raw.get("depends_on", []))
        if not isinstance(dependencies, (list, tuple)):
            raise WorkflowTemplateError("component dependencies must be an array")
        dependencies = [str(item).strip() for item in dependencies[:8] if str(item).strip()]
        if component_id in dependencies:
            raise WorkflowTemplateError("workflow component cannot depend on itself")
        normalized["component_id"] = component_id[:96]
        normalized["depends_on_components"] = list(dict.fromkeys(dependencies))
        components.append(normalized)

    component_ids = {item["component_id"] for item in components}
    for component in components:
        unknown = sorted(set(component["depends_on_components"]) - component_ids)
        if unknown:
            raise WorkflowTemplateError(
                "workflow component dependency is unknown: " + ", ".join(unknown)
            )
    if _has_component_cycle(components):
        raise WorkflowTemplateError("workflow component dependencies contain a cycle")

    template_ids = [str(item.get("template_id")) for item in components]
    evidence = []
    for component in components:
        for value in component.get("evidence") or []:
            if value not in evidence:
                evidence.append(value)
    result: Dict[str, Any] = {
        "schema_version": WORKFLOW_COMPOSITION_SCHEMA_VERSION,
        "template_id": composition_template_id or (template_ids[0] if len(template_ids) == 1 else "workflow_composition"),
        "template_version": "1.0.0",
        "components": components,
        "component_template_ids": template_ids[:8],
        "constraints": dict(components[0].get("constraints") or {}) if len(components) == 1 else {},
        "evidence": evidence[:16],
    }
    if len(components) == 1:
        result["template_version"] = components[0].get("template_version") or "1.0.0"
    return result

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
    *,
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
    known_tools: Optional[Iterable[str]] = None,
    known_result_types: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Normalize the user-selected template before a run is queued."""

    template = get_workflow_template(template_id, catalog=catalog)
    normalized_constraints = normalize_workflow_constraints(
        template,
        {} if constraints is None else constraints,
        catalog=catalog,
        known_tools=known_tools,
        known_result_types=known_result_types,
    )
    return {
        "template_id": template["id"],
        "template_version": template["version"],
        "constraints": normalized_constraints,
        "evidence": normalize_workflow_evidence(
            template,
            evidence,
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        ),
    }

def workflow_request_hint(request: str, workflow: Optional[Mapping[str, Any]]) -> str:
    """Add bounded, domain-neutral workflow context to planner input.

    Domain-specific labels and parsing belong to the active Domain Pack. This
    compatibility helper only forwards safe, bounded constraint key/value
    pairs, so a non-GIS Domain can reuse it without inheriting GIS vocabulary.
    """

    if not workflow:
        return request
    if not isinstance(workflow, Mapping):
        raise WorkflowTemplateError("workflow must be an object")
    constraints = workflow.get("constraints", {})
    if not isinstance(constraints, Mapping):
        raise WorkflowTemplateError("workflow.constraints must be an object")
    parts = []
    for key, value in constraints.items():
        key_text = str(key or "").strip()[:64]
        if (
            not key_text
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", key_text)
            or any(token in key_text.lower() for token in ("password", "secret", "token", "credential", "api_key"))
        ):
            continue
        safe_value = _workflow_hint_value(value)
        if safe_value is not None:
            parts.append("{}={}".format(key_text, safe_value))
    if not parts:
        return request
    return "{}\n[workflow parameters: {}]".format(request.strip(), "；".join(parts))

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

def _has_component_cycle(components: Iterable[Mapping[str, Any]]) -> bool:
    graph = {str(item["component_id"]): set(item.get("depends_on_components") or []) for item in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dep) for dep in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)

def _is_empty_constraint(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())

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
    if kind == "array":
        if not isinstance(value, (list, tuple)):
            raise WorkflowTemplateError("constraint {} must be an array".format(name))
        values = list(value)
        if "min_items" in spec and len(values) < spec["min_items"]:
            raise WorkflowTemplateError("constraint {} has too few items".format(name))
        if "max_items" in spec and len(values) > spec["max_items"]:
            raise WorkflowTemplateError("constraint {} has too many items".format(name))
        if not all(isinstance(item, str) and item.strip() for item in values):
            raise WorkflowTemplateError("constraint {} items must be non-empty strings".format(name))
        return [item.strip() for item in values]
    if kind == "enum":
        if value not in spec["choices"]:
            raise WorkflowTemplateError("constraint {} must be one of: {}".format(name, ", ".join(spec["choices"])))
        return value
    raise WorkflowTemplateError("unsupported constraint type: " + kind)

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

def _rewrite_component_references(value: Any, old_ids: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        result = {key: _rewrite_component_references(item, old_ids) for key, item in value.items()}
        for key in ("step", "from", "to"):
            if key in result and str(result[key]) in old_ids:
                result[key] = old_ids[str(result[key])]
        return result
    if isinstance(value, list):
        return [_rewrite_component_references(item, old_ids) for item in value]
    return value

def _safe_component_prefix(value: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")[:48]
    return prefix or "component"
