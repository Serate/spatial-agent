"""Domain-owned GIS actions exposed through the generic action contract."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import DomainActionSpec, DOMAIN_ACTION_SCHEMA_VERSION


GIS_ACTION_SPECS = (
    DomainActionSpec(
        "gis.buildability_threshold_comparison",
        "建设筛选阈值对比",
        "比较多个坡度阈值下的建设候选规模。",
        {
            "type": "object",
            "required": ["admin_name", "thresholds"],
            "properties": {
                "admin_name": {"type": "string", "title": "行政区", "minLength": 1, "default": "洪山区"},
                "thresholds": {"type": "array", "title": "坡度阈值（度）", "minItems": 1, "items": {"type": "number"}, "default": [15, 20, 25]},
                "planner": {"type": "string", "title": "规划器", "enum": ["rule", "openai"], "default": "rule"},
                "backend": {"type": "string", "title": "后端", "enum": ["memory", "local"], "default": "memory"},
                "spatial_context": {"type": "object", "title": "空间上下文（JSON）"},
            },
            "additionalProperties": False,
        },
        "buildability_comparison",
    ),
    DomainActionSpec(
        "gis.buildability_region_comparison",
        "多区域建设筛选对比",
        "在同一坡度阈值下比较多个行政区。",
        {
            "type": "object",
            "required": ["admin_names"],
            "properties": {
                "admin_names": {"type": "array", "title": "行政区列表", "minItems": 2, "items": {"type": "string"}, "default": ["洪山区", "江夏区"]},
                "threshold": {"type": "number", "title": "坡度阈值（度）", "minimum": 1, "maximum": 45, "default": 20},
                "planner": {"type": "string", "title": "规划器", "enum": ["rule", "openai"], "default": "rule"},
                "backend": {"type": "string", "title": "后端", "enum": ["memory", "local"], "default": "memory"},
            },
            "additionalProperties": False,
        },
        "buildability_comparison",
    ),
    DomainActionSpec(
        "gis.constrained_buildability_comparison",
        "道路约束敏感性对比",
        "比较道路距离约束下的建设候选结果，并保留水体排除证据。",
        {
            "type": "object",
            "required": ["admin_name", "road_distances"],
            "properties": {
                "admin_name": {"type": "string", "title": "行政区", "minLength": 1, "default": "洪山区"},
                "road_distances": {"type": "array", "title": "道路距离（米）", "minItems": 1, "items": {"type": "number"}, "default": [200, 500, 1000]},
                "slope_limit_degrees": {"type": "number", "title": "坡度阈值（度）", "minimum": 1, "maximum": 45, "default": 15},
                "planner": {"type": "string", "title": "规划器", "enum": ["rule", "openai"], "default": "rule"},
                "backend": {"type": "string", "title": "后端", "enum": ["memory", "local"], "default": "memory"},
                "spatial_context": {"type": "object", "title": "空间上下文（JSON）"},
            },
            "additionalProperties": False,
        },
        "constrained_buildability_result",
    ),
)


def execute_action(
    action_id: str,
    payload: Mapping[str, Any],
    *,
    service: Any = None,
) -> dict[str, Any]:
    """Delegate only declared GIS actions to the existing Service adapters."""
    if service is None:
        raise ValueError("GIS action execution requires a service context")
    if action_id == "gis.buildability_threshold_comparison":
        return service.compare_buildability(
            admin_name=payload.get("admin_name", ""),
            thresholds=payload.get("thresholds", []),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
            spatial_context=payload.get("spatial_context"),
        )
    if action_id == "gis.buildability_region_comparison":
        return service.compare_buildability_regions(
            admin_names=payload.get("admin_names", []),
            threshold=payload.get("threshold", 20),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
        )
    if action_id == "gis.constrained_buildability_comparison":
        return service.compare_constrained_buildability(
            admin_name=payload.get("admin_name", ""),
            road_distances=payload.get("road_distances", []),
            slope_limit_degrees=payload.get("slope_limit_degrees", 15.0),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
            spatial_context=payload.get("spatial_context"),
        )
    raise ValueError("unknown GIS action: " + str(action_id))


__all__ = ["DOMAIN_ACTION_SCHEMA_VERSION", "GIS_ACTION_SPECS", "execute_action"]
