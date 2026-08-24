"""Domain-owned indicator request facts and interpretation guidance."""

INDICATOR_REQUEST_UNDERSTANDING_GUIDANCE = {
    "domain_id": "indicators",
    "fact_fields": ["text", "tasks", "datasets", "constraints", "evidence", "entities"],
    "task_hints": [
        {"id": "discover", "label": "发现指标", "phrases": ["有哪些指标", "指标目录", "可用指标"]},
        {"id": "trend", "label": "趋势分析", "phrases": ["趋势", "变化", "增长", "历年"]},
        {"id": "compare", "label": "区域比较", "phrases": ["比较", "对比", "区域差异"]},
        {"id": "latest", "label": "最新指标", "phrases": ["最新", "当前", "指标是多少"]},
    ],
    "constraint_hints": [
        {"id": "indicator", "label": "指标 ID", "phrases": ["指标", "指数"]},
        {"id": "regions", "label": "区域", "phrases": ["市", "区", "县", "区域"]},
    ],
    "evidence_hints": [{"id": "provenance", "label": "来源证据", "phrases": ["来源", "数据出处"]}],
    "clarification_policy": ["缺少指标或区域时先澄清，不凭空推断。"],
    "discovery_policy": ["只选择当前 Indicators Domain Pack 声明的能力和工具。"],
}
