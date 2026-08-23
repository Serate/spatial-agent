"""Text-domain capability and tool contracts.

This intentionally contains no GIS dataset or spatial result vocabulary.
"""

TEXT_DATASET_TOOL_CAPABILITIES = {
    "documents": ["normalize_text", "summarize_text", "text_stats"],
}

TEXT_DATASET_GROUPS = {
    "core": ("documents",),
}

TEXT_CAPABILITIES = (
    {
        "id": "text_normalize",
        "label": "文本规范化",
        "datasets": ["documents"],
        "tools": ["normalize_text"],
        "result_types": ["text_normalize_result"],
        "environments": ["memory"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["规范化", "清洗文本", "整理文本", "normalize"],
            "tasks": ["normalize"],
            "datasets": ["documents"],
        },
    },
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
    {
        "id": "text_stats",
        "label": "文本统计",
        "datasets": ["documents"],
        "tools": ["text_stats"],
        "result_types": ["text_stats_result"],
        "environments": ["memory"],
        "geometry": "none",
        "request_hints": {
            "phrases": ["统计字数", "字符数", "词数", "行数", "文本统计", "text statistics"],
            "tasks": ["stats"],
            "datasets": ["documents"],
        },
    },
)

TEXT_TOOL_DEFINITIONS = {
    "normalize_text": {
        "name": "normalize_text",
        "description": "Normalize whitespace in supplied text without side effects.",
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
            "required": ["normalized_text", "char_count", "word_count"],
            "properties": {
                "normalized_text": {"type": "string"},
                "char_count": {"type": "integer"},
                "word_count": {"type": "integer"},
            },
        },
    },
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
    "text_stats": {
        "name": "text_stats",
        "description": "Return bounded character, word and line counts for text.",
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
            "required": ["char_count", "word_count", "line_count"],
            "properties": {
                "char_count": {"type": "integer"},
                "word_count": {"type": "integer"},
                "line_count": {"type": "integer"},
            },
        },
    },
}
