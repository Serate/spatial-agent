"""Text-owned request understanding and capability discovery guidance."""

TEXT_REQUEST_UNDERSTANDING_GUIDANCE = {
    "domain_id": "text",
    "fact_fields": ["text", "tasks", "datasets", "constraints", "evidence"],
    "task_hints": [
        {"id": "summarize", "label": "文本摘要", "phrases": ["摘要", "概括", "总结"]},
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
