"""Compatibility application for bounded comparison scenarios.

Comparison requests are optional convenience operations built on top of the
normal Agent run seam.  Keeping their orchestration here prevents the service
facade from owning scenario loops, monotonicity checks and comparison views.
The underlying runs still use the generic Runtime, Result and Artifact
contracts; this module does not add a special Runtime path.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from agent.scenario import (
    BuildabilityComparisonScenario,
    ConstrainedBuildabilityComparisonScenario,
)
from agent.application.service_format import (
    analysis_ready_summary as _analysis_ready_summary,
    normalize_spatial_context as _normalize_spatial_context,
)
from result_contract import (
    build_comparison_lineage,
    build_comparison_views,
)


class ComparisonApplication:
    """Run and compose the legacy bounded comparison scenarios."""

    def __init__(self, *, run_provider: Callable[..., Dict[str, Any]]) -> None:
        self._run_provider = run_provider

    def compare_buildability(
        self,
        admin_name: str,
        thresholds,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        scenario = BuildabilityComparisonScenario.for_thresholds(admin_name, thresholds)
        admin_name = scenario.admin_names[0]
        rows = []
        for value in scenario.thresholds:
            result = self._run_provider(
                request=f"分析{admin_name}建设适宜性，坡度不超过{value:g}度，使用 DEM 和土地利用数据",
                session_id=f"comparison-{admin_name}-{value:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
                export_artifact=True,
            )
            step = next(
                (
                    item
                    for item in result.get("steps", [])
                    if item.get("tool") == "get_zonal_buildability_analysis"
                ),
                {},
            )
            tool_result = step.get("result") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append(
                {
                    "run_id": result.get("run_id"),
                    "slope_limit_degrees": value,
                    "status": result.get("status"),
                    "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                    "valid_pixel_count": statistics.get("valid_pixel_count"),
                    "candidate_ratio": statistics.get("candidate_ratio"),
                    "error": statistics.get("error") or result.get("error"),
                    "planner_metrics": result.get("planner_metrics"),
                    "actual_tools": [
                        step.get("tool")
                        for step in result.get("steps", [])
                        if isinstance(step, dict)
                    ],
                    "failed_steps": [
                        {"tool": step.get("tool"), "error": step.get("error")}
                        for step in result.get("steps", [])
                        if isinstance(step, dict) and step.get("status") == "FAILED"
                    ],
                    "analysis_ready": _analysis_ready_summary(result),
                    "lineage": (result.get("result") or {}).get("lineage"),
                }
            )
        evidence = next(
            (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
            None,
        )
        return {
            "admin_name": admin_name,
            "thresholds": list(scenario.thresholds),
            "scenario": scenario.to_dict(),
            "spatial_context": normalized_context,
            "results": rows,
            "views": build_comparison_views(
                rows,
                "buildability_threshold_comparison",
                title="建设适宜性阈值对比",
                x_field="slope_limit_degrees",
                x_label="坡度阈值",
                y_field="candidate_pixel_count",
                y_label="候选像元",
                table_columns=[
                    ("坡度", "slope_limit_degrees"),
                    ("候选像元", "candidate_pixel_count"),
                    ("候选比例", "candidate_ratio"),
                    ("状态", "status"),
                ],
                note="坡度阈值越高，候选像元通常应保持不减；本图用于展示筛选敏感性。",
            ),
            "lineage": build_comparison_lineage(rows, "buildability_threshold_comparison"),
            **({"analysis_ready": evidence} if evidence else {}),
        }

    def compare_buildability_regions(
        self,
        admin_names,
        threshold: float = 20,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict[str, Any]:
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold must be a number") from exc
        scenario = BuildabilityComparisonScenario.for_regions(admin_names, threshold_value)
        names = list(scenario.admin_names)
        rows = []
        for admin_name in names:
            result = self.compare_buildability(
                admin_name=admin_name,
                thresholds=[threshold_value],
                planner=planner,
                backend=backend,
            )
            row = (result.get("results") or [{}])[0]
            rows.append({"admin_name": admin_name, **row})
        return {
            "admin_names": names,
            "slope_limit_degrees": threshold_value,
            "scenario": scenario.to_dict(),
            "results": rows,
            "views": build_comparison_views(
                rows,
                "buildability_region_comparison",
                title="多区域建设适宜性对比",
                x_field="admin_name",
                x_label="行政区",
                y_field="candidate_pixel_count",
                y_label="候选像元",
                table_columns=[
                    ("行政区", "admin_name"),
                    ("候选像元", "candidate_pixel_count"),
                    ("候选比例", "candidate_ratio"),
                    ("状态", "status"),
                ],
                note="同一坡度阈值下对比不同区域的候选规模。",
            ),
            "lineage": build_comparison_lineage(rows, "buildability_region_comparison"),
            **(
                {
                    "analysis_ready": next(
                        (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
                        None,
                    )
                }
                if any(row.get("analysis_ready") for row in rows)
                else {}
            ),
        }

    def compare_constrained_buildability(
        self,
        admin_name: str,
        road_distances,
        slope_limit_degrees: float = 15.0,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Compare constrained candidates while making monotonicity explicit."""
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        scenario = ConstrainedBuildabilityComparisonScenario.for_road_distances(
            admin_name, slope_limit_degrees, road_distances
        )
        admin_name = scenario.admin_name
        rows = []
        for distance in scenario.road_distances:
            result = self._run_provider(
                request=(
                    f"筛选{admin_name}坡度不超过{scenario.slope_limit_degrees:g}度、"
                    f"距道路{distance:g}米内、排除水体的建设候选区域"
                ),
                session_id=f"constrained-compare-{admin_name}-{distance:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
                export_artifact=True,
            )
            step = next(
                (
                    item
                    for item in result.get("steps", [])
                    if item.get("tool") == "get_zonal_constrained_buildability_analysis"
                ),
                {},
            )
            tool_result = step.get("result") or {}
            constraint_summary = tool_result.get("constraint_summary") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append(
                {
                    "run_id": result.get("run_id"),
                    "road_distance_m": distance,
                    "slope_limit_degrees": scenario.slope_limit_degrees,
                    "status": result.get("status"),
                    "candidate_features": constraint_summary.get("candidate_features"),
                    "eligible_features": constraint_summary.get("eligible_features"),
                    "water_excluded_features": constraint_summary.get("water_excluded_features"),
                    "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                    "candidate_ratio": statistics.get("candidate_ratio"),
                    "error": (
                        constraint_summary.get("error")
                        or statistics.get("error")
                        or result.get("error")
                    ),
                    "planner_metrics": result.get("planner_metrics"),
                    "actual_tools": [
                        step.get("tool")
                        for step in result.get("steps", [])
                        if isinstance(step, dict)
                    ],
                    "failed_steps": [
                        {"tool": step.get("tool"), "error": step.get("error")}
                        for step in result.get("steps", [])
                        if isinstance(step, dict) and step.get("status") == "FAILED"
                    ],
                    "analysis_ready": _analysis_ready_summary(result),
                    "lineage": (result.get("result") or {}).get("lineage"),
                }
            )
        eligible = [
            row.get("eligible_features")
            for row in rows
            if row.get("status") == "COMPLETED" and row.get("eligible_features") is not None
        ]
        monotonic = len(eligible) >= 2 and all(
            later >= earlier for earlier, later in zip(eligible, eligible[1:])
        )
        evidence = next(
            (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
            None,
        )
        return {
            "admin_name": admin_name,
            "slope_limit_degrees": scenario.slope_limit_degrees,
            "road_distances": list(scenario.road_distances),
            "scenario": scenario.to_dict(),
            "results": rows,
            "monotonic_eligible_features": monotonic,
            "views": build_comparison_views(
                rows,
                "constrained_buildability_road_distance_comparison",
                title="道路距离约束对比",
                x_field="road_distance_m",
                x_label="道路距离",
                y_field="eligible_features",
                y_label="满足道路约束",
                table_columns=[
                    ("道路距离", "road_distance_m"),
                    ("满足道路约束", "eligible_features"),
                    ("水体排除", "water_excluded_features"),
                    ("候选几何样本", "candidate_features"),
                    ("状态", "status"),
                ],
                note="道路距离放宽时，满足道路约束的候选数应单调不减；水体排除仅作演示约束。",
            ),
            "lineage": build_comparison_lineage(
                rows, "constrained_buildability_road_distance_comparison"
            ),
            **({"analysis_ready": evidence} if evidence else {}),
        }


__all__ = ["ComparisonApplication"]
