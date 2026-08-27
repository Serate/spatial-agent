"""GIS-specific capability and dataset contract.

This module is the domain-owned catalog.  The generic Runtime consumes it
through ``DomainPack`` and does not need to know these dataset names.
"""

GIS_DATASET_TOOL_CAPABILITIES = {
    "admin_areas": ["get_dataset_schema", "range_query", "record_analysis", "spatial_operation"],
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
        "record_analysis",
        "get_zonal_vector_summary",
        "spatial_join",
        "spatial_operation",
    ],
    "water": [
        "get_dataset_schema",
        "range_query",
        "record_analysis",
        "get_zonal_vector_summary",
        "spatial_join",
        "spatial_operation",
    ],
    "earthquakes_wuhan": [
        "get_dataset_schema",
        "range_query",
        "record_analysis",
    ],
}

GIS_DATASET_GROUPS = {
    "core": ("admin_areas", "dem", "land_use"),
    "optional": ("roads", "water", "earthquakes_wuhan"),
}

GIS_ANALYSIS_OPERATIONS = {
    "spatial_overview": ("query", "aggregate"),
    "spatial_analysis": ("query", "aggregate", "filter", "spatial_operation"),
    "admin_boundary_query": ("query",),
    "raster_metadata": ("query",),
    "zonal_raster_statistics": ("aggregate",),
    "zonal_terrain_land_use": ("aggregate",),
    "buildability_screening": ("filter",),
    "constrained_buildability_screening": ("filter", "spatial_operation"),
    "vector_summary": ("query", "aggregate"),
    "dataset_health": ("query",),
    "raster_statistics": ("query", "aggregate"),
    "vector_query": ("query", "filter"),
    "earthquake_event_query": ("query", "filter"),
    "vector_relation": ("spatial_operation",),
    "vector_operation": ("spatial_operation",),
    "vector_measurement": ("spatial_operation",),
    "legacy_road_slope": ("query", "spatial_operation"),
    "admin_raster_composite": ("query", "aggregate"),
}

# Capability IDs are the public discovery identity. Workflow IDs are the
# executable Domain-owned identity. Keep aliases explicit so two capabilities
# sharing a tool/result pair cannot be matched by coincidence.
GIS_CAPABILITY_WORKFLOW_IDS = {
    "spatial_overview": ("spatial_overview",),
    "spatial_analysis": ("spatial_analysis",),
    "admin_boundary_query": ("admin_boundary_query",),
    "raster_metadata": ("raster_metadata",),
    "earthquake_event_query": ("earthquake_event_query",),
    "vector_operation": ("vector_operation",),
    "vector_measurement": ("vector_measurement",),
    "constrained_buildability_screening": ("constrained_buildability",),
}


def _request_requirements(*, entities=(), datasets=(), constraints=(), fields=()):
    """Declare request facts needed to clarify a GIS capability.

    Dataset dependencies remain on each capability's ``datasets`` field.  The
    optional ``request_requirements`` block only describes facts that must be
    present in the user's request, so the generic catalog can project them
    without knowing GIS capability IDs.
    """

    return {
        "entities": list(entities),
        "datasets": list(datasets),
        "constraints": list(constraints),
        "clarification_fields": [dict(field) for field in fields],
    }


_REGION_FIELD = {
    "id": "region",
    "label": "区域或行政区",
    "kind": "entity",
    "key": "admin_name",
}
_DATASET_FIELD = {
    "id": "dataset",
    "label": "数据集",
    "kind": "dataset",
    "mode": "any",
}
_THRESHOLD_FIELD = {
    "id": "filter_threshold",
    "label": "筛选阈值",
    "kind": "constraint",
    "mode": "any",
}


def _region_requirements():
    return _request_requirements(entities=("admin_name",), fields=(_REGION_FIELD,))


