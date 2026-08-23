"""Text-owned request understanding and capability discovery guidance."""

TEXT_REQUEST_UNDERSTANDING_GUIDANCE = {
    "domain_id": "text",
    "fact_fields": ["text", "tasks", "datasets", "constraints", "evidence"],
    "task_hints": [
        {"id": "normalize", "label": "文本规范化", "phrases": ["规范化", "清洗文本", "整理文本"]},
        {"id": "summarize", "label": "文本摘要", "phrases": ["摘要", "概括", "总结"]},
        {"id": "stats", "label": "文本统计", "phrases": ["统计", "字数", "字符数", "词数", "行数"]},
    ],
    "constraint_hints": [],
    "evidence_hints": [
        {"id": "answer", "label": "文本答案", "phrases": ["回答", "说明"]},
    ],
    "clarification_policy": [
        "文本请求缺少可处理内容时，先请求补充文本。",
        "不把文本请求解释为空间分析。",
    ],
    "discovery_policy": [
        "只选择当前 Text Domain Pack 声明的能力和工具。",
    ],
}
