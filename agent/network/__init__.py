"""Network capabilities kept behind explicit, server-owned policy seams."""

from .web_search import (
    DOCUMENT_EVIDENCE_SCHEMA_VERSION,
    WebSearchAdapter,
    WebSearchConfig,
    web_search_tool_definition,
)
from .web_policy import (
    DEFAULT_WEB_MODE,
    WEB_MODE_ALLOWLIST,
    WEB_MODE_OFF,
    WEB_MODE_PUBLIC,
    WEB_MODES,
    WebAccessPolicy,
    WebPolicyDecision,
    normalize_web_domains,
    normalize_web_mode,
)
from .web_fetch import (
    DOCUMENT_EVIDENCE_RESULT_TYPE,
    WEB_FETCH_SCHEMA_VERSION,
    WEB_FETCH_TOOL_NAME,
    WebFetchAdapter,
    WebFetchConfig,
    web_fetch_tool_definition,
)

__all__ = [
    "DOCUMENT_EVIDENCE_SCHEMA_VERSION",
    "WebSearchAdapter",
    "WebSearchConfig",
    "web_search_tool_definition",
    "DEFAULT_WEB_MODE",
    "WEB_MODE_ALLOWLIST",
    "WEB_MODE_OFF",
    "WEB_MODE_PUBLIC",
    "WEB_MODES",
    "WebAccessPolicy",
    "WebPolicyDecision",
    "normalize_web_domains",
    "normalize_web_mode",
    "WEB_FETCH_SCHEMA_VERSION",
    "WEB_FETCH_TOOL_NAME",
    "DOCUMENT_EVIDENCE_RESULT_TYPE",
    "WebFetchAdapter",
    "WebFetchConfig",
    "web_fetch_tool_definition",
]
