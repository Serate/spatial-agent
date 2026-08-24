"""LLM Planner guidance owned by the indicator Domain Pack."""

INDICATOR_PLANNER_GUIDANCE = {
    "domain_id": "indicators",
    "domain_description": "查询可追溯的区域指标，并按区域或期间输出结构化统计。",
    "tool_semantics": {
        "list_indicators": "发现数据源中可用指标、区域、期间和来源；不猜测不存在的指标。",
        "indicator_query": "按已发现或用户明确提供的指标 ID 和区域执行 latest、trend 或 compare；数据不足时保留结构化不可用状态。",
    },
    "result_types": {
        "indicator_catalog_result": "指标目录和来源摘要。",
        "indicator_metrics_result": "指标最新值及统计摘要。",
        "indicator_timeseries_result": "按期间排列的指标时间序列。",
        "indicator_comparison_result": "多个区域的指标比较。",
    },
    "planning_rules": [
        "先使用 list_indicators 发现指标、区域或期间不明确的数据，再使用 indicator_query。",
        "indicator_query 必须提供 dataset、indicator、regions 和 operation；不得发明指标 ID、区域或数值。",
        "趋势问题输出 indicator_timeseries_result，区域比较输出 indicator_comparison_result，单期查询输出 indicator_metrics_result。",
    ],
    "clarification_policy": [
        "缺少指标或区域时请求补充，不用 demo fixture 的名称替代用户目标。",
        "数据源没有匹配项时返回结构化数据缺失说明，不生成经济或规划结论。",
    ],
    "rejection_policy": ["拒绝越权访问、修改数据或要求伪造指标的请求。"],
}
