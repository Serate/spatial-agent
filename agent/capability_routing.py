"""Capability routing for deterministic spatial planning.

This module selects a capability from bounded request facts. It deliberately
does not build TaskPlan objects; plan composition lives in rule_planning.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from .request_model import SpatialRequest


CAPABILITY_DISCOVERY_SCHEMA_VERSION = "spatial-agent.capability-discovery.v1"


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
    "composition": ("综合", "同时", "分别", "汇总", "全面", "整体", "并"),
    "overview": ("空间概况", "空间总览", "整体空间分析", "综合空间概览", "全面分析"),
    "relation": ("距离", "附近", "以内", "邻近", "周边"),
}

RASTER_TASKS = ("elevation", "slope", "land_use")
VECTOR_TASKS = ("roads", "water")


def contains_any(text: str, terms: Iterable[str]) -> bool:
    """Return whether any configured lexical signal appears in text."""
    return any(term in text for term in terms)


def signal_terms(signal: str) -> Tuple[str, ...]:
    """Return terms for a signal as an immutable tuple."""
    return tuple(SIGNAL_TERMS.get(signal, ()))


def request_signals(text: str, spatial: SpatialRequest) -> Tuple[str, ...]:
    """Derive coarse routing signals from text and structured facts."""
    signals = {
        name
        for name, terms in SIGNAL_TERMS.items()
        if contains_any(text, terms)
    }
    if "road_distance_max" in spatial.constraints:
        signals.add("relation")
    return tuple(sorted(signals))


@dataclass(frozen=True)
class CapabilityRoute:
    """Declarative route from request facts to a capability id."""

    capability_id: str
    priority: int
    require_admin: bool = False
    min_task_count: int = 0
    all_tasks: Tuple[str, ...] = ()
    any_tasks: Tuple[str, ...] = ()
    no_tasks: Tuple[str, ...] = ()
    any_task_groups: Tuple[Tuple[str, ...], ...] = ()
    all_constraints: Tuple[str, ...] = ()
    any_constraints: Tuple[str, ...] = ()
    all_signals: Tuple[str, ...] = ()
    any_signals: Tuple[str, ...] = ()
    no_signals: Tuple[str, ...] = ()

    def matches(self, text: str, spatial: SpatialRequest) -> bool:
        tasks = set(spatial.tasks)
        constraints = set(spatial.constraints)
        signals = set(request_signals(text, spatial))
        if self.require_admin and not spatial.admin_name:
            return False
        if len(tasks) < self.min_task_count:
            return False
        if not set(self.all_tasks).issubset(tasks):
            return False
        if self.any_tasks and not tasks.intersection(self.any_tasks):
            return False
        if tasks.intersection(self.no_tasks):
            return False
        if self.any_task_groups and not any(set(group).issubset(tasks) for group in self.any_task_groups):
            return False
        if not set(self.all_constraints).issubset(constraints):
            return False
        if self.any_constraints and not constraints.intersection(self.any_constraints):
            return False
        if not set(self.all_signals).issubset(signals):
            return False
        if self.any_signals and not signals.intersection(self.any_signals):
            return False
        if signals.intersection(self.no_signals):
            return False
        return True


@dataclass(frozen=True)
class CapabilityMatch:
    """A selected capability plus its routing evidence."""

    capability_id: str
    priority: int
    signals: Tuple[str, ...] = field(default_factory=tuple)
    tasks: Tuple[str, ...] = field(default_factory=tuple)
    constraints: Tuple[str, ...] = field(default_factory=tuple)

    def as_context_dict(self) -> Mapping[str, Any]:
        return {
            "capability_id": self.capability_id,
            "priority": self.priority,
            "signals": list(self.signals),
            "tasks": list(self.tasks),
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True)
class CapabilityDiscovery:
    """Planner-facing, JSON-safe capability discovery evidence."""

    signals: Tuple[str, ...]
    tasks: Tuple[str, ...]
    constraints: Tuple[str, ...]
    admin_name: Optional[str]
    candidates: Tuple[CapabilityMatch, ...] = field(default_factory=tuple)

    @property
    def selected(self) -> Optional[CapabilityMatch]:
        return self.candidates[0] if self.candidates else None

    def as_context_dict(self, *, max_candidates: int = 8) -> Mapping[str, Any]:
        selected = self.selected
        candidates = self.candidates[:max_candidates]
        return {
            "schema_version": CAPABILITY_DISCOVERY_SCHEMA_VERSION,
            "available": True,
            "signals": list(self.signals),
            "tasks": list(self.tasks),
            "constraints": list(self.constraints),
            "admin_name": self.admin_name,
            "selected_capability_id": selected.capability_id if selected else None,
            "candidate_ids": [item.capability_id for item in candidates],
            "candidate_count": len(self.candidates),
            "candidates": [
                {"capability_id": item.capability_id, "priority": item.priority}
                for item in candidates
            ],
        }


class CapabilityRouter:
    """Select capability ids without knowing how plans are built."""

    def __init__(self, routes: Sequence[CapabilityRoute] | None = None) -> None:
        self._routes = tuple(sorted(routes or DEFAULT_ROUTES, key=lambda item: item.priority))

    @property
    def route_ids(self) -> List[str]:
        return [route.capability_id for route in self._routes]

    def select(self, text: str, spatial: SpatialRequest) -> Tuple[CapabilityMatch, ...]:
        return self.discover(text, spatial).candidates

    def discover(self, text: str, spatial: SpatialRequest) -> CapabilityDiscovery:
        signals = request_signals(text, spatial)
        constraints = tuple(sorted(spatial.constraints))
        candidates = tuple(
            CapabilityMatch(route.capability_id, route.priority, signals, spatial.tasks, constraints)
            for route in self._routes
            if route.matches(text, spatial)
        )
        return CapabilityDiscovery(
            signals=signals,
            tasks=spatial.tasks,
            constraints=constraints,
            admin_name=spatial.admin_name,
            candidates=candidates,
        )


DEFAULT_ROUTES: Tuple[CapabilityRoute, ...] = (
    CapabilityRoute("dataset_health", 10, all_signals=("health",)),
    CapabilityRoute("spatial_analysis", 20, require_admin=True, min_task_count=3, all_signals=("composition",)),
    CapabilityRoute("constrained_buildability_screening", 30, all_tasks=("buildability",), any_tasks=VECTOR_TASKS),
    CapabilityRoute(
        "zonal_terrain_land_use",
        40,
        require_admin=True,
        any_task_groups=(("buildability",), RASTER_TASKS),
    ),
    CapabilityRoute(
        "admin_raster_composite",
        50,
        require_admin=True,
        any_tasks=RASTER_TASKS,
        all_signals=("admin_boundary", "composition", "raster_statistics"),
    ),
    CapabilityRoute("spatial_overview", 60, require_admin=True, all_signals=("overview",)),
    CapabilityRoute("legacy_road_slope", 65, all_tasks=("roads", "slope"), all_constraints=("slope_value",), any_signals=("relation",)),
    CapabilityRoute("vector_relation", 80, all_tasks=VECTOR_TASKS, any_signals=("relation",)),
    CapabilityRoute("vector_summary", 90, require_admin=True, any_tasks=VECTOR_TASKS, no_signals=("relation",)),
    CapabilityRoute("vector_query", 100, any_tasks=VECTOR_TASKS, no_tasks=("slope",), no_signals=("relation",)),
    CapabilityRoute("zonal_raster_statistics", 110, require_admin=True, any_tasks=RASTER_TASKS, all_signals=("raster_statistics",), no_signals=("raster_metadata",)),
    CapabilityRoute("raster_metadata", 120, any_tasks=RASTER_TASKS, all_signals=("raster_metadata",)),
    CapabilityRoute("raster_statistics", 130, any_tasks=RASTER_TASKS, all_signals=("raster_statistics",), no_signals=("raster_metadata",)),
    CapabilityRoute("admin_boundary_query", 140, all_signals=("admin_boundary",)),
)
