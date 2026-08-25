"""Generic metrics/table/chart views for Economic results."""

from __future__ import annotations

from typing import Any, Dict, List

from agent.analysis.record_views import build_record_analysis_view


def build_views(
    result_type: str,
    *,
    steps: List[Any],
    geometry_evidence: Dict[str, Any],
    geojson_ref: Any = None,
    workspace: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del geometry_evidence, geojson_ref, workspace
    results = [step.get("result") for step in steps if isinstance(step, dict) and isinstance(step.get("result"), dict)]
    result = next((item for item in results if item.get("result_type") or item.get("indicators") or item.get("sources")), {})
    if result_type == "record_analysis_result":
        return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": build_record_analysis_view(result)}}
    if result_type == "economic_catalog_result":
        indicators = result.get("indicators") or []
        rows = [[item.get("id"), item.get("label"), ", ".join(item.get("units") or []), ", ".join(item.get("period_types") or [])] for item in indicators[:32]]
        return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": {"kind": "indicator_catalog", "title": "可用经济指标", "table": {"columns": ["指标 ID", "名称", "单位", "期间类型"], "rows": rows}}}}
    if result_type == "economic_evidence_result":
        sources = result.get("sources") or []
        rows = [[item.get("name"), item.get("published_at"), item.get("version"), item.get("locator"), item.get("url")] for item in sources[:24]]
        return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": {"kind": "source_evidence", "title": "数据来源证据", "table": {"columns": ["来源", "发布日期", "版本", "定位", "URL"], "rows": rows}, "note": "请注意统计期间与来源页面的口径说明。"}}}
    if result_type not in {"economic_metrics_result", "economic_timeseries_result", "economic_comparison_result"}:
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}
    rows = result.get("rows") or []
    metrics = result.get("metrics") or {}
    metric_cards = [
        {"label": "观测数", "value": metrics.get("record_count", len(rows))},
        {"label": "最小值", "value": metrics.get("minimum")},
        {"label": "最大值", "value": metrics.get("maximum")},
        {"label": "平均值", "value": metrics.get("mean")},
    ]
    table_rows = [[item.get("region"), item.get("geography_level"), item.get("period"), item.get("period_type"), item.get("value"), item.get("unit")] for item in rows[:80] if isinstance(item, dict)]
    panel = {
        "kind": "comparison_chart" if result_type in {"economic_timeseries_result", "economic_comparison_result"} else "indicator_metrics",
        "title": str(result.get("indicator") or "经济指标结果"),
        "metrics": metric_cards,
        "table": {"columns": ["区域", "区域层级", "期间", "期间类型", "数值", "单位"], "rows": table_rows},
        "availability": {"status": result.get("status", "unknown"), "code": result.get("code")},
        "note": "来源：" + str((result.get("provenance") or {}).get("source") or "未提供")[:160],
        "evidence": result.get("source_evidence") or [],
    }
    if panel["kind"] == "comparison_chart":
        panel["comparison_kind"] = "区域/期间比较"
        panel["series"] = [{"id": "economic-indicator", "points": [{"x": item.get("period"), "y": item.get("value"), "label": str(item.get("region") or "") + " · " + str(item.get("period") or "")} for item in rows[:80] if isinstance(item, dict)]}]
    return {"schema_version": "spatial-agent.views.v1", "panels": {"generic": panel}}
