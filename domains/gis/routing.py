"""GIS-owned lexical signals and deterministic capability routes."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, Tuple

from agent.capability_discovery import (
    CapabilityDiscovery,
    CapabilityMatch,
    CapabilityRoute,
)


SIGNAL_TERMS: Mapping[str, Tuple[str, ...]] = {
    "admin_boundary": ("行政区", "边界", "县域", "行政范围", "区划"),
    "health": (
        "数据质量", "数据健康", "数据检查", "数据可用", "是否可用", "可用性",
        "数据状态", "数据完整性", "数据诊断",
    ),
    "raster_metadata": ("元数据", "栅格", "像元", "影像", "metadata"),
    "raster_statistics": (
        "统计", "分析", "均值", "平均", "最小", "最大", "高程概况", "分布",
        "情况", "如何", "怎么样", "概况",
    ),
    # Keep an explicit buildability signal separate from the broader
    # ``buildability`` task.  Phrases such as “有哪些地方适合建设” can still
    # use the generic terrain/land-use route, while an explicit suitability or
    # candidate-screening request can select the dedicated capability.
    "buildability": (
        "建设适宜性", "适宜建设", "建设候选", "建设筛选", "建设潜力", "建设用地",
        "buildability",
    ),
    "composition": ("综合", "同时", "分别", "汇总", "全面", "整体", "并"),
    "overview": ("空间概况", "空间总览", "整体空间分析", "综合空间概览", "全面分析"),
    "relation": ("距离", "附近", "以内", "邻近", "周边"),
}

RASTER_TASKS = ("elevation", "slope", "land_use")
VECTOR_TASKS = ("roads", "water")


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def signal_terms(signal: str) -> Tuple[str, ...]:
    return tuple(SIGNAL_TERMS.get(signal, ()))


def request_signals(text: str, spatial: Any) -> Tuple[str, ...]:
    signals = {
        name for name, terms in SIGNAL_TERMS.items() if contains_any(text, terms)
    }
    constraints = getattr(spatial, "constraints", {}) or {}
    if "road_distance_max" in constraints:
        signals.add("relation")
    return tuple(sorted(signals))


class GisCapabilityRouter:
    """Select GIS capabilities from GIS-owned RequestFacts."""

    def __init__(self, routes: Sequence[CapabilityRoute] | None = None) -> None:
        self._routes = tuple(sorted(routes or DEFAULT_ROUTES, key=lambda item: item.priority))

    @property
    def route_ids(self) -> list[str]:
        return [route.capability_id for route in self._routes]

    def select(self, text: str, spatial: Any) -> Tuple[CapabilityMatch, ...]:
        return self.discover(text, spatial).candidates

    def discover(self, text: str, spatial: Any) -> CapabilityDiscovery:
        signals = request_signals(text, spatial)
        tasks = tuple(getattr(spatial, "tasks", ()) or ())
        constraints = tuple(sorted((getattr(spatial, "constraints", {}) or {}).keys()))
        entities = {"admin_name": getattr(spatial, "admin_name", None)}
        candidates = tuple(
            CapabilityMatch(route.capability_id, route.priority, signals, tasks, constraints)
            for route in self._routes
            if route.matches(
                entities=entities,
                tasks=tasks,
                constraints=constraints,
                signals=signals,
            )
        )
        return CapabilityDiscovery(
            signals=signals,
            tasks=tasks,
            constraints=constraints,
            entities=entities,
            candidates=candidates,
        )


DEFAULT_ROUTES: Tuple[CapabilityRoute, ...] = (
    CapabilityRoute("dataset_health", 10, all_signals=("health",)),
    CapabilityRoute("spatial_analysis", 20, required_entity="admin_name", min_task_count=3, all_signals=("composition",)),
    CapabilityRoute("constrained_buildability_screening", 30, all_tasks=("buildability",), any_tasks=VECTOR_TASKS),
    CapabilityRoute(
        "buildability_screening", 35, required_entity="admin_name",
        all_tasks=("buildability",), all_signals=("buildability",),
    ),
    CapabilityRoute(
        "zonal_terrain_land_use", 40, required_entity="admin_name",
        any_task_groups=(("buildability",), RASTER_TASKS),
    ),
    CapabilityRoute(
        "admin_raster_composite", 50, required_entity="admin_name",
        any_tasks=RASTER_TASKS, all_signals=("admin_boundary", "composition", "raster_statistics"),
    ),
    CapabilityRoute("spatial_overview", 60, required_entity="admin_name", all_signals=("overview",)),
    CapabilityRoute("legacy_road_slope", 65, all_tasks=("roads", "slope"), all_constraints=("slope_value",), any_signals=("relation",)),
    CapabilityRoute("vector_relation", 80, all_tasks=VECTOR_TASKS, any_signals=("relation",)),
    CapabilityRoute("vector_summary", 90, required_entity="admin_name", any_tasks=VECTOR_TASKS, no_signals=("relation",)),
    CapabilityRoute("vector_query", 100, any_tasks=VECTOR_TASKS, no_tasks=("slope",), no_signals=("relation",)),
    CapabilityRoute("zonal_raster_statistics", 110, required_entity="admin_name", any_tasks=RASTER_TASKS, all_signals=("raster_statistics",), no_signals=("raster_metadata",)),
    CapabilityRoute("raster_metadata", 120, any_tasks=RASTER_TASKS, all_signals=("raster_metadata",)),
    CapabilityRoute("raster_statistics", 130, any_tasks=RASTER_TASKS, all_signals=("raster_statistics",), no_signals=("raster_metadata",)),
    CapabilityRoute("admin_boundary_query", 140, all_signals=("admin_boundary",)),
)
