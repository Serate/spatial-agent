"""Economic Domain capability and ToolRegistry catalogue."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ECONOMIC_DATASET = "wuhan_hongshan_economic_indicators"
ECONOMIC_DATASET_TOOL_CAPABILITIES = {
    ECONOMIC_DATASET: [
        "economic_list_indicators",
        "economic_indicator_query",
        "economic_source_evidence",
    ],
}
ECONOMIC_DATASET_GROUPS = {"core": (ECONOMIC_DATASET,)}


_INDICATOR_FIELD = {
    "id": "indicator",
    "label": "经济指标",
    "kind": "constraint",
    "keys": ["indicator"],
}
_REGIONS_FIELD = {
    "id": "regions",
    "label": "分析区域",
    "kind": "entity",
    "key": "regions",
}


def _analysis_requirements() -> dict[str, Any]:
    """Declare public facts needed by metric analysis capabilities.

    The generic Runtime only projects this metadata.  Indicator semantics and
    parsing remain owned by the Economic Domain Pack.
    """

    return {
        "entities": ["regions"],
        "constraints": ["indicator"],
        "clarification_fields": [dict(_INDICATOR_FIELD), dict(_REGIONS_FIELD)],
    }

INDICATOR_ALIASES = {
    "gdp_total": ("地区生产总值", "gdp", "GDP", "经济总量"),
    "gdp_growth_yoy": ("GDP增速", "生产总值增速", "经济增速"),
    "fixed_asset_investment_growth_yoy": ("固定资产投资", "投资增速"),
    "retail_sales_total": ("社会消费品零售总额", "社会消费品零售", "消费总额"),
    "urban_disposable_income": ("城镇居民人均可支配收入", "居民收入", "可支配收入"),
}

_ECONOMIC_INDICATOR_HINT_PHRASES = tuple(
    dict.fromkeys(
        phrase
        for indicator, aliases in INDICATOR_ALIASES.items()
        for phrase in (indicator, *aliases)
    )
)

ECONOMIC_CAPABILITIES = (
    {
        "id": "economic_indicator_discovery",
        "label": "经济指标目录查询",
        "datasets": [ECONOMIC_DATASET],
        "tools": ["economic_list_indicators"],
        "result_types": ["economic_catalog_result"],
        "analysis_operations": ["query"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_hints": {"phrases": ["有哪些经济指标", "经济指标目录", "经济数据"], "tasks": ["discover"], "datasets": [ECONOMIC_DATASET]},
    },
    {
        "id": "economic_indicator_latest",
        "label": "经济指标查询",
        "datasets": [ECONOMIC_DATASET],
        "tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_metrics_result", "economic_evidence_result"],
        "analysis_operations": ["query", "evidence"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_requirements": _analysis_requirements(),
        "request_hints": {"phrases": ["经济指标是多少", "最新经济指标", "经济水平", *_ECONOMIC_INDICATOR_HINT_PHRASES], "tasks": ["latest"], "datasets": [ECONOMIC_DATASET]},
    },
    {
        "id": "economic_indicator_trend",
        "label": "经济指标趋势分析",
        "datasets": [ECONOMIC_DATASET],
        "tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_timeseries_result", "economic_evidence_result"],
        "analysis_operations": ["trend", "evidence"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_requirements": _analysis_requirements(),
        "request_hints": {"phrases": ["经济趋势", "经济变化", "经济增长", "历年经济", *_ECONOMIC_INDICATOR_HINT_PHRASES], "tasks": ["trend"], "datasets": [ECONOMIC_DATASET]},
    },
    {
        "id": "economic_indicator_compare",
        "label": "经济指标区域比较",
        "datasets": [ECONOMIC_DATASET],
        "tools": ["economic_indicator_query", "economic_source_evidence"],
        "result_types": ["economic_comparison_result", "economic_evidence_result"],
        "analysis_operations": ["compare", "evidence"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_requirements": _analysis_requirements(),
        "request_hints": {"phrases": ["经济比较", "经济对比", "区域经济差异", *_ECONOMIC_INDICATOR_HINT_PHRASES], "tasks": ["compare"], "datasets": [ECONOMIC_DATASET]},
    },
    {
        "id": "economic_source_evidence",
        "label": "经济数据来源证据",
        "datasets": [ECONOMIC_DATASET],
        "tools": ["economic_source_evidence"],
        "result_types": ["economic_evidence_result"],
        "analysis_operations": ["evidence"],
        "environments": ["memory", "local", "production"],
        "geometry": "none",
        "request_requirements": _analysis_requirements(),
        "request_hints": {"phrases": ["经济数据来源", "统计口径", "数据出处"], "tasks": ["evidence"], "datasets": [ECONOMIC_DATASET]},
    },
)

_REGION_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "maxItems": 16,
    "items": {"type": "string", "minLength": 1, "maxLength": 96},
}

_QUERY_SCHEMA = {
    "type": "object",
    "required": ["dataset", "operation", "indicator", "regions"],
    "properties": {
        "dataset": {"type": "string", "enum": [ECONOMIC_DATASET]},
        "operation": {"type": "string", "enum": ["latest", "trend", "compare"]},
        "indicator": {"type": "string", "minLength": 1, "maxLength": 96},
        "regions": _REGION_SCHEMA,
        "period_type": {"type": "string", "enum": ["annual", "quarter", "half_year", "month", "month_ytd"]},
        "period_start": {"type": "string", "maxLength": 32},
        "period_end": {"type": "string", "maxLength": 32},
    },
    "additionalProperties": False,
}

_EVIDENCE_SCHEMA = {
    "type": "object",
    "required": ["dataset", "indicator", "regions"],
    "properties": {
        "dataset": {"type": "string", "enum": [ECONOMIC_DATASET]},
        "indicator": {"type": "string", "minLength": 1, "maxLength": 96},
        "regions": _REGION_SCHEMA,
        "period_type": {"type": "string", "enum": ["annual", "quarter", "half_year", "month", "month_ytd"]},
        "period_start": {"type": "string", "maxLength": 32},
        "period_end": {"type": "string", "maxLength": 32},
    },
    "additionalProperties": False,
}

ECONOMIC_TOOL_DEFINITIONS = {
    "economic_list_indicators": {
        "name": "economic_list_indicators",
        "description": "列出真实经济数据源中的指标、区域、期间和来源摘要。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 10,
        "permissions": ["economic_data:read"],
        "data_dependencies": [ECONOMIC_DATASET],
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {
            "type": "object",
            "required": ["status", "indicators", "regions", "periods", "provenance"],
            "properties": {"status": {"type": "string"}, "indicators": {"type": "array"}, "regions": {"type": "array"}, "periods": {"type": "array"}, "provenance": {"type": "object"}},
        },
    },
    "economic_indicator_query": {
        "name": "economic_indicator_query",
        "description": "按指标、区域和期间执行最新值、趋势或区域比较查询，并返回逐条来源证据。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 15,
        "permissions": ["economic_data:read"],
        "data_dependencies": ["$dataset"],
        "input_schema": _QUERY_SCHEMA,
        "output_schema": {
            "type": "object",
            "required": ["status", "dataset", "data_profile", "provenance"],
            "properties": {"status": {"type": "string"}, "result_type": {"type": "string"}, "dataset": {"type": "string"}, "rows": {"type": "array"}, "metrics": {"type": "object"}, "data_profile": {"type": "object"}, "provenance": {"type": "object"}, "source_evidence": {"type": "array"}},
        },
    },
    "economic_source_evidence": {
        "name": "economic_source_evidence",
        "description": "返回经济指标请求对应的官方来源、发布日期、期间和字段/表格定位。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 10,
        "permissions": ["economic_data:read"],
        "data_dependencies": ["$dataset"],
        "input_schema": _EVIDENCE_SCHEMA,
        "output_schema": {
            "type": "object",
            "required": ["status", "dataset", "data_profile", "provenance"],
            "properties": {"status": {"type": "string"}, "dataset": {"type": "string"}, "sources": {"type": "array"}, "data_profile": {"type": "object"}, "provenance": {"type": "object"}},
        },
    },
}


def economic_tool_definitions() -> dict[str, dict[str, Any]]:
    return deepcopy(ECONOMIC_TOOL_DEFINITIONS)


def indicator_aliases() -> dict[str, tuple[str, ...]]:
    return deepcopy(INDICATOR_ALIASES)
