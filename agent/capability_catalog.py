"""The shared, safe capability contract for planners, APIs, and the Console."""

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

from .workflow_templates import workflow_template_catalog
from domains.gis.catalog import (
    GIS_CAPABILITIES,
    GIS_DATASET_GROUPS,
    GIS_DATASET_TOOL_CAPABILITIES,
)


CAPABILITY_CONTEXT_SCHEMA_VERSION = "spatial-agent.capability-catalog-context.v1"


DATASET_TOOL_CAPABILITIES = GIS_DATASET_TOOL_CAPABILITIES
DATASET_GROUPS = GIS_DATASET_GROUPS
_CAPABILITIES = GIS_CAPABILITIES


def capability_catalog(
    *,
    environment: str = "unknown",
    dataset_capabilities: Mapping[str, Iterable[str]] | None = None,
    dataset_statuses: Mapping[str, str] | None = None,
    analysis_ready: Mapping[str, Any] | None = None,
    capability_definitions: Iterable[Mapping[str, Any]] | None = None,
    dataset_tool_capabilities: Mapping[str, Iterable[str]] | None = None,
    dataset_groups: Mapping[str, Iterable[str]] | None = None,
    domain_id: str = "gis",
    analysis_ready_capability_ids: Iterable[str] | None = None,
    workflow_templates: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a JSON-safe snapshot; callers cannot mutate the source contract."""
    has_dataset_gate = dataset_capabilities is not None
    available = {
        name: sorted(set(values))
        for name, values in (dataset_capabilities or {}).items()
    }
    definitions = tuple(
        _CAPABILITIES if capability_definitions is None else capability_definitions
    )
    tool_capabilities = (
        DATASET_TOOL_CAPABILITIES
        if dataset_tool_capabilities is None
        else dataset_tool_capabilities
    )
    groups = DATASET_GROUPS if dataset_groups is None else dataset_groups
    analysis_ready_ids = set(
        analysis_ready_capability_ids
        if analysis_ready_capability_ids is not None
        else {"buildability_screening", "constrained_buildability_screening"}
    )
    capabilities = []
    for item in definitions:
        entry = deepcopy(item)
        missing = sorted(
            dataset
            for dataset in entry["datasets"]
            if has_dataset_gate and not available.get(dataset)
        )
        entry["environment_supported"] = (
            environment == "unknown" or environment in entry["environments"]
        )
        entry["dataset_gate"] = (
            "unknown" if not has_dataset_gate else "ready" if not missing else "missing"
        )
        analysis_required = bool((analysis_ready or {}).get("required", False))
        analysis_status = (analysis_ready or {}).get("status")
        needs_analysis_ready = item["id"] in analysis_ready_ids
        if needs_analysis_ready and analysis_required and analysis_status != "ready":
            entry["dataset_gate"] = "missing"
        entry["missing_datasets"] = missing
        if needs_analysis_ready and analysis_required and analysis_status != "ready":
            entry["missing_datasets"] = sorted(
                set(entry["missing_datasets"]) | {"analysis_ready"}
            )
        entry["data_layer"] = _capability_data_layer(entry["datasets"], groups)
        entry["capability_status"] = _capability_status(
            entry["datasets"], dataset_statuses
        )
        entry["available"] = (
            entry["environment_supported"]
            and entry["dataset_gate"] != "missing"
            and (
                dataset_statuses is None
                or entry["capability_status"] not in {"unavailable", "unknown"}
            )
        )
        if needs_analysis_ready and analysis_required and analysis_status != "ready":
            entry["available"] = False
        capabilities.append(entry)
    return {
        "version": "1.0",
        "domain_id": str(domain_id),
        "environment": environment,
        "capabilities": capabilities,
        "dataset_tools": deepcopy(tool_capabilities),
        "available_dataset_tools": available,
        "dataset_groups": {
            name: list(datasets) for name, datasets in groups.items()
        },
        "workflow_templates": deepcopy(
            workflow_templates
            if workflow_templates is not None
            else workflow_template_catalog()
        ),
    }


def capability_suggestions() -> list[Dict[str, str]]:
    """Return the stable, user-facing capability choices for clarification UI."""
    return [
        {"id": str(item["id"]), "label": str(item["label"])}
        for item in _CAPABILITIES
    ]


def capability_context_summary(
    *,
    catalog: Mapping[str, Any] | None = None,
    tool_definitions: Mapping[str, Mapping[str, Any]] | None = None,
    tool_provider: Mapping[str, Any] | str | None = None,
    tool_provider_health: Mapping[str, Any] | None = None,
    tool_governance: Mapping[str, Any] | None = None,
    selected_capability_ids: Iterable[str] | None = None,
    max_capabilities: int = 10,
    max_tools: int = 16,
) -> Dict[str, Any]:
    """Return a compact planner-facing capability catalog summary."""
    source = catalog or capability_catalog()
    capabilities = [
        item for item in source.get("capabilities", [])
        if isinstance(item, Mapping) and item.get("id")
    ]
    selected = [str(item) for item in (selected_capability_ids or []) if item]
    selected_index = {capability_id: index for index, capability_id in enumerate(selected)}
    if selected_index:
        candidates = [
            item for item in capabilities
            if str(item.get("id")) in selected_index
        ]
        ordered = sorted(
            candidates,
            key=lambda item: selected_index.get(str(item.get("id")), len(selected_index)),
        )[:max_capabilities]
    else:
        ordered = capabilities[:max_capabilities]
    capability_items = [_capability_context_item(item) for item in ordered]
    tool_names = []
    seen_tools = set()
    for item in capability_items:
        for tool_name in item["tools"]:
            if tool_name not in seen_tools:
                tool_names.append(tool_name)
                seen_tools.add(tool_name)
    tool_schema_source = tool_definitions or {}
    tool_schemas = {
        name: _safe_tool_schema_summary(tool_schema_source[name])
        for name in tool_names[:max_tools]
        if name in tool_schema_source and isinstance(tool_schema_source[name], Mapping)
    }
    analysis_ready = source.get("analysis_ready")
    result = {
        "schema_version": CAPABILITY_CONTEXT_SCHEMA_VERSION,
        "domain_id": source.get("domain_id", "unknown"),
        "catalog_version": source.get("version"),
        "environment": source.get("environment", "unknown"),
        "health_status": source.get("health_status", "unknown"),
        "data_readiness": source.get("data_readiness", "unknown"),
        "analysis_ready": _safe_analysis_ready_summary(analysis_ready),
        "capability_count": len(capabilities),
        "selected_capability_ids": [item for item in selected if item],
        "capabilities": capability_items,
        "tool_schemas": tool_schemas,
        "tool_schema_count": len(tool_schemas),
        "dataset_groups": deepcopy(source.get("dataset_groups") or {}),
    }
    if tool_provider is not None:
        result["tool_provider"] = _safe_tool_provider_summary(tool_provider)
    if tool_provider_health is not None:
        result["tool_provider_health"] = _safe_tool_provider_health(tool_provider_health)
    if tool_governance is not None:
        result["tool_governance"] = _safe_tool_governance(tool_governance, max_tools=max_tools)
    return result


def runtime_capability_catalog(
    health_report: Mapping[str, Any],
    *,
    environment: str = "unknown",
    tool_provider: Mapping[str, Any] | None = None,
    tool_provider_health: Mapping[str, Any] | None = None,
    tool_governance: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Attach bounded data evidence to the static capability contract."""
    dataset_reports = {
        str(item.get("dataset")): item
        for item in health_report.get("datasets", [])
        if isinstance(item, Mapping) and item.get("dataset")
    }
    dataset_capabilities = health_report.get("capabilities")
    dataset_statuses = {
        name: str(item.get("status", "unknown"))
        for name, item in dataset_reports.items()
    }
    snapshot = capability_catalog(
        environment=environment,
        dataset_capabilities=dataset_capabilities if isinstance(dataset_capabilities, Mapping) else None,
        dataset_statuses=dataset_statuses,
        analysis_ready=health_report.get("analysis_ready") if isinstance(health_report.get("analysis_ready"), Mapping) else None,
    )
    evidence = {}
    for name, item in dataset_reports.items():
        evidence[name] = {
            "status": item.get("status", "unknown"),
            "quality": item.get("status", "unknown"),
            "coverage": item.get("bounds"),
            "crs": list(item.get("crs_values") or []),
            "file_count": int(item.get("file_count") or 0),
            "checked_files": int((item.get("metrics") or {}).get("checked_files") or 0),
            "updated_at": health_report.get("updated_at"),
        }
    for item in snapshot["capabilities"]:
        item["runtime_evidence"] = {
            "datasets": {
                name: evidence.get(name, {"status": "unknown"})
                for name in item["datasets"]
            },
            "updated_at": health_report.get("updated_at"),
        }
    snapshot["updated_at"] = health_report.get("updated_at")
    snapshot["data_evidence"] = evidence
    snapshot["health_status"] = health_report.get("status", "unknown")
    snapshot["core_health_status"] = health_report.get(
        "core_status", health_report.get("status", "unknown")
    )
    snapshot["optional_health_status"] = health_report.get(
        "optional_status", "unknown"
    )
    manifest = health_report.get("manifest")
    if isinstance(manifest, Mapping):
        snapshot["manifest"] = {
            "status": manifest.get("status", "unknown"),
            "required": bool(manifest.get("required", False)),
            "verification_mode": manifest.get("verification_mode", "metadata"),
            "hashes_verified": bool(manifest.get("hashes_verified", False)),
            "verified_files": int(manifest.get("verified_files") or 0),
            "mismatch_count": int(manifest.get("mismatch_count") or 0),
        }
    snapshot["data_readiness"] = health_report.get("data_readiness", "ready")
    if isinstance(tool_provider, Mapping):
        snapshot["tool_provider"] = _safe_tool_provider_summary(tool_provider)
    if isinstance(tool_provider_health, Mapping):
        snapshot["tool_provider_health"] = _safe_tool_provider_health(tool_provider_health)
    if isinstance(tool_governance, Mapping):
        snapshot["tool_governance"] = _safe_tool_governance(
            tool_governance,
            max_tools=0,
        )
    analysis_ready = health_report.get("analysis_ready")
    if isinstance(analysis_ready, Mapping):
        snapshot["analysis_ready"] = {
            "status": analysis_ready.get("status", "unknown"),
            "required": bool(analysis_ready.get("required", False)),
            "derived_version": str(analysis_ready.get("derived_version", "unknown"))[:128],
            "target_grid": deepcopy(analysis_ready.get("target_grid") or {}),
            "grid_alignment": deepcopy(analysis_ready.get("grid_alignment") or {}),
            "verification_mode": analysis_ready.get("verification_mode", "metadata"),
        }
        source_binding = analysis_ready.get("source_binding")
        if isinstance(source_binding, Mapping):
            snapshot["analysis_ready"]["source_binding"] = _safe_source_binding_summary(source_binding)
        output_manifest = analysis_ready.get("output_manifest")
        if isinstance(output_manifest, Mapping):
            safe_output_manifest = {
                "status": str(output_manifest.get("status", "unknown"))[:20],
                "verification_mode": str(output_manifest.get("verification_mode", "metadata"))[:20],
                "hashes_verified": bool(output_manifest.get("hashes_verified", False)),
                "verified_files": int(output_manifest.get("verified_files") or 0),
                "mismatch_count": int(output_manifest.get("mismatch_count") or 0),
            }
            output_matches = output_manifest.get("outputs")
            if isinstance(output_matches, Mapping):
                safe_output_manifest["outputs"] = {
                    str(name)[:32]: {
                        "reported": str(item.get("reported", ""))[:160],
                        "manifest": [
                            str(value)[:160]
                            for value in (item.get("manifest") or [])[:3]
                        ],
                        "matched": bool(item.get("matched", False)),
                    }
                    for name, item in output_matches.items()
                    if isinstance(item, Mapping)
                }
            snapshot["analysis_ready"]["output_manifest"] = safe_output_manifest
        for name in ("dem", "land_use"):
            if name in snapshot["data_evidence"]:
                snapshot["data_evidence"][name]["analysis_ready"] = {
                    "status": analysis_ready.get("status", "unknown"),
                    "derived_version": snapshot["analysis_ready"]["derived_version"],
                    "target_grid": deepcopy(snapshot["analysis_ready"]["target_grid"]),
                    "grid_alignment": deepcopy(snapshot["analysis_ready"]["grid_alignment"]),
                }
                if "source_binding" in snapshot["analysis_ready"]:
                    snapshot["data_evidence"][name]["analysis_ready"]["source_binding"] = deepcopy(
                        snapshot["analysis_ready"]["source_binding"]
                    )
                if "output_manifest" in snapshot["analysis_ready"]:
                    snapshot["data_evidence"][name]["analysis_ready"]["output_manifest"] = deepcopy(
                        snapshot["analysis_ready"]["output_manifest"]
                    )
    else:
        snapshot["analysis_ready"] = {
            "status": "not_configured",
            "required": False,
        }
    return snapshot


def _capability_context_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "label": str(item.get("label", ""))[:80],
        "datasets": [str(value) for value in item.get("datasets", [])],
        "tools": [str(value) for value in item.get("tools", [])],
        "result_types": [str(value) for value in item.get("result_types", [])],
        "environment_supported": bool(item.get("environment_supported", False)),
        "dataset_gate": str(item.get("dataset_gate", "unknown")),
        "capability_status": str(item.get("capability_status", "unknown")),
        "available": bool(item.get("available", False)),
        "missing_datasets": [str(value) for value in item.get("missing_datasets", [])],
        "geometry": str(item.get("geometry", "unknown"))[:80],
    }


