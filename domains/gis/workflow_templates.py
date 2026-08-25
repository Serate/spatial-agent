"""GIS-owned declarative workflow catalog.

The generic workflow module validates and composes templates but does not own
GIS tools or result types. This module is the GIS Domain adapter for that seam.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

KNOWN_TOOL_NAMES = [
    "get_dataset_health_report",
    "get_dataset_schema",
    "range_query",
    "record_analysis",
    "spatial_join",
    "spatial_operation",
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
    "spatial_operation_result",
    "record_analysis_result",
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
    "earthquake_event_query": {
        "id": "earthquake_event_query",
        "version": "1.0.0",
        "label": "地震事件查询",
        "goal_template": "query registered earthquake event vector data",
        "allowed_tools": ["get_dataset_schema", "range_query", "record_analysis"],
        "result_types": ["vector_result", "record_analysis_result"],
        "max_steps": 2,
        "required_constraints": [],
        "constraint_specs": [],
        "evidence_options": ["summary", "geometry", "trace"],
        "default_evidence": ["summary", "geometry", "trace"],
        "step_blueprint": [
            {
                "id": "schema-earthquakes",
                "tool": "get_dataset_schema",
                "args": {"dataset": "earthquakes_wuhan"},
                "depends_on": [],
            },
            {
                "id": "query-earthquakes",
                "tool": "range_query",
                "args": {
                    "dataset": "earthquakes_wuhan",
                    "conditions": [],
                    "limit": 10000,
                },
                "depends_on": ["schema-earthquakes"],
            },
        ],
        "output_template": {"type": "vector_result", "summary": True},
    },
    "vector_operation": {
        "id": "vector_operation",
        "version": "1.0.0",
        "label": "通用矢量空间算子",
        "goal_template": "apply a bounded vector geometry operation to two spatial sources",
        "allowed_tools": ["spatial_operation"],
        "result_types": ["spatial_operation_result"],
        "max_steps": 1,
        "required_constraints": ["operation", "input_ref", "mask_ref"],
        "constraint_specs": [
            {"name": "operation", "label": "空间操作", "type": "enum", "required": True, "choices": ["clip", "intersect"]},
            {"name": "input_ref", "label": "输入数据或结果引用", "type": "string", "required": True, "min_length": 1},
            {"name": "mask_ref", "label": "掩膜数据或结果引用", "type": "string", "required": True, "min_length": 1},
            {"name": "max_features", "label": "最大要素数", "type": "integer", "required": False, "min": 1, "max": 10000, "default": 10000},
        ],
        "evidence_options": ["summary", "geometry", "trace"],
        "default_evidence": ["summary", "geometry", "trace"],
        "step_blueprint": [
            {
                "id": "spatial-operation",
                "tool": "spatial_operation",
                "args": {
                    "operation": {"$constraint": "operation"},
                    "input_ref": {"$constraint": "input_ref"},
                    "mask_ref": {"$constraint": "mask_ref"},
                    "max_features": {"$constraint": "max_features"},
                },
                "depends_on": [],
            },
        ],
        "output_template": {"type": "spatial_operation_result", "summary": True},
    },
    "vector_measurement": {
        "id": "vector_measurement",
        "version": "1.0.0",
        "label": "通用矢量距离算子",
        "goal_template": "buffer or measure nearest distances between vector sources",
        "allowed_tools": ["spatial_operation"],
        "result_types": ["spatial_operation_result"],
        "max_steps": 1,
        "required_constraints": ["operation", "input_ref", "mask_ref", "distance_m"],
        "constraint_specs": [
            {"name": "operation", "label": "空间操作", "type": "enum", "required": True, "choices": ["buffer", "distance"]},
            {"name": "input_ref", "label": "输入数据或结果引用", "type": "string", "required": True, "min_length": 1},
            {"name": "mask_ref", "label": "参照数据或结果引用", "type": "string", "required": True, "min_length": 1},
            {"name": "distance_m", "label": "距离（米）", "type": "number", "required": True, "min": 0, "max": 100000},
            {"name": "max_features", "label": "最大要素数", "type": "integer", "required": False, "min": 1, "max": 10000, "default": 10000},
        ],
        "evidence_options": ["summary", "geometry", "trace"],
        "default_evidence": ["summary", "geometry", "trace"],
        "step_blueprint": [
            {
                "id": "spatial-measurement",
                "tool": "spatial_operation",
                "args": {
                    "operation": {"$constraint": "operation"},
                    "input_ref": {"$constraint": "input_ref"},
                    "mask_ref": {"$constraint": "mask_ref"},
                    "distance_m": {"$constraint": "distance_m"},
                    "max_features": {"$constraint": "max_features"},
                },
                "depends_on": [],
            },
        ],
        "output_template": {"type": "spatial_operation_result", "summary": True},
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


def workflow_template_catalog(
    catalog: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return an isolated copy of the GIS-owned catalog."""

    source = WORKFLOW_TEMPLATE_CATALOG if catalog is None else catalog
    if not isinstance(source, Mapping):
        raise TypeError("catalog must be an object")
    return deepcopy(dict(source))
