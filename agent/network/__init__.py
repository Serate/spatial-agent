"""Network capabilities kept behind explicit, server-owned policy seams."""

from .web_search import (
    DOCUMENT_EVIDENCE_SCHEMA_VERSION,
    WebSearchAdapter,
    WebSearchConfig,
    web_search_tool_definition,
)

__all__ = [
    "DOCUMENT_EVIDENCE_SCHEMA_VERSION",
    "WebSearchAdapter",
    "WebSearchConfig",
    "web_search_tool_definition",
]
