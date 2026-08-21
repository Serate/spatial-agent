"""Text-domain capability and tool contracts.

This intentionally contains no GIS dataset or spatial result vocabulary.
"""

TEXT_DATASET_TOOL_CAPABILITIES = {
    "documents": ["summarize_text"],
}

TEXT_DATASET_GROUPS = {
    "core": ("documents",),
}

TEXT_CAPABILITIES = (
    {
        "id": "text_summary",
        "label": "文本摘要",
        "datasets": ["documents"],
        "tools": ["summarize_text"],
        "result_types": ["text_summary_result"],
        "environments": ["memory"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["摘要", "总结", "概括", "summarize", "summary"],
            "tasks": ["summarize"],
            "datasets": ["documents"],
        },
    },
)

TEXT_TOOL_DEFINITIONS = {
    "summarize_text": {
        "name": "summarize_text",
        "description": "Return a bounded deterministic summary of supplied text.",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 10,
        "permissions": ["text_data:read"],
        "data_dependencies": [],
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["summary", "char_count", "word_count"],
            "properties": {
                "summary": {"type": "string"},
                "char_count": {"type": "integer"},
                "word_count": {"type": "integer"},
            },
        },
    },
}
