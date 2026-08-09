"""The shared, safe capability contract for planners, APIs, and the Console."""

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping


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
        capabilities.append(entry)
    return {
        "version": "1.0",
        "environment": environment,
        "capabilities": capabilities,
        "dataset_tools": deepcopy(DATASET_TOOL_CAPABILITIES),
        "available_dataset_tools": available,
    }
