"""GIS-owned lexical intent and structured clarification policy."""

from __future__ import annotations

from typing import Any

from agent.capability_catalog import (
    capability_suggestions,
    project_clarification_requirements,
)

from .catalog import GIS_CAPABILITIES
from .request_model import parse_spatial_request

_HINTS = (
    ("spatial_overview", ("空间概况", "空间总览", "整体空间分析", "综合空间概览", "全面分析")),
    ("admin_boundary_query", ("行政区", "边界", "区域", "区划")),
    ("zonal_raster_statistics", ("高程", "DEM", "地形", "栅格", "像元")),
    ("zonal_terrain_land_use", ("坡度", "土地利用", "土地覆盖", "地类")),
    ("buildability_screening", ("建设适宜性", "适宜建设", "建设候选", "建设用地")),
    ("vector_summary", ("道路", "路网", "水体", "河流", "湖泊")),
    ("constrained_buildability_screening", ("距离道路", "避开水体", "道路附近")),
    ("vector_operation", ("裁剪", "空间相交", "几何相交", "叠加分析", "按范围截取")),
    ("vector_measurement", ("缓冲", "缓冲区", "距离测算", "最近距离", "距离分析")),
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


def classify_spatial_intent(request: str) -> dict[str, Any]:
    """Return bounded GIS hints without claiming that a capability ran."""

    text = str(request or "").strip()
    suggested_details = [
        item
        for item in capability_suggestions(GIS_CAPABILITIES)
        if item.get("id") in _HINT_CAPABILITY_IDS
    ]
    matched: list[str] = []
    matched_terms: list[str] = []
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


def clarification_details(request: str) -> dict[str, Any]:
    """Return UI/API-safe next actions for an unresolved GIS request."""

    intent = classify_spatial_intent(request)
    catalog_details = [
        item
        for item in intent.get("suggested_capability_details", [])
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ][:16]
    catalog_by_id = {str(item["id"]): item for item in catalog_details}
    if intent["matched_capabilities"]:
        facts = parse_spatial_request(request)
        projection = project_clarification_requirements(
            intent["matched_capabilities"],
            facts,
            capability_definitions=GIS_CAPABILITIES,
        )
        missing = list(projection["missing"])
        missing_details = list(projection["missing_fields"])
        if missing:
            next_actions = ["补充" + "、".join(missing), "或改问已注册的空间能力"]
        else:
            next_actions = ["确认目标能力并执行", "或改问已注册的空间能力"]
        state = "matched_capability_missing_parameters"
    else:
        missing = ["空间对象", "区域", "分析条件"]
        missing_details = [
            {"id": "object", "label": "空间对象", "kind": "entity"},
            {"id": "region", "label": "区域", "kind": "entity"},
            {"id": "conditions", "label": "分析条件", "kind": "constraint"},
        ]
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
        "missing_fields": missing_details[:8],
        "next_actions": next_actions[:8],
    }


__all__ = [
    "CLARIFICATION_SCHEMA_VERSION",
    "clarification_details",
    "clarification_message",
    "classify_spatial_intent",
]