def _safe_tool_provider_summary(value: Mapping[str, Any] | str) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        try:
            tool_count = max(0, int(value.get("tool_count", 0)))
        except (TypeError, ValueError):
            tool_count = 0
        return {
            "id": str(value.get("id", "unknown"))[:64],
            "tool_count": tool_count,
        }
    return {"id": str(value)[:64]}


def _safe_tool_provider_health(value: Mapping[str, Any]) -> Dict[str, Any]:
    status = str(value.get("status", "unknown"))
    if status not in {"ready", "degraded", "unavailable", "unknown"}:
        status = "unknown"
    result = {
        "schema_version": str(value.get("schema_version") or "spatial-agent.tool-provider-health.v1")[:80],
        "provider_id": str(value.get("provider_id", "unknown"))[:64],
        "status": status,
        "tool_count": max(0, int(value.get("tool_count", 0) or 0)),
        "checks": [
            {
                "name": str(item.get("name", "check"))[:64],
                "status": str(item.get("status", "unknown"))[:20],
            }
            for item in (value.get("checks") or [])[:12]
            if isinstance(item, Mapping)
        ],
    }
    if value.get("reason_code"):
        result["reason_code"] = str(value["reason_code"])[:96]
    contract = value.get("definition_contract")
    if isinstance(contract, Mapping):
        result["definition_contract"] = {
            "schema_version": str(
                contract.get("schema_version") or "spatial-agent.tool-provider-contract.v1"
            )[:80],
            "provider_id": str(contract.get("provider_id", "unknown"))[:64],
            "status": str(contract.get("status", "unknown"))[:20],
            "tool_count": max(0, int(contract.get("tool_count", 0) or 0)),
            "validation": str(contract.get("validation", "unknown"))[:64],
        }
    return result


