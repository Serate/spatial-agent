"""Domain-neutral views for bounded record-analysis results."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


_OPERATION_LABELS = {
    "filter": "筛选",
    "aggregate": "聚合",
    "timeseries": "时间序列",
    "compare": "分组比较",
}
_METRIC_LABELS = {
    "input_count": "输入记录",
    "scanned_count": "扫描记录",
    "filtered_count": "满足条件",
    "output_count": "输出行数",
    "group_count": "分组数",
    "minimum": "最小值",
    "maximum": "最大值",
    "mean": "平均值",
}


def build_record_analysis_view(
    result: Mapping[str, Any],
    *,
    title: str = "记录分析结果",
) -> dict[str, Any]:
    """Build a bounded table/chart panel without domain vocabulary."""

    rows = [dict(item) for item in (result.get("rows") or []) if isinstance(item, Mapping)][:80]
    metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
    operation = str(result.get("operation") or "").strip().lower()
    columns = _columns(rows)
    table_rows = [[_display_value(row.get(column)) for column in columns] for row in rows]
    metric_cards = [
        {"label": label, "value": metrics[key]}
        for key, label in _METRIC_LABELS.items()
        if key in metrics and metrics[key] is not None
    ][:8]
    panel: dict[str, Any] = {
        "kind": "comparison_chart" if operation in {"timeseries", "compare"} else "record_analysis",
        "title": title,
        "subtitle": "{} · {}".format(
            result.get("dataset") or "已登记数据集",
            _OPERATION_LABELS.get(operation, operation or "结构化分析"),
        )[:160],
        "metrics": metric_cards,
        "table": {"columns": columns, "rows": table_rows},
        "availability": {
            "status": result.get("status") or "unknown",
            "warnings": [str(item)[:200] for item in (result.get("warnings") or [])[:4]],
        },
        "note": "结果仅展示有界属性记录；几何、完整原始数据和来源证据通过对应 artifact/evidence 查看。",
    }
    if operation in {"timeseries", "compare"}:
        panel["comparison_kind"] = _OPERATION_LABELS.get(operation, operation)
        panel["series"] = [{"id": str(result.get("dataset") or "records"), "points": _chart_points(result, rows)}]
    return panel


def _columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            name = str(key)[:96]
            if name not in columns:
                columns.append(name)
            if len(columns) >= 8:
                return columns
    return columns or ["结果"]


def _chart_points(result: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    request = result.get("request") if isinstance(result.get("request"), Mapping) else {}
    time_field = str(request.get("time_field") or "").strip()
    group_fields = request.get("group_by") if isinstance(request.get("group_by"), list) else []
    x_field = time_field or (str(group_fields[0]) if group_fields else "")
    value_field = _value_field(rows, request)
    points = []
    for row in rows[:40]:
        value = row.get(value_field) if value_field else None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        x = row.get(x_field) if x_field else len(points) + 1
        label = str(row.get(str(group_fields[0])) or "") if group_fields else ""
        if x is not None:
            label = (label + " · " if label else "") + str(x)
        points.append({"x": _display_value(x), "y": value, "label": label[:160]})
    return points


def _value_field(rows: Sequence[Mapping[str, Any]], request: Mapping[str, Any]) -> str | None:
    aggregations = request.get("aggregations") if isinstance(request.get("aggregations"), list) else []
    for item in aggregations:
        if isinstance(item, Mapping) and item.get("alias"):
            alias = str(item["alias"])
            if any(alias in row for row in rows):
                return alias
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return str(key)
    return None


def _display_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (Mapping, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:240]
        except (TypeError, ValueError):
            return str(value)[:240]
    return str(value)[:240]


__all__ = ["build_record_analysis_view"]
