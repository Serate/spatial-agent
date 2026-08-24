"""GIS-owned policy supplied to the generic LLM Planner."""

from __future__ import annotations

from typing import Any


GIS_PLANNER_GUIDANCE: dict[str, Any] = {
    "domain_id": "gis",
    "domain_description": "地理空间数据分析与受控空间筛选。结果必须区分真实证据、演示筛选和不可用数据。",
    "tool_semantics": {
        "get_raster_statistics": "统计指定栅格数据集的像元值。DEM 或土地利用值统计使用 dataset 和 max_files。",
        "get_zonal_raster_statistics": "在已解析的行政区域内统计栅格；使用 dataset、admin_name 和 max_files。",
        "get_zonal_slope_statistics": "从真实 DEM 计算行政区域内坡度统计；使用 admin_name 和 max_files。",
        "get_zonal_land_use_distribution": "统计行政区域内土地利用类别组成；使用 admin_name 和 max_files。",
        "get_zonal_buildability_analysis": "根据显式坡度规则进行演示建设候选筛选，不代表法定建设适宜性或规划许可。",
        "get_zonal_constrained_buildability_analysis": "根据坡度、道路距离和水体排除条件进行有界演示筛选；候选几何是样本，不是法定结论。",
        "get_dataset_health_report": "报告数据可用性、CRS、覆盖和分析能力；数据 degraded 或 unavailable 时必须如实返回。",
        "get_dataset_schema": "读取数据集字段与几何元数据，为后续查询提供 schema 证据。",
        "range_query": "按属性条件查询数据集；没有属性过滤时使用 conditions=[]，不要捏造 OSM 的法定分类。",
        "spatial_join": "执行已声明的空间关系或距离约束，并保留来源数据集。",
        "spatial_operation": "对配置的数据集或前一步矢量结果执行有限的 clip/intersect 几何操作；输入可以是数据集 ID 或 result_ref，输出包含 CRS、来源和要素预算。",
        "get_zonal_vector_summary": "汇总行政区域内道路或水体等矢量；可选限制参数是 max_features，不是 max_files。",
        "get_raster_metadata": "读取 DEM 或土地利用栅格元数据，不声称已经统计像元。",
    },
    "result_types": {
        "raster_metadata_result": "栅格元数据及文件级读取证据。",
        "zonal_raster_statistics_result": "行政区域栅格统计及降级说明。",
        "terrain_land_use_analysis_result": "高程、坡度和土地利用的组合统计。",
        "buildability_result": "声明规则下的演示建设筛选，必须明确 screening only。",
        "constrained_buildability_result": "含道路/水体约束的演示建设筛选，必须明确几何边界和证据限制。",
        "spatial_overview_result": "行政区域空间总览，包含健康、边界、栅格和矢量证据。",
        "spatial_analysis_result": "按模板组合的综合空间分析结果。",
    },
    "planning_rules": [
        "Allowed datasets are roads, water, slope, admin_areas, dem, and land_use.",
        "For DEM or land use value statistics, use get_raster_statistics with dataset and max_files at most 3.",
        "For statistics inside a named administrative area, use get_zonal_raster_statistics with dataset, admin_name, and max_files at most 10.",
        "For slope inside an administrative area, derive it from the real DEM with get_zonal_slope_statistics.",
        "For land-use class composition inside an administrative area, use get_zonal_land_use_distribution.",
        "When elevation, slope, and land-use distribution are requested together, create ordered steps and bind admin_name from the resolved area.",
        "Do not claim construction suitability unless the user gives explicit slope, land-use, and weighting rules.",
        "For a demo construction request, use get_zonal_buildability_analysis after the admin lookup; use the explicit slope_limit_degrees or 15 by default. The plan output type must be \"buildability_result\" and the answer must describe screening only.",
        "For construction screening with road distance or water exclusion, get_dataset_health_report(dataset=all) must be an earlier preflight step. Then use get_zonal_constrained_buildability_analysis with admin_name, slope_limit_degrees, road_distance_m, exclude_water, and max_files. The plan output type must be \"constrained_buildability_result\".",
        "The constrained_buildability_result rule applies only when construction screening is primary. If trusted spatial_request.tasks contains admin_boundary, elevation, slope, land_use, roads, water, and buildability, use the composite spatial_analysis workflow instead and output type MUST be \"spatial_analysis_result\".",
        "For raster metadata, use get_raster_metadata with dataset dem or land_use and max_files at most 3.",
        "For a named administrative boundary, use get_dataset_schema and range_query on admin_areas with a name equality condition and limit 100.",
        "For road and slope proximity requests, use get_dataset_schema, range_query, and spatial_join as needed.",
        "For vector clipping or intersection, use spatial_operation with operation=clip or intersect; input_ref and mask_ref must be configured vector dataset IDs or completed vector result_ref values. Do not pass raw GeoJSON, filesystem paths, or invented datasets.",
        "For spatial_operation, preserve the source CRS and max_features budget in the result; if the backend has no vector geometry, report the recoverable data-unavailable state instead of fabricating geometry.",
        "For road or water inventory requests, use get_dataset_schema and range_query with conditions=[] when no attribute filter is requested.",
        "For data quality, availability, CRS, coverage, or dataset health requests, use get_dataset_health_report with all or the explicitly named dataset and max_files at most 10.",
        "For any regional raster, slope, land-use, or buildability analysis, put the health step before the dependent tool and preserve its dependency. An unavailable required dataset must be reported as unavailable.",
        "For buildability screening, the first step MUST be get_dataset_health_report(dataset=all, max_files=10), and the buildability tool MUST depend on it.",
        "For spatial overview, use get_dataset_health_report, admin_areas schema and range_query, zonal DEM/slope/land-use tools, and get_zonal_vector_summary for roads and water. Its optional limit is max_features (not max_files).",
        "Use the resolved admin name binding for every regional step. Do not claim real geometry unless a tool result or exported artifact provides it.",
        "A later step may bind a previous result with {\"$from\":\"filter-admin\",\"path\":\"first_name\"}; the source step must appear in depends_on.",
    ],
    "clarification_policy": [
        "Ask for the region, dataset, or explicit threshold when a spatial request cannot be safely mapped to registered capabilities.",
        "Do not invent measurements, legal classifications, geometry, or unavailable data.",
    ],
    "rejection_policy": [
        "Reject destructive, unauthorized, oversized, or code-execution requests.",
        "Reject a plan that bypasses registered tools or claims a legal planning decision from a demo screening.",
    ],
}