def _safe_tool_governance(value: Mapping[str, Any], *, max_tools: int) -> Dict[str, Any]:
    # Per-tool governance is already carried by the selected tool schema
    # summaries. Duplicating all entries here can evict the more important
    # capability/template sections from the bounded planner context.
    tools = []
    return {
        "schema_version": str(value.get("schema_version") or "spatial-agent.tool-governance.v1")[:80],
        "provider_id": str(value.get("provider_id", "unknown"))[:64],
        "tool_count": max(0, int(value.get("tool_count", 0) or 0)),
        "returned_tool_count": len(tools),
        "requires_approval_count": max(0, int(value.get("requires_approval_count", 0) or 0)),
        "side_effect_tool_count": max(0, int(value.get("side_effect_tool_count", 0) or 0)),
        "tools": tools,
    }


def _safe_tool_schema_summary(definition: Mapping[str, Any]) -> Dict[str, Any]:
    input_schema = definition.get("input_schema")
    output_schema = definition.get("output_schema")
    if not isinstance(input_schema, Mapping):
        input_schema = {}
    if not isinstance(output_schema, Mapping):
        output_schema = {}
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        properties = {}
    result = {
        "description": str(definition.get("description", ""))[:180],
        "side_effect": str(definition.get("side_effect", "unknown"))[:32],
        "requires_approval": bool(definition.get("requires_approval", False)),
        "required": [str(value) for value in input_schema.get("required", [])],
        "arguments": {
            str(name): _safe_schema_property(prop)
            for name, prop in properties.items()
            if isinstance(prop, Mapping)
        },
        "additional_properties": input_schema.get("additionalProperties", True),
        "output_required": [str(value) for value in output_schema.get("required", [])],
    }
    for key in ("permissions", "data_dependencies"):
        value = definition.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (list, tuple, set)):
            result[key] = [str(item)[:96] for item in list(value)[:8]]
    timeout = definition.get("timeout_seconds")
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0:
        result["timeout_seconds"] = float(timeout)
    return result