def _region_dataset_requirements(values):
    dataset_field = dict(_DATASET_FIELD)
    dataset_field["values"] = list(values)
    return _request_requirements(
        entities=("admin_name",),
        datasets=values,
        fields=(_REGION_FIELD, dataset_field),
    )


def _buildability_requirements():
    threshold = dict(_THRESHOLD_FIELD)
    threshold["keys"] = ["slope_max"]
    return _request_requirements(
        entities=("admin_name",),
        constraints=("slope_max",),
        fields=(_REGION_FIELD, threshold),
    )


def _constrained_buildability_requirements():
    threshold = dict(_THRESHOLD_FIELD)
    threshold["keys"] = ["slope_max", "road_distance_max", "exclude_water"]
    threshold["mode"] = "all"
    return _request_requirements(
        entities=("admin_name",),
        constraints=("slope_max", "road_distance_max", "exclude_water"),
        fields=(_REGION_FIELD, threshold),
    )


def _legacy_road_slope_requirements():
    threshold = dict(_THRESHOLD_FIELD)
    threshold["keys"] = ["slope_value"]
    return _request_requirements(
        constraints=("slope_value",),
        fields=(threshold,),
    )

def _request_hints(*, phrases=(), tasks=(), datasets=(), constraints=(), required_entities=()):
    """Declare bounded lexical/fact hints for catalog-driven discovery."""

    return {
        "phrases": list(phrases),
        "tasks": list(tasks),
        "datasets": list(datasets),
        "constraints": list(constraints),
        "required_entities": list(required_entities),
    }


def _attach_request_hints(definitions):
    hints = {
        "conversation": _request_hints(
            phrases=("聊天", "解释", "说明", "介绍"),
        ),
        "spatial_overview": _request_hints(
            phrases=("空间总览", "区域概览", "总体情况"),
            tasks=("admin_boundary", "elevation", "land_use", "roads", "water"),
            required_entities=("admin_name",),
        ),
        "spatial_analysis": _request_hints(
            phrases=("综合空间分析", "组合式空间分析", "综合分析"),
            tasks=("admin_boundary", "elevation", "land_use"),
            required_entities=("admin_name",),
        ),
        "admin_boundary_query": _request_hints(
            phrases=("行政区边界", "行政边界", "区划边界"),
            tasks=("admin_boundary",),
            datasets=("admin_areas",),
        ),
        "raster_metadata": _request_hints(
            phrases=("栅格元数据", "栅格信息", "栅格属性", "文件属性", "DEM信息", "DEM详情"),
            datasets=("dem", "land_use"),
        ),
        "zonal_raster_statistics": _request_hints(
            phrases=("区域栅格统计", "区域高程统计", "区域土地利用统计"),
            tasks=("elevation", "land_use"),
            datasets=("admin_areas", "dem", "land_use"),
            required_entities=("admin_name",),
        ),
        "zonal_terrain_land_use": _request_hints(
            phrases=("地形与土地利用", "高程与坡度", "地形土地利用"),
            tasks=("elevation", "slope", "land_use"),
            required_entities=("admin_name",),
        ),
        "buildability_screening": _request_hints(
            phrases=("建设适宜性", "建设候选", "适宜建设", "建设筛选"),
            tasks=("buildability",),
            constraints=("slope_max",),
            required_entities=("admin_name",),
        ),
        "constrained_buildability_screening": _request_hints(
            phrases=("道路与水体约束", "建设约束筛选", "距离道路", "排除水体"),
            tasks=("buildability", "roads", "water"),
            constraints=("slope_max", "road_distance_max", "exclude_water"),
            required_entities=("admin_name",),
        ),
        "vector_summary": _request_hints(
            phrases=("道路和水体汇总", "道路水体摘要", "道路与水体分布"),
            tasks=("roads", "water"),
            required_entities=("admin_name",),
        ),
        "dataset_health": _request_hints(
            phrases=("数据健康", "数据完整性", "数据就绪", "数据状态"),
        ),
        "raster_statistics": _request_hints(
            phrases=("栅格值统计", "栅格统计", "像元统计"),
            tasks=("elevation", "land_use"),
            datasets=("dem", "land_use"),
        ),
        "vector_query": _request_hints(
            phrases=("道路查询", "水体查询", "矢量查询", "要素查询"),
            tasks=("roads", "water"),
        ),
        "earthquake_event_query": _request_hints(
            phrases=("地震", "地震事件", "震级", "earthquake"),
            datasets=("earthquakes_wuhan",),
        ),
        "vector_relation": _request_hints(
            phrases=("空间关系", "空间连接", "相交查询", "附近要素"),
            tasks=("roads", "water"),
            constraints=("road_distance_max",),
        ),
        "vector_operation": _request_hints(
            phrases=("裁剪", "空间相交", "几何相交", "叠加分析", "按范围截取"),
            tasks=("roads", "water"),
        ),
        "vector_measurement": _request_hints(
            phrases=("缓冲", "缓冲区", "距离测算", "最近距离", "距离分析"),
            tasks=("roads", "water"),
        ),
        "legacy_road_slope": _request_hints(
            phrases=("道路邻近高坡度", "道路坡度关系"),
            tasks=("roads", "slope"),
            constraints=("slope_value",),
        ),
        "admin_raster_composite": _request_hints(
            phrases=("行政区栅格复合", "区域高程土地利用"),
            tasks=("admin_boundary", "elevation", "land_use"),
            required_entities=("admin_name",),
        ),
    }
    return tuple(
        {
            **item,
            "request_hints": hints.get(
                str(item.get("id")), _request_hints()
            ),
            "analysis_operations": list(
                GIS_ANALYSIS_OPERATIONS.get(str(item.get("id")), ())
            ),
            **(
                {"workflow_ids": list(GIS_CAPABILITY_WORKFLOW_IDS[str(item.get("id"))])}
                if str(item.get("id")) in GIS_CAPABILITY_WORKFLOW_IDS
                else {}
            ),
        }
        for item in definitions
    )


