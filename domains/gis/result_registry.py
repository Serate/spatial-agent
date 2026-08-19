"""Default GIS result metadata used by the backwards-compatible pack."""

from agent.result_registry import ResultContractRegistry, ResultTypeSpec


def _build_gis_views(*args, **kwargs):
    """Lazy import keeps the generic result contract free of GIS bootstrap."""
    from result_contract import _view_model

    return _view_model(*args, **kwargs)


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
    "spatial_relation_result": "空间关系",
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
    "spatial_relation_result": ("vector",),
    "spatial_result": ("vector",),
}

_GEOMETRY_TYPES = {
    "spatial_analysis_result",
    "spatial_overview_result",
    "terrain_land_use_analysis_result",
    "admin_area_result",
    "zonal_raster_statistics_result",
    "raster_statistics_result",
}

GIS_RESULT_REGISTRY = ResultContractRegistry(
    {
        result_type: ResultTypeSpec(
            title=_TITLES[result_type],
            panels=tuple(_PANELS.get(result_type, ())),
            requires_geometry=result_type in _GEOMETRY_TYPES,
        )
        for result_type in _TITLES
    },
    fallback_title="空间分析结果",
    view_builder=_build_gis_views,
)