def _safe_schema_property(prop: Mapping[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"type": str(prop.get("type", "any"))}
    if "enum" in prop and isinstance(prop.get("enum"), list):
        summary["enum"] = [str(value) for value in prop.get("enum", [])[:16]]
    for key in ("minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"):
        if key in prop:
            summary[key] = prop.get(key)
    return summary


def _safe_analysis_ready_summary(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "not_configured", "required": False}
    target_grid = value.get("target_grid")
    if not isinstance(target_grid, Mapping):
        target_grid = {}
    grid_alignment = value.get("grid_alignment")
    if not isinstance(grid_alignment, Mapping):
        grid_alignment = {}
    return {
        "status": str(value.get("status", "unknown"))[:32],
        "required": bool(value.get("required", False)),
        "derived_version": str(value.get("derived_version", "unknown"))[:80],
        "crs": str(target_grid.get("crs", "unknown"))[:80],
        "grid_alignment_status": str(grid_alignment.get("status", "unknown"))[:32],
        "verification_mode": str(value.get("verification_mode", "metadata"))[:32],
    }


def _safe_source_binding_summary(binding: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "binding_version": binding.get("binding_version"),
        "fingerprint": str(binding.get("fingerprint", ""))[:80],
        "verification_mode": str(binding.get("verification_mode", "sha256"))[:20],
        "datasets": sorted(str(name)[:64] for name in (binding.get("datasets") or [])),
        "status": str(binding.get("status", "recorded"))[:20],
    }


def _capability_data_layer(
    datasets: Iterable[str],
    dataset_groups: Mapping[str, Iterable[str]] | None = None,
) -> str:
    names = set(datasets)
    groups_source = DATASET_GROUPS if dataset_groups is None else dataset_groups
    groups = {
        group
        for group, members in groups_source.items()
        if names and names.issubset(set(members))
    }
    if len(groups) == 1:
        return next(iter(groups))
    return "mixed" if names else "none"


def _capability_status(
    datasets: Iterable[str], dataset_statuses: Mapping[str, str] | None
) -> str:
    if dataset_statuses is None:
        return "unknown"
    statuses = [str(dataset_statuses.get(name, "unavailable")) for name in datasets]
    if not statuses:
        return "ready"
    if any(status == "unavailable" for status in statuses):
        return "unavailable"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    if all(status == "ready" for status in statuses):
        return "ready"
    return "unknown"
