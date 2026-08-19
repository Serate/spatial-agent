"""Small, deterministic spatial-intent hints used before capability dispatch."""

from typing import Any, Dict, List

from .capability_catalog import capability_suggestions


_HINTS = (
    ("spatial_overview", ("空间概况", "空间总览", "整体空间分析", "综合空间概览", "全面分析")),
    ("admin_boundary_query", ("行政区", "边界", "区域", "区划")),
    ("zonal_raster_statistics", ("高程", "DEM", "地形", "栅格", "像元")),
    ("zonal_terrain_land_use", ("坡度", "土地利用", "土地覆盖", "地类")),
    ("buildability_screening", ("建设适宜性", "适宜建设", "建设候选", "建设用地")),
    ("vector_summary", ("道路", "路网", "水体", "河流", "湖泊")),
    ("constrained_buildability_screening", ("距离道路", "避开水体", "道路附近")),
)
_HINT_CAPABILITY_IDS = {capability_id for capability_id, _ in _HINTS}

_SPATIAL_TERMS = tuple(
    sorted(
        {
            term
            for _, terms in _HINTS
            for term in terms
        }
        | {"空间", "地图", "坐标", "位置", "范围", "分布", "面积", "周边", "地理"},
        key=len,
        reverse=True,
    )
)

CLARIFICATION_SCHEMA_VERSION = "spatial-agent.clarification.v1"


def classify_spatial_intent(request: str) -> Dict[str, Any]:
    """Return bounded hints without claiming that a capability was executed."""
    text = str(request or "").strip()
    suggested_details = [
        item
        for item in capability_suggestions()
        if item.get("id") in _HINT_CAPABILITY_IDS
    ]
    matched: List[str] = []
    matched_terms: List[str] = []
    for capability_id, terms in _HINTS:
        hits = [term for term in terms if term in text]
        if hits:
            matched.append(capability_id)
            matched_terms.extend(hits)
    is_spatial = bool(matched or any(term in text for term in _SPATIAL_TERMS))
    return {
        "is_spatial": is_spatial,
        "matched_capabilities": matched,
        "matched_terms": sorted(set(matched_terms), key=len, reverse=True)[:8],
        "suggested_capabilities": [item["id"] for item in suggested_details],
        "suggested_capability_details": suggested_details,
    }


def clarification_message(request: str) -> str:
    intent = classify_spatial_intent(request)
    if not intent["is_spatial"]:
        return "请说明希望查询的空间对象、区域或分析条件。"
    if intent["matched_capabilities"]:
        capabilities = "、".join(intent["matched_capabilities"])
        return (
            "已识别为开放式空间问题，可能涉及能力："
            + capabilities
            + "。请补充行政区名称、数据集或阈值；当前未执行工具。"
        )
    return (
        "已识别为空间问题，但暂未匹配到已注册能力。请补充对象、区域、"
        "距离/阈值等条件，或改问行政区边界、DEM/坡度、土地利用、道路水体摘要。"
    )


def clarification_details(request: str) -> Dict[str, Any]:
    """Return UI/API-safe next actions for an unresolved spatial request."""
    intent = classify_spatial_intent(request)
    catalog_details = [
        item
        for item in intent.get("suggested_capability_details", [])
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ][:16]
    catalog_by_id = {str(item["id"]): item for item in catalog_details}
    if intent["matched_capabilities"]:
        missing = ["区域或行政区"]
        if any(item in intent["matched_capabilities"] for item in ("zonal_raster_statistics", "zonal_terrain_land_use")):
            missing.append("数据集")
        if any(item in intent["matched_capabilities"] for item in ("buildability_screening", "constrained_buildability_screening")):
            missing.append("筛选阈值")
        next_actions = ["补充" + "、".join(missing), "或改问已注册的空间能力"]
        state = "matched_capability_missing_parameters"
    else:
        missing = ["空间对象", "区域", "分析条件"]
        next_actions = ["补充" + "、".join(missing), "或从能力目录选择一个空间能力"]
        state = "unmatched_spatial_capability"
    return {
        "schema_version": CLARIFICATION_SCHEMA_VERSION,
        "state": state,
        "is_spatial": bool(intent["is_spatial"]),
        "matched_capabilities": list(intent["matched_capabilities"]),
        "suggested_capabilities": list(intent["suggested_capabilities"]),
        "matched_capability_details": [
            catalog_by_id[item]
            for item in intent["matched_capabilities"]
            if item in catalog_by_id
        ][:8],
        "suggested_capability_details": catalog_details,
        "missing": missing[:8],
        "next_actions": next_actions[:8],
    }
