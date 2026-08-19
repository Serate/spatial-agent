"""GIS-owned data and evidence preflight policy.

The generic Runtime owns permissions and approval gates.  Dataset health,
raster alignment, and GIS-specific fallback messages belong to this adapter so
another Domain Pack can use the same execution seam without inheriting GIS
dataset names.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from agent.errors import ToolError


_PIXEL_ALIGNMENT_TOOLS = frozenset(
    {
        "get_zonal_buildability_analysis",
        "get_zonal_constrained_buildability_analysis",
    }
)


def _required_health_datasets(tool: str, arguments: Mapping[str, Any]) -> set[str]:
    if tool in {"get_raster_metadata", "get_raster_statistics", "get_zonal_raster_statistics"}:
        dataset = arguments.get("dataset")
        return {dataset} if dataset in {"dem", "land_use"} else set()
    if tool == "get_zonal_slope_statistics":
        return {"dem"}
    if tool == "get_zonal_land_use_distribution":
        return {"land_use"}
    if tool == "get_zonal_buildability_analysis":
        return {"dem", "land_use"}
    if tool == "get_zonal_constrained_buildability_analysis":
        required = {"dem", "land_use", "roads"}
        if arguments.get("exclude_water", True):
            required.add("water")
        return required
    return set()


def preflight_tool(
    tool: str,
    arguments: Mapping[str, Any],
    completed_results: Mapping[str, Mapping[str, Any]],
    *,
    required_datasets: Iterable[str] = (),
    require_dependency_evidence: bool = False,
) -> None:
    """Enforce GIS health/alignment evidence before a tool adapter runs."""
    required = {str(item) for item in required_datasets if str(item)}
    required.update(_required_health_datasets(tool, arguments))
    health = next(
        (value for value in completed_results.values() if value.get("capabilities") is not None),
        None,
    )
    if health is None:
        if (
            require_dependency_evidence
            and required
            and tool != "get_dataset_health_report"
        ):
            raise ToolError(
                "数据依赖门控阻止工具 {}：缺少数据健康证据；请先执行 get_dataset_health_report".format(tool),
                category="policy",
                code="dependency_evidence_required",
                retryable=False,
            )
        if tool in _PIXEL_ALIGNMENT_TOOLS:
            raise ToolError(
                "像元级对齐门控阻止工具 {}：缺少 DEM/土地利用网格对齐证据".format(tool)
            )
        return

    if tool in _PIXEL_ALIGNMENT_TOOLS:
        alignment = (
            (health.get("relationships") or {})
            .get("dem_land_use", {})
            .get("grid_alignment")
        )
        # In-memory demos intentionally have no raster geometry. Preserve
        # their explanatory placeholder, but never run real joint pixels
        # when an explicit health report says the grids are incompatible.
        if isinstance(alignment, dict) and alignment.get("status") not in {"aligned"}:
            status = alignment.get("status") or "unknown"
            reason = alignment.get("reason") or "未提供对齐原因"
            raise ToolError(
                "像元级对齐门控阻止工具 {}：DEM/土地利用网格状态为 {}；{}".format(
                    tool, status, reason
                )
            )

    reports = {item.get("dataset"): item for item in health.get("datasets", [])}
    for dataset in required:
        report = reports.get(dataset) or {}
        if report.get("status") != "unavailable":
            continue
        capabilities = report.get("usable_for") or []
        capability_text = ", ".join(capabilities) if capabilities else "无"
        raise ToolError(
            f"数据预检阻止工具 {tool}：数据集 {dataset} 不可用；"
            f"当前可用能力：{capability_text}。请切换到本地 GIS 后端或补充数据配置。",
            category="policy",
            code="data_unavailable",
            retryable=False,
        )


__all__ = ["preflight_tool"]
