"""Economic request facts and interpretation guidance."""


ECONOMIC_REQUEST_UNDERSTANDING_GUIDANCE = {
    "domain_id": "economic",
    "fact_fields": ["text", "tasks", "datasets", "constraints", "evidence", "entities"],
    "task_hints": [
        {"id": "discover", "label": "发现经济指标", "phrases": ["有哪些经济指标", "经济指标目录", "经济数据"]},
        {"id": "trend", "label": "经济趋势分析", "phrases": ["趋势", "变化", "增长", "历年"]},
        {"id": "compare", "label": "区域经济比较", "phrases": ["比较", "对比", "差异"]},
        {"id": "evidence", "label": "查看来源证据", "phrases": ["来源", "出处", "统计口径"]},
        {"id": "latest", "label": "查询最新指标", "phrases": ["最新", "当前", "指标是多少"]},
    ],
    "constraint_hints": [
        {"id": "indicator", "label": "经济指标 ID", "phrases": ["指标", "GDP", "投资", "消费", "收入"]},
        {"id": "regions", "label": "统计区域", "phrases": ["市", "区", "县", "区域"]},
        {"id": "period_type", "label": "期间类型", "phrases": ["年度", "季度", "半年", "月度"]},
    ],
    "evidence_hints": [{"id": "provenance", "label": "来源证据", "phrases": ["来源", "出处", "统计口径"]}],
    "clarification_policy": [
        "缺少指标时先澄清或引导用户查看指标目录，不凭空决定‘经济发展’的指标集合。",
        "年度、半年和月度数据不直接混为同一时间序列。",
    ],
    "discovery_policy": ["只选择 Economic Domain Pack 声明的能力和工具。"],
}
