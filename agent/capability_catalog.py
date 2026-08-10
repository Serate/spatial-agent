"""The shared, safe capability contract for planners, APIs, and the Console."""

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping

from .workflow_templates import workflow_template_catalog


DATASET_TOOL_CAPABILITIES = {
    "admin_areas": ["get_dataset_schema", "range_query"],
    "dem": [
        "get_raster_metadata",
        "get_raster_statistics",
        "get_zonal_raster_statistics",
        "get_zonal_slope_statistics",
    ],
    "land_use": [
        "get_raster_metadata",
        "get_raster_statistics",
        "get_zonal_raster_statistics",
        "get_zonal_land_use_distribution",
    ],
    "roads": [
        "get_dataset_schema",
        "range_query",
        "get_zonal_vector_summary",
        "spatial_join",
    ],
    "water": [
        "get_dataset_schema",
        "range_query",
        "get_zonal_vector_summary",
        "spatial_join",
    ],
}

# The core layer supports the default spatial workflows. Roads and water are
# optional enrichments and must not make core capabilities unavailable.
DATASET_GROUPS = {
    "core": ("admin_areas", "dem", "land_use"),
    "optional": ("roads", "water"),
}


_CAPABILITIES = (
    {
        "id": "conversation",
        "label": "通用对话",
        "datasets": [],
        "tools": [],
        "result_types": ["direct_answer"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
    },
    {
        "id": "spatial_overview",
        "label": "区域空间总览",
        "datasets": ["admin_areas", "dem", "land_use", "roads", "water"],
        "tools": [
            "get_dataset_health_report", "get_dataset_schema", "range_query",
            "get_zonal_raster_statistics", "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution", "get_zonal_vector_summary",
        ],
        "result_types": ["spatial_overview_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
    },
    {
        "id": "admin_boundary_query",
        "label": "行政区边界查询",
        "datasets": ["admin_areas"],
        "tools": ["get_dataset_schema", "range_query"],
        "result_types": ["admin_area_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "optional",
    },
    {
        "id": "raster_metadata",
        "label": "栅格元数据查询",
        "datasets": ["dem", "land_use"],
        "tools": ["get_raster_metadata"],
        "result_types": ["raster_metadata_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
    },
    {
        "id": "zonal_raster_statistics",
        "label": "区域栅格统计",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": ["get_dataset_health_report", "get_zonal_raster_statistics"],
        "result_types": ["zonal_raster_statistics_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
    },
    {
        "id": "zonal_terrain_land_use",
        "label": "区域地形与土地利用分析",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": [
            "get_dataset_health_report",
            "get_dataset_schema",
            "range_query",
            "get_zonal_raster_statistics",
            "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
        ],
        "result_types": ["terrain_land_use_analysis_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
    },
    {
        "id": "buildability_screening",
        "label": "建设候选演示筛选",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": ["get_dataset_health_report", "get_zonal_buildability_analysis"],
        "result_types": ["buildability_result", "buildability_comparison"],
        "environments": ["local", "production"],
        "geometry": "available_when_artifact_contains_features",
    },
    {
        "id": "constrained_buildability_screening",
        "label": "道路与水体约束筛选",
        "datasets": ["admin_areas", "dem", "land_use", "roads", "water"],
        "tools": [
            "get_dataset_health_report",
            "get_zonal_constrained_buildability_analysis",
        ],
        "result_types": ["constrained_buildability_result"],
        "environments": ["local", "production"],
        "geometry": "available_when_artifact_contains_features",
    },
    {
        "id": "vector_summary",
        "label": "道路与水体区域摘要",
        "datasets": ["admin_areas", "roads", "water"],
        "tools": ["get_dataset_health_report", "get_zonal_vector_summary"],
        "result_types": ["zonal_vector_summary_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
    },
)


def capability_catalog(
    *,
    environment: str = "unknown",
    dataset_capabilities: Mapping[str, Iterable[str]] | None = None,
    dataset_statuses: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    """Return a JSON-safe snapshot; callers cannot mutate the source contract."""
    has_dataset_gate = dataset_capabilities is not None
    available = {
        name: sorted(set(values))
        for name, values in (dataset_capabilities or {}).items()
    }
    capabilities = []
    for item in _CAPABILITIES:
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
        entry["missing_datasets"] = missing
        entry["data_layer"] = _capability_data_layer(entry["datasets"])
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
        capabilities.append(entry)
    return {
        "version": "1.0",
        "environment": environment,
        "capabilities": capabilities,
        "dataset_tools": deepcopy(DATASET_TOOL_CAPABILITIES),
        "available_dataset_tools": available,
        "dataset_groups": {
            name: list(datasets) for name, datasets in DATASET_GROUPS.items()
        },
        "workflow_templates": workflow_template_catalog(),
    }


def capability_suggestions() -> list[Dict[str, str]]:
    """Return the stable, user-facing capability choices for clarification UI."""
    return [
        {"id": str(item["id"]), "label": str(item["label"])}
        for item in _CAPABILITIES
    ]


def runtime_capability_catalog(
    health_report: Mapping[str, Any],
    *,
    environment: str = "unknown",
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
    return snapshot


def _capability_data_layer(datasets: Iterable[str]) -> str:
    names = set(datasets)
    groups = {
        group
        for group, members in DATASET_GROUPS.items()
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
