"""Bounded public-web search adapter.

The adapter owns network effects and never accepts a model-supplied URL,
method, headers, or script.  It returns small source records so the generic
Runtime can treat search like any other registered tool.
"""

from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import (
    parse_qs,
    parse_qsl,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..errors import ToolError
from .web_policy import (
    DEFAULT_WEB_MODE,
    WEB_MODE_ALLOWLIST,
    WebAccessPolicy,
    domain_allowed,
    normalize_web_domains,
    normalize_web_mode,
)


DOCUMENT_EVIDENCE_SCHEMA_VERSION = "spatial-agent.document-evidence.v1"
WEB_SEARCH_TOOL_NAME = "web_search"
_MAX_QUERY = 512
_MAX_DOMAIN = 255
_MAX_TITLE = 240
_MAX_SNIPPET = 600
_MAX_URL = 2048
_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class WebSearchConfig:
    """Server-owned search settings after bounded environment parsing."""

    provider_url: str = ""
    allowed_domains: tuple[str, ...] = ()
    timeout_seconds: float = 8.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_sources: int = 8
    user_agent: str = "spatial-agent-web-search/1.0"
    mode: str = DEFAULT_WEB_MODE

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "WebSearchConfig":
        values = settings if isinstance(settings, Mapping) else {}
        return cls(
            provider_url=str(values.get("web_search_provider_url") or "").strip()[:_MAX_URL],
            allowed_domains=normalize_web_domains(values.get("web_allowed_domains")),
            timeout_seconds=_bounded_float(values.get("web_search_timeout_seconds"), 8.0, 1.0, 30.0),
            max_response_bytes=_bounded_int(
                values.get("web_search_max_response_bytes"),
                2 * 1024 * 1024,
                1024,
                20 * 1024 * 1024,
            ),
            max_sources=_bounded_int(values.get("web_search_max_sources"), 8, 1, 8),
            mode=normalize_web_mode(values.get("web_mode")),
        )


class WebSearchAdapter:
    """Perform one allowlisted GET and project bounded search sources."""

    def __init__(
        self,
        config: WebSearchConfig | None = None,
        *,
        opener: Any = None,
        resolver: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config or WebSearchConfig()
        if self._config.mode not in {"off", "allowlist", "public"}:
            self._config = WebSearchConfig(
                provider_url=self._config.provider_url,
                allowed_domains=self._config.allowed_domains,
                timeout_seconds=self._config.timeout_seconds,
                max_response_bytes=self._config.max_response_bytes,
                max_sources=self._config.max_sources,
                user_agent=self._config.user_agent,
                mode=DEFAULT_WEB_MODE,
            )
        self._allowed_domains = normalize_web_domains(self._config.allowed_domains)
        self._policy = WebAccessPolicy(
            self._config.mode, self._allowed_domains, resolver=resolver
        )
        self._opener = opener

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> "WebSearchAdapter":
        return cls(WebSearchConfig.from_settings(settings))

    @property
    def config(self) -> WebSearchConfig:
        return self._config

    def invoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """ToolRegistry handler for the public ``web_search`` contract."""

        return self.search(
            arguments.get("query"),
            domains=arguments.get("domains"),
            max_results=arguments.get("max_results"),
        )

    def search(
        self,
        query: Any,
        *,
        domains: Iterable[Any] | None = None,
        max_results: Any = None,
    ) -> dict[str, Any]:
        query_text = _required_query(query)
        requested_domains = normalize_web_domains(domains)
        limit = _bounded_int(max_results, self._config.max_sources, 1, 8)
        effective_domains = (
            requested_domains[:8]
            if self._config.mode != WEB_MODE_ALLOWLIST
            else _effective_domains(self._allowed_domains, requested_domains)
        )
        base = _base_result(query_text, effective_domains)

        if not effective_domains and self._config.mode == WEB_MODE_ALLOWLIST:
            return _unavailable(base, "search_allowlist_empty")
        provider_decision = self._policy.check_provider(self._config.provider_url)
        if not provider_decision.allowed:
            reason = (
                "search_provider_url_unconfigured"
                if not self._config.provider_url
                else provider_decision.reason_code
            )
            return _unavailable(base, reason)

        request_url = _build_request_url(
            self._config.provider_url,
            query_text,
            requested_domains=effective_domains,
            max_results=limit,
        )
        try:
            response = self._open(request_url)
            try:
                final_url = str(response.geturl() or request_url)
                redirect_decision = self._policy.check_url(final_url)
                if not redirect_decision.allowed:
                    return _unavailable(
                        base,
                        _search_policy_reason(redirect_decision.reason_code),
                    )
                content_length = _header(response, "Content-Length")
                if content_length is not None and content_length > self._config.max_response_bytes:
                    return _unavailable(base, "search_response_too_large")
                body = _read_bounded(response, self._config.max_response_bytes)
                content_type = _header_text(response, "Content-Type")
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except _WebSearchPolicyError as exc:
            return _unavailable(base, exc.reason_code)
        except TimeoutError as exc:
            del exc
            return _unavailable(base, "search_timeout")
        except (HTTPError, URLError, OSError):
            return _unavailable(base, "search_network_error")
        except Exception:
            return _unavailable(base, "search_network_error")

        items = _parse_items(body, content_type, final_url)
        sources = _project_sources(
            items,
            self._allowed_domains,
            limit,
            retrieved_at=_utc_timestamp(),
            policy=self._policy if self._config.mode != WEB_MODE_ALLOWLIST else None,
        )
        if sources:
            return {
                **base,
                "status": "ok",
                "sources": sources,
                "source_count": len(sources),
                "reason_code": "search_completed",
            }
        if items:
            return {
                **base,
                "status": "degraded",
                "sources": [],
                "source_count": 0,
                "reason_code": "search_no_allowed_sources",
            }
        if _response_is_invalid(body, content_type):
            return _unavailable(base, "search_response_invalid")
        return {
            **base,
            "status": "ok",
            "sources": [],
            "source_count": 0,
            "reason_code": "search_no_results",
        }

    def _open(self, url: str) -> Any:
        request = Request(
            url,
            headers={"Accept": "application/json, text/html;q=0.9", "User-Agent": self._config.user_agent[:120]},
            method="GET",
        )
        opener_target = self._opener or self._build_opener()
        opener = getattr(opener_target, "open", None)
        if not callable(opener):
            raise _WebSearchPolicyError("search_opener_unavailable")
        return opener(request, timeout=self._config.timeout_seconds)

    def _build_opener(self) -> Any:
        allowed = self._allowed_domains
        redirect_count = 0

        class AllowlistedRedirectHandler(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                nonlocal redirect_count
                if redirect_count >= _MAX_REDIRECTS:
                    raise _WebSearchPolicyError("search_redirect_limit_exceeded")
                redirect_count += 1
                target = urljoin(req.full_url, newurl)
                decision = self._policy.check_url(target)
                if not decision.allowed:
                    raise _WebSearchPolicyError(
                        _search_policy_reason(decision.reason_code)
                    )
                return super().redirect_request(req, fp, code, msg, headers, target)

        return build_opener(AllowlistedRedirectHandler())


class _WebSearchPolicyError(Exception):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = str(reason_code)[:96]
        super().__init__(self.reason_code)


class _SearchHTMLParser(HTMLParser):
    """Parse common search-result markup without preserving page HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._anchor: dict[str, Any] | None = None
        self._snippet: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {str(key).lower(): value or "" for key, value in attrs}
        classes = set(str(attributes.get("class") or "").split())
        if tag.lower() == "a" and (
            "result__a" in classes
            or "result-link" in classes
            or "search-result" in classes
        ):
            self._anchor = {"url": str(attributes.get("href") or ""), "title": []}
        if classes.intersection({"result__snippet", "result-snippet", "search-snippet"}):
            self._snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchor is not None:
            title = " ".join(str(item) for item in self._anchor["title"])
            self.items.append({"url": self._anchor["url"], "title": title})
            self._anchor = None
        if self._snippet is not None and tag.lower() in {"div", "p", "span"}:
            if self.items:
                self.items[-1]["snippet"] = " ".join(self._snippet)
            self._snippet = None

    def handle_data(self, data: str) -> None:
        text = " ".join(str(data).split())
        if not text:
            return
        if self._anchor is not None:
            self._anchor["title"].append(text)
        if self._snippet is not None:
            self._snippet.append(text)


def web_search_tool_definition() -> dict[str, Any]:
    """Return the Registry-owned definition for ``web_search``."""

    return {
        "name": WEB_SEARCH_TOOL_NAME,
        "description": "Search allowlisted public web sources and return bounded document evidence.",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY},
                "domains": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {"type": "string", "maxLength": _MAX_DOMAIN},
                },
                "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": [
                "schema_version",
                "status",
                "result_type",
                "query",
                "sources",
                "source_count",
                "allowed_domains",
                "reason_code",
            ],
            "properties": {"result_type": {"type": "string", "const": "document_evidence"}},
            "additionalProperties": True,
        },
    }


def _required_query(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolError(
            "web search query must be a non-empty string",
            category="validation",
            code="web_search_query_invalid",
            retryable=False,
        )
    if len(value.strip()) > _MAX_QUERY:
        raise ToolError(
            "web search query exceeds the maximum length",
            category="validation",
            code="web_search_query_invalid",
            retryable=False,
        )
    return value.strip()


def _normalize_domains(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    result: list[str] = []
    for item in value:
        text = str(item or "").strip().lower().rstrip(".")
        if not text or len(text) > _MAX_DOMAIN or "/" in text or ":" in text or " " in text:
            continue
        try:
            text = text.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        if _is_ip_literal(text) or text == "localhost" or "." not in text:
            continue
        if text not in result:
            result.append(text)
    return tuple(result[:32])


def _effective_domains(server: tuple[str, ...], requested: tuple[str, ...]) -> tuple[str, ...]:
    if not requested:
        return server[:8]
    return tuple(
        item
        for item in requested
        if any(_domain_allowed(item, allowed) for allowed in server)
    )[:8]


def _domain_allowed(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith("." + allowed)


def _validated_url_host(url: str, allowed: tuple[str, ...], reason_code: str) -> str | None:
    try:
        parsed = urlsplit(str(url or ""))
        host = (parsed.hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        return None
    if _is_ip_literal(host) or host == "localhost" or not any(domain_allowed(host, item) for item in allowed):
        return None
    return host


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _build_request_url(
    provider_url: str,
    query: str,
    *,
    requested_domains: tuple[str, ...],
    max_results: int,
) -> str:
    parsed = urlsplit(provider_url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query_items.extend(
        [
            ("q", query),
            ("max_results", str(max_results)),
            ("domains", ",".join(requested_domains)),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_items), ""))


def _base_result(query: str, domains: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": DOCUMENT_EVIDENCE_SCHEMA_VERSION,
        "result_type": "document_evidence",
        "status": "unavailable",
        "query": query[:_MAX_QUERY],
        "sources": [],
        "source_count": 0,
        "allowed_domains": list(domains[:8]),
        "reason_code": "search_unavailable",
    }


def _unavailable(base: Mapping[str, Any], reason_code: str) -> dict[str, Any]:
    return {**dict(base), "status": "unavailable", "reason_code": str(reason_code)[:96]}


def _header(response: Any, name: str) -> int | None:
    value = _header_text(response, name)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _header_text(response: Any, name: str) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    value = getter(name) if callable(getter) else None
    return str(value or "")[:128]


def _read_bounded(response: Any, maximum: int) -> bytes:
    data = response.read(maximum + 1)
    if not isinstance(data, bytes):
        data = str(data or "").encode("utf-8", errors="replace")
    if len(data) > maximum:
        raise _WebSearchPolicyError("search_response_too_large")
    return data


def _parse_items(body: bytes, content_type: str, base_url: str) -> list[dict[str, str]]:
    text = body.decode("utf-8", errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return _json_items(json.loads(text))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    parser = _SearchHTMLParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return []
    return [
        {**item, "url": urljoin(base_url, str(item.get("url") or ""))}
        for item in parser.items
        if item.get("url")
    ]


def _json_items(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, Mapping):
        raw_items = value.get("results") or value.get("items") or value.get("data") or []
    else:
        return []
    result = []
    for item in raw_items[:32] if isinstance(raw_items, list) else []:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url") or item.get("link") or item.get("href")
        title = item.get("title") or item.get("name")
        snippet = item.get("snippet") or item.get("description") or item.get("content")
        if url:
            result.append({
                "url": str(url)[:_MAX_URL],
                "title": str(title or "")[:_MAX_TITLE],
                "snippet": str(snippet or "")[:_MAX_SNIPPET],
            })
    return result


def _project_sources(
    items: Iterable[Mapping[str, Any]],
    allowed_domains: tuple[str, ...],
    limit: int,
    *,
    retrieved_at: str = "",
    policy: WebAccessPolicy | None = None,
) -> list[dict[str, str]]:
    sources = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        raw_url = str(item.get("url") or "")[:_MAX_URL]
        parsed = urlsplit(raw_url)
        redirect = parse_qs(parsed.query).get("uddg")
        if redirect and redirect[0]:
            raw_url = unquote(str(redirect[0]))[:_MAX_URL]
        if policy is not None:
            decision = policy.check_url(raw_url, require_allowlisted=False)
            host = decision.host if decision.allowed else ""
        else:
            host = _validated_url_host(raw_url, allowed_domains, "search_source_not_allowlisted")
        if not host:
            continue
        url = _canonical_url(raw_url)
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append(
            {
                "title": _clean_text(item.get("title"), _MAX_TITLE) or "未命名来源",
                "url": url,
                "domain": host[:_MAX_DOMAIN],
                "snippet": _clean_text(item.get("snippet"), _MAX_SNIPPET),
            }
        )
        if retrieved_at:
            sources[-1]["retrieved_at"] = retrieved_at
        if len(sources) >= limit:
            break
    return sources


def _canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))[:_MAX_URL]


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _response_is_invalid(body: bytes, content_type: str) -> bool:
    text = body.decode("utf-8", errors="replace").lstrip()
    if "json" in content_type.lower():
        try:
            json.loads(text)
            return False
        except (TypeError, ValueError, json.JSONDecodeError):
            return True
    return not text or ("<" not in text and not text.startswith(("{", "[")))


def _search_policy_reason(reason_code: str) -> str:
    """Keep M321 public reason codes stable while sharing policy logic."""

    if reason_code in {"web_host_not_allowlisted", "web_address_not_public"}:
        return "search_redirect_not_allowlisted"
    return reason_code or "search_network_error"


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return default
    return max(minimum, min(parsed, maximum))


__all__ = [
    "DOCUMENT_EVIDENCE_SCHEMA_VERSION",
    "WebSearchAdapter",
    "WebSearchConfig",
    "web_search_tool_definition",
]