GIS_CAPABILITIES = _attach_request_hints((
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
        "demo_supported": True,
        "geometry": "optional",
        "request_requirements": _region_requirements(),
    },
    {
        "id": "spatial_analysis",
        "label": "组合式空间分析",
        "datasets": ["admin_areas", "dem", "land_use", "roads", "water"],
        "tools": [
            "get_dataset_health_report", "get_dataset_schema", "range_query",
            "get_zonal_raster_statistics", "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution", "get_zonal_vector_summary",
            "get_zonal_buildability_analysis", "get_zonal_constrained_buildability_analysis",
        ],
        "result_types": ["spatial_analysis_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "available_when_artifact_contains_features",
        "request_requirements": _region_requirements(),
    },
    {
        "id": "admin_boundary_query",
        "label": "行政区边界查询",
        "datasets": ["admin_areas"],
        "tools": ["get_dataset_schema", "range_query"],
        "result_types": ["admin_area_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "optional",
        "request_requirements": _request_requirements(
            entities=("admin_name",), fields=(_REGION_FIELD,)
        ),
    },
    {
        "id": "raster_metadata",
        "label": "栅格元数据查询",
        "datasets": ["dem", "land_use"],
        "tools": ["get_raster_metadata"],
        "result_types": ["raster_metadata_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_requirements": _request_requirements(
            datasets=("dem", "land_use"),
            fields=({**_DATASET_FIELD, "mode": "one"},),
        ),
    },
    {
        "id": "zonal_raster_statistics",
        "label": "区域栅格统计",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": ["get_dataset_health_report", "get_zonal_raster_statistics"],
        "result_types": ["zonal_raster_statistics_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "optional",
        "request_requirements": _region_dataset_requirements(("dem", "land_use")),
    },
    {
        "id": "zonal_terrain_land_use",
        "label": "区域地形与土地利用分析",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": [
            "get_dataset_health_report", "get_dataset_schema", "range_query",
            "get_zonal_raster_statistics", "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
        ],
        "result_types": ["terrain_land_use_analysis_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "optional",
        "request_requirements": _region_dataset_requirements(("dem", "land_use")),
    },
    {
        "id": "buildability_screening",
        "label": "建设候选演示筛选",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": ["get_dataset_health_report", "get_zonal_buildability_analysis"],
        "result_types": ["buildability_result", "buildability_comparison"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "available_when_artifact_contains_features",
        "request_requirements": _buildability_requirements(),
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
        "demo_supported": True,
        "geometry": "available_when_artifact_contains_features",
        "request_requirements": _constrained_buildability_requirements(),
    },
    {
        "id": "vector_summary",
        "label": "道路与水体区域摘要",
        "datasets": ["admin_areas", "roads", "water"],
        "tools": ["get_dataset_health_report", "get_zonal_vector_summary"],
        "result_types": ["zonal_vector_summary_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "optional",
        "request_requirements": _region_requirements(),
    },
    {
        "id": "dataset_health",
        "label": "数据健康检查",
        "datasets": [],
        "tools": ["get_dataset_health_report"],
        "result_types": ["dataset_health_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
    },
    {
        "id": "raster_statistics",
        "label": "栅格值统计",
        "datasets": ["dem", "land_use"],
        "tools": ["get_raster_statistics"],
        "result_types": ["raster_statistics_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
    },
    {
        "id": "vector_query",
        "label": "矢量要素查询",
        "datasets": ["roads", "water"],
        "tools": ["get_dataset_schema", "range_query", "record_analysis"],
        "result_types": ["vector_result", "record_analysis_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "optional",
    },
    {
        "id": "earthquake_event_query",
        "label": "地震事件矢量查询",
        "datasets": ["earthquakes_wuhan"],
        "tools": ["get_dataset_schema", "range_query", "record_analysis"],
        "result_types": ["vector_result", "record_analysis_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
        "request_requirements": _request_requirements(
            datasets=("earthquakes_wuhan",),
            fields=(_DATASET_FIELD,),
        ),
    },
    {
        "id": "vector_relation",
        "label": "矢量空间关系查询",
        "datasets": ["roads", "water"],
        "tools": ["get_dataset_schema", "spatial_join"],
        "result_types": ["spatial_relation_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "optional",
    },
    {
        "id": "vector_operation",
        "label": "通用矢量空间算子",
        "datasets": ["admin_areas", "roads", "water"],
        "tools": ["spatial_operation"],
        "result_types": ["spatial_operation_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "available_when_artifact_contains_features",
    },
    {
        "id": "vector_measurement",
        "label": "通用矢量距离算子",
        "datasets": ["admin_areas", "roads", "water"],
        "tools": ["spatial_operation"],
        "result_types": ["spatial_operation_result"],
        "environments": ["local", "production"],
        "demo_supported": True,
        "geometry": "available_when_artifact_contains_features",
    },
    {
        "id": "legacy_road_slope",
        "label": "道路邻近高坡度查询（M0 兼容）",
        "datasets": ["roads", "slope"],
        "tools": ["get_dataset_schema", "range_query", "spatial_join"],
        "result_types": ["spatial_result"],
        "environments": ["memory", "local", "production"],
        "geometry": "optional",
        "request_requirements": _legacy_road_slope_requirements(),
    },
    {
        "id": "admin_raster_composite",
        "label": "行政区栅格复合统计",
        "datasets": ["admin_areas", "dem", "land_use"],
        "tools": [
            "get_dataset_health_report", "get_dataset_schema", "range_query",
            "get_zonal_raster_statistics",
        ],
        "result_types": ["zonal_raster_statistics_result"],
        "environments": ["local", "production"],
        "geometry": "optional",
        "request_requirements": _region_requirements(),
    },
))
