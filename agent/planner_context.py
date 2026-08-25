"""Planner-only projections of the richer runtime context contracts.

The Runtime keeps complete capability and workflow evidence for validation,
repair, and result projection.  A planner needs a much smaller interface:
selected capabilities, executable tool arguments, workflow DAG hints, and
bounded availability facts.  Keeping that projection here prevents provider
prompt concerns from leaking into Domain Packs or public evidence contracts.
"""

from __future__ import annotations

from typing import Any, Mapping


PLANNER_CONTEXT_PROJECTION_SCHEMA_VERSION = "spatial-agent.planner-context-projection.v1"


def project_planner_sections(
    *,
    capability_discovery: Mapping[str, Any],
    capability_catalog: Mapping[str, Any],
    workflow_selection: Mapping[str, Any],
    workflow_templates: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the three bounded sections needed to construct a TaskPlan."""

    return {
        "capability_discovery": _project_capability_discovery(capability_discovery),
        "capability_catalog": _project_capability_catalog(capability_catalog),
        "workflow_selection": _project_workflow_selection(workflow_selection),
        "workflow_templates": _project_workflow_templates(workflow_templates),
    }


def _project_capability_discovery(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "schema_version",
            "domain_id",
            "available",
            "selection_state",
            "selected_capability_id",
            "candidate_ids",
            "candidate_count",
            "signals",
            "tasks",
            "constraints",
            "entities",
            "missing_fields",
            "suggested_capability_ids",
            "discovery_reason_code",
        ),
    )
    guidance = value.get("guidance")
    if isinstance(guidance, Mapping):
        projected["guidance"] = _copy_fields(
            guidance,
            (
                "schema_version",
                "state",
                "reason_code",
                "missing_fields",
                "suggested_capability_ids",
                "next_actions",
            ),
        )
    return projected


def _project_capability_catalog(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "schema_version",
            "domain_id",
            "catalog_version",
            "environment",
            "health_status",
            "data_readiness",
            "analysis_ready",
            "capability_count",
            "selected_capability_ids",
            "tool_schema_count",
        ),
    )
    projected["capabilities"] = [
        _project_capability(item)
        for item in (value.get("capabilities") or [])[:4]
        if isinstance(item, Mapping)
    ]
    schemas = value.get("tool_schemas")
    projected["tool_schemas"] = {
        str(name)[:96]: _project_tool_schema(schema)
        for name, schema in list(schemas.items())[:16]
        if isinstance(schema, Mapping)
    } if isinstance(schemas, Mapping) else {}
    projected["tool_schema_count"] = len(projected["tool_schemas"])
    return projected


def _project_capability(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "id",
            "label",
            "description",
            "datasets",
            "tools",
            "result_types",
            "available",
            "availability_mode",
            "availability_reason",
            "missing_datasets",
            "request_requirements",
        ),
    )
    evidence = value.get("evidence")
    if isinstance(evidence, Mapping):
        compact_evidence = _copy_fields(
            evidence,
            ("schema_version", "status", "reason_code", "missing_reasons"),
        )
        alignment = evidence.get("alignment")
        if isinstance(alignment, Mapping):
            compact_evidence["alignment"] = _copy_fields(
                alignment, ("status", "reason_code")
            )
        projected["evidence"] = compact_evidence
    dataset_evidence = value.get("dataset_evidence")
    if isinstance(dataset_evidence, Mapping):
        projected["dataset_evidence"] = {
            str(name)[:96]: _project_dataset_evidence(item)
            for name, item in list(dataset_evidence.items())[:16]
            if isinstance(item, Mapping)
        }
    return projected


def _project_dataset_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "status",
            "quality",
            "stage",
            "coverage",
            "time_range",
            "crs",
            "resolution",
            "availability_reason",
            "file_count",
            "checked_files",
            "analysis_ready",
        ),
    )
    discovery = value.get("discovery")
    if isinstance(discovery, Mapping):
        projected["discovery"] = {
            str(key)[:48]: item
            for key, item in list(discovery.items())[:16]
        }
    return projected


def _project_tool_schema(value: Mapping[str, Any]) -> dict[str, Any]:
    # Output contracts, provider permissions, dependencies, and timeouts are
    # enforced by ToolRegistry.  The Planner only chooses arguments and must
    # know whether a tool requires explicit approval.
    return _copy_fields(
        value,
        (
            "description",
            "requires_approval",
            "required",
            "arguments",
            "additional_properties",
        ),
    )


def _project_workflow_selection(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "schema_version",
            "available",
            "state",
            "reason_code",
            "domain_id",
            "selected_by",
            "selected_capability_id",
            "candidate_ids",
            "candidate_count",
            "workflow_template_id",
            "workflow_template_version",
            "candidate_workflow_ids",
            "suggested_capability_ids",
            "missing_fields",
            "request_facts_schema_version",
        ),
    )
    projected["workflow_components"] = [
        _copy_fields(
            item,
            (
                "component_id",
                "template_id",
                "template_version",
                "depends_on_components",
                "constraint_keys",
            ),
        )
        for item in (value.get("workflow_components") or [])[:12]
        if isinstance(item, Mapping)
    ]

    details = [
        item
        for item in (value.get("candidate_details") or [])
        if isinstance(item, Mapping)
    ]
    if str(value.get("state") or "") == "selected":
        selected_id = str(value.get("selected_capability_id") or "")
        selected = [item for item in details if str(item.get("id") or "") == selected_id]
        details = (selected or details[:1])[:1]
    projected["candidate_summaries"] = [
        _copy_fields(
            item,
            ("id", "label", "description", "available", "input_facts", "result_types"),
        )
        for item in details[:8]
    ]
    return projected


def _project_workflow_templates(value: Mapping[str, Any]) -> dict[str, Any]:
    projected = _copy_fields(
        value,
        (
            "schema_version",
            "template_count",
            "returned_count",
            "omitted_count",
            "selection_filtered",
        ),
    )
    projected["templates"] = [
        _copy_fields(
            item,
            (
                "id",
                "goal_template",
                "allowed_tools",
                "result_types",
                "required_constraints",
                "max_steps",
                "step_blueprint",
                "output_type",
            ),
        )
        for item in (value.get("templates") or [])[:4]
        if isinstance(item, Mapping)
    ]
    return projected


def _copy_fields(value: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: value[name] for name in names if name in value}
