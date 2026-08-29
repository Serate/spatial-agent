"""Domain-owned catalog for generic regional indicator queries."""

from __future__ import annotations

from typing import Any


INDICATOR_DATASET_TOOL_CAPABILITIES = {
    "regional_indicators": ["list_indicators", "indicator_query"],
}

INDICATOR_DATASET_GROUPS = {"core": ("regional_indicators",)}

INDICATOR_CAPABILITIES = (
    {
        "id": "indicator_discovery",
        "label": "指标目录查询",
        "datasets": ["regional_indicators"],
        "tools": ["list_indicators"],
        "result_types": ["indicator_catalog_result"],
        "analysis_operations": ["query"],
        "workflow_ids": ["indicator_discovery"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["有哪些指标", "指标目录", "可用指标", "指标数据"],
            "tasks": ["discover"],
            "datasets": ["regional_indicators"],
        },
    },
    {
        "id": "indicator_latest",
        "label": "指标查询",
        "datasets": ["regional_indicators"],
        "tools": ["indicator_query"],
        "result_types": ["indicator_metrics_result"],
        "analysis_operations": ["query"],
        "workflow_ids": ["indicator_latest"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["指标是多少", "指标水平", "最新指标", "当前指标"],
            "tasks": ["latest"],
            "datasets": ["regional_indicators"],
        },
    },
    {
        "id": "indicator_trend",
        "label": "指标趋势分析",
        "datasets": ["regional_indicators"],
        "tools": ["indicator_query"],
        "result_types": ["indicator_timeseries_result"],
        "analysis_operations": ["trend"],
        "workflow_ids": ["indicator_trend"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["趋势", "变化", "增长", "历年", "时间序列"],
            "tasks": ["trend"],
            "datasets": ["regional_indicators"],
        },
    },
    {
        "id": "indicator_compare",
        "label": "区域指标比较",
        "datasets": ["regional_indicators"],
        "tools": ["indicator_query"],
        "result_types": ["indicator_comparison_result"],
        "analysis_operations": ["compare"],
        "workflow_ids": ["indicator_compare"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["比较", "对比", "哪个区域更高", "区域差异"],
            "tasks": ["compare"],
            "datasets": ["regional_indicators"],
        },
    },
)


_QUERY_SCHEMA = {
    "type": "object",
    "required": ["dataset", "operation", "indicator", "regions"],
    "properties": {
        "dataset": {"type": "string", "enum": ["regional_indicators"]},
        "operation": {"type": "string", "enum": ["latest", "trend", "compare"]},
        "indicator": {"type": "string", "minLength": 1, "maxLength": 96},
        "regions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": {"type": "string", "minLength": 1, "maxLength": 96},
        },
        "period_start": {"type": "string", "maxLength": 32},
        "period_end": {"type": "string", "maxLength": 32},
    },
    "additionalProperties": False,
}


INDICATOR_TOOL_DEFINITIONS = {
    "list_indicators": {
        "name": "list_indicators",
        "description": "列出当前指标数据源中的指标、区域、期间和来源摘要。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 10,
        "permissions": ["indicator_data:read"],
        "data_dependencies": ["regional_indicators"],
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["indicators", "regions", "periods", "provenance"],
            "properties": {
                "indicators": {"type": "array"},
                "regions": {"type": "array"},
                "periods": {"type": "array"},
                "provenance": {"type": "object"},
            },
        },
    },
    "indicator_query": {
        "name": "indicator_query",
        "description": "按指标、区域和期间执行最新值、趋势或区域比较查询。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 15,
        "permissions": ["indicator_data:read"],
        "data_dependencies": ["$dataset"],
        "input_schema": _QUERY_SCHEMA,
        "output_schema": {
            "type": "object",
            "required": ["operation", "indicator", "rows", "data_profile", "provenance"],
            "properties": {
                "operation": {"type": "string"},
                "indicator": {"type": "string"},
                "rows": {"type": "array"},
                "metrics": {"type": "object"},
                "data_profile": {"type": "object"},
                "provenance": {"type": "object"},
            },
        },
    },
}


def indicator_tool_definitions() -> dict[str, dict[str, Any]]:
    """Return a detached copy so Registry callers cannot mutate the catalog."""
    import copy

    return copy.deepcopy(INDICATOR_TOOL_DEFINITIONS)
