"""Bounded LLM planner vocabulary for Economic Domain."""

ECONOMIC_PLANNER_GUIDANCE = {
    "domain_id": "economic",
    "principles": [
        "先通过 economic_list_indicators 发现可用指标，再选择已声明的指标 ID。",
        "年度、季度、半年和月度期间不可未经说明地混合比较。",
        "所有经济结论必须保留 economic_source_evidence 返回的来源信息。",
        "没有指标、区域或可用期间时，请返回结构化澄清或选择已声明的不可用状态。",
    ],
    "terms": ["地区生产总值", "固定资产投资", "社会消费品零售总额", "城镇居民人均可支配收入", "同比增速"],
}
