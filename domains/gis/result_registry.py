"""Default GIS result metadata used by the backwards-compatible pack."""

from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec


from .views import build_views


def _project_gis_provenance(result, summary):
    """Preserve legacy GIS identity fields outside the generic allowlist."""
    for key in ("admin_name", "crs", "first_name", "matched_files"):
        value = result.get(key)
        if isinstance(value, (str, int, float, bool, list)):
            summary[key] = value
    return summary


_TITLES = {
    "direct_answer": "通用回答",
    "spatial_overview_result": "区域空间总览",
    "admin_area_result": "行政区边界",
    "raster_metadata_result": "栅格元数据",
    "raster_statistics_result": "栅格统计",
    "zonal_raster_statistics_result": "区域栅格统计",
    "terrain_land_use_analysis_result": "综合空间分析",
    "spatial_analysis_result": "综合空间分析",
    "buildability_result": "建设适宜性筛选",
    "buildability_comparison": "建设适宜性对比",
    "constrained_buildability_result": "约束建设候选筛选",
    "dataset_health_result": "数据健康检查",
    "zonal_vector_summary_result": "区域矢量摘要",
    "zonal_vector_result": "区域矢量摘要",
    "vector_result": "矢量结果",
    "record_analysis_result": "记录分析结果",
    "spatial_relation_result": "空间关系",
    "spatial_operation_result": "空间算子结果",
    "spatial_result": "空间结果",
}

_PANELS = {
    "direct_answer": (),
    "spatial_overview_result": ("overview",),
    "spatial_analysis_result": ("raster", "composite"),
    "terrain_land_use_analysis_result": ("raster", "composite"),
    "admin_area_result": (),
    "raster_metadata_result": ("raster",),
    "raster_statistics_result": ("raster",),
    "zonal_raster_statistics_result": ("raster",),
    "dataset_health_result": ("health",),
    "buildability_result": ("raster", "buildability", "compare"),
    "buildability_comparison": ("buildability", "compare"),
    "constrained_buildability_result": ("buildability", "compare"),
    "zonal_vector_summary_result": ("vector",),
    "zonal_vector_result": ("vector",),
    "vector_result": ("vector",),
    "record_analysis_result": ("vector",),
    "spatial_relation_result": ("vector",),
    "spatial_operation_result": ("vector",),
    "spatial_result": ("vector",),
}

_DATA_KINDS = {
    "direct_answer": ("text",),
    "spatial_overview_result": ("composite", "vector", "raster", "metrics"),
    "spatial_analysis_result": ("composite", "vector", "raster", "metrics"),
    "terrain_land_use_analysis_result": ("composite", "raster", "metrics"),
    "admin_area_result": ("vector",),
    "raster_metadata_result": ("raster", "metrics"),
    "raster_statistics_result": ("raster", "metrics"),
    "zonal_raster_statistics_result": ("raster", "metrics"),
    "buildability_result": ("composite", "raster", "vector", "metrics"),
    "buildability_comparison": ("composite", "vector", "metrics"),
    "constrained_buildability_result": ("composite", "raster", "vector", "metrics"),
    "dataset_health_result": ("metrics",),
    "zonal_vector_summary_result": ("vector", "metrics"),
    "zonal_vector_result": ("vector", "metrics"),
    "vector_result": ("vector",),
    "spatial_relation_result": ("vector", "metrics"),
    "spatial_operation_result": ("vector", "metrics"),
    "spatial_result": ("vector",),
    "record_analysis_result": ("vector",),
}

_GEOMETRY_TYPES = {
    "spatial_analysis_result",
    "spatial_overview_result",
    "terrain_land_use_analysis_result",
    "admin_area_result",
    "zonal_raster_statistics_result",
    "raster_statistics_result",
    "spatial_operation_result",
}

_VIEW_TITLES = {
    "raster": "栅格统计",
    "overview": "空间总览",
    "health": "数据健康",
    "composite": "综合分析",
    "buildability": "建设筛选",
    "compare": "结果对比",
    "vector": "矢量摘要",
    "map": "空间预览",
    "generic": "结构化结果",
}
_VIEW_RENDERERS = {
    "raster": "metrics",
    "overview": "metrics",
    "health": "table",
    "composite": "metrics",
    "buildability": "metrics",
    "compare": "chart",
    "vector": "table",
    "map": "map",
    "generic": "generic",
}

_MAP_RENDER_TYPES = set(_TITLES) - {"direct_answer", "dataset_health_result", "record_analysis_result"}


def _view_specs_for(result_type: str) -> tuple[ViewSpec, ...]:
    specs = [
        ViewSpec(
            view_id=panel,
            renderer=_VIEW_RENDERERS.get(panel, "generic"),
            title=_VIEW_TITLES.get(panel),
        )
        for panel in _PANELS.get(result_type, ())
    ]
    if result_type in _MAP_RENDER_TYPES and not any(
        item.view_id == "map" for item in specs
    ):
        specs.append(ViewSpec(view_id="map", renderer="map", title=_VIEW_TITLES["map"]))
    return tuple(specs)

GIS_RESULT_REGISTRY = ResultContractRegistry(
    {
        result_type: ResultTypeSpec(
            title=_TITLES[result_type],
            panels=tuple(_PANELS.get(result_type, ())),
            requires_geometry=result_type in _GEOMETRY_TYPES,
            view_specs=_view_specs_for(result_type),
            data_kinds=_DATA_KINDS.get(result_type, ("unknown",)),
        )
        for result_type in _TITLES
    },
    fallback_title="空间分析结果",
    view_builder=build_views,
    provenance_projector=_project_gis_provenance,
)
