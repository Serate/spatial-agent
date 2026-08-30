"""Bounded HTML fetching behind the shared public-web policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..errors import ToolError
from .web_policy import (
    DEFAULT_WEB_MODE,
    MAX_WEB_URL,
    WebAccessPolicy,
    normalize_web_domains,
)


WEB_FETCH_TOOL_NAME = "web_fetch"
WEB_FETCH_SCHEMA_VERSION = "spatial-agent.web-fetch.v1"
DOCUMENT_EVIDENCE_RESULT_TYPE = "document_evidence"
_MAX_TITLE = 240
_MAX_PREVIEW = 1600
_MAX_MODEL_CHARS = 24_000
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class WebFetchConfig:
    mode: str = DEFAULT_WEB_MODE
    allowed_domains: tuple[str, ...] = ()
    timeout_seconds: float = 10.0
    max_response_bytes: int = _MAX_RESPONSE_BYTES
    max_model_chars: int = _MAX_MODEL_CHARS
    user_agent: str = "spatial-agent-web-fetch/1.0"


class WebFetchAdapter:
    """Fetch one HTML page and return a safe projection plus transient text."""

    def __init__(
        self,
        config: WebFetchConfig | None = None,
        *,
        opener: Any = None,
        resolver: Callable[..., Any] | None = None,
        policy: WebAccessPolicy | None = None,
    ) -> None:
        self._config = config or WebFetchConfig()
        self._allowed_domains = normalize_web_domains(self._config.allowed_domains)
        self._policy = policy or WebAccessPolicy(
            self._config.mode,
            self._allowed_domains,
            resolver=resolver,
        )
        self._opener = opener

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None,
        *,
        policy: WebAccessPolicy | None = None,
    ) -> "WebFetchAdapter":
        values = settings if isinstance(settings, Mapping) else {}
        config = WebFetchConfig(
            mode=str(values.get("web_mode") or DEFAULT_WEB_MODE).strip().lower(),
            allowed_domains=normalize_web_domains(values.get("web_allowed_domains")),
            timeout_seconds=_bounded_float(values.get("web_fetch_timeout_seconds"), 10.0, 1.0, 30.0),
            max_response_bytes=_bounded_int(
                values.get("web_fetch_max_response_bytes"),
                _MAX_RESPONSE_BYTES,
                1024,
                20 * 1024 * 1024,
            ),
            max_model_chars=_bounded_int(
                values.get("web_fetch_max_model_chars"),
                _MAX_MODEL_CHARS,
                512,
                48_000,
            ),
        )
        return cls(config, policy=policy)

    @property
    def config(self) -> WebFetchConfig:
        return self._config

    def invoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.fetch(arguments.get("url"), source=arguments.get("source"))

    def fetch(self, url: Any, *, source: Any = None) -> dict[str, Any]:
        del source  # Authorization is enforced by the Runtime's same-Run seam.
        decision = self._policy.check_url(url)
        if not decision.allowed:
            return _unavailable(
                url,
                decision.host,
                _fetch_reason(decision.reason_code),
            )
        base = _base_result(decision.url, decision.host)
        try:
            response = self._open(decision.url)
            try:
                final_url = str(response.geturl() or decision.url)
                final_decision = self._policy.check_url(final_url)
                if not final_decision.allowed:
                    return _unavailable(
                        decision.url,
                        decision.host,
                        _fetch_reason(final_decision.reason_code),
                    )
                content_type = _header_text(response, "Content-Type")
                if not _is_html(content_type):
                    return _unavailable(
                        final_decision.url,
                        final_decision.host,
                        "web_content_type_unsupported",
                    )
                content_length = _header(response, "Content-Length")
                if content_length is not None and content_length > self._config.max_response_bytes:
                    return _unavailable(
                        final_decision.url,
                        final_decision.host,
                        "web_response_too_large",
                    )
                body = _read_bounded(response, self._config.max_response_bytes)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except _WebFetchPolicyError as exc:
            return _unavailable(decision.url, decision.host, exc.reason_code)
        except TimeoutError:
            return _unavailable(decision.url, decision.host, "web_fetch_timeout")
        except (HTTPError, URLError, OSError):
            return _unavailable(decision.url, decision.host, "web_fetch_network_error")
        except Exception:
            return _unavailable(decision.url, decision.host, "web_fetch_network_error")

        title, text = _extract_html(body)
        if not text:
            return _unavailable(decision.url, decision.host, "web_document_empty")
        model_text = text[: self._config.max_model_chars]
        preview = text[:_MAX_PREVIEW]
        source_record = {
            "title": title[:_MAX_TITLE] or "未命名页面",
            "url": final_decision.url,
            "domain": final_decision.host,
        }
        if preview:
            source_record["snippet"] = preview
        result = {
            **base,
            "status": "ok",
            "url": final_decision.url,
            "domain": final_decision.host,
            "source_count": 1,
            "sources": [dict(source_record)],
            "source_records": [dict(source_record)],
            "title": title[:_MAX_TITLE] or "未命名页面",
            "content_type": content_type[:96] or "text/html",
            "content_length": len(text),
            "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_preview": preview,
            "truncated": len(model_text) < len(text),
            "reason_code": "web_fetch_completed",
        }
        # This key is an internal handoff. RuntimeReactExecution removes it
        # before StepRun/state persistence and keeps it only for answer input.
        result["_model_context"] = {
            "url": final_decision.url,
            "domain": final_decision.host,
            "title": title[:_MAX_TITLE] or "未命名页面",
            "text": model_text,
        }
        return result

    def _open(self, url: str) -> Any:
        request = Request(
            url,
            headers={
                "Accept": "text/html, application/xhtml+xml;q=0.9",
                "User-Agent": self._config.user_agent[:120],
            },
            method="GET",
        )
        opener_target = self._opener or self._build_opener()
        opener = getattr(opener_target, "open", None)
        if not callable(opener):
            raise _WebFetchPolicyError("web_fetch_opener_unavailable")
        return opener(request, timeout=self._config.timeout_seconds)

    def _build_opener(self) -> Any:
        redirect_count = 0

        class SafeRedirectHandler(HTTPRedirectHandler):
            def redirect_request(inner_self, req, fp, code, msg, headers, newurl):
                nonlocal redirect_count
                if redirect_count >= _MAX_REDIRECTS:
                    raise _WebFetchPolicyError("web_redirect_limit_exceeded")
                redirect_count += 1
                target = urljoin(req.full_url, newurl)
                decision = self._policy.check_url(target)
                if not decision.allowed:
                    raise _WebFetchPolicyError(_fetch_reason(decision.reason_code))
                return super().redirect_request(req, fp, code, msg, headers, decision.url)

        return build_opener(SafeRedirectHandler())


class _WebFetchPolicyError(Exception):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = str(reason_code)[:96]
        super().__init__(self.reason_code)


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._title_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "title":
            self._title_depth += 1
        if name in {"script", "style", "noscript", "template", "svg", "form"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "title" and self._title_depth:
            self._title_depth -= 1
        if name in {"script", "style", "noscript", "template", "svg", "form"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        value = " ".join(str(data).split())
        if not value or self._skip_depth:
            return
        if self._title_depth:
            self.title_parts.append(value)
        else:
            self.text_parts.append(value)


def web_fetch_tool_definition() -> dict[str, Any]:
    return {
        "name": WEB_FETCH_TOOL_NAME,
        "description": "读取一个受控 HTTPS HTML 页面，提取有限正文供当前分析使用。",
        "side_effect": "none",
        "requires_approval": False,
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "minLength": 1, "maxLength": MAX_WEB_URL},
                "source": {"type": "string", "maxLength": 96},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": [
                "schema_version",
                "status",
                "result_type",
                "url",
                "reason_code",
            ],
            "properties": {
                "result_type": {"type": "string", "const": DOCUMENT_EVIDENCE_RESULT_TYPE},
            },
            "additionalProperties": True,
        },
    }


def _extract_html(body: bytes) -> tuple[str, str]:
    parser = _HTMLTextParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        return "", ""
    title = " ".join(parser.title_parts)
    text = "\n".join(parser.text_parts)
    return title, text[:_MAX_MODEL_CHARS * 2]


def _base_result(url: str, domain: str) -> dict[str, Any]:
    return {
        "schema_version": WEB_FETCH_SCHEMA_VERSION,
        "result_type": DOCUMENT_EVIDENCE_RESULT_TYPE,
        "status": "unavailable",
        "url": url[:MAX_WEB_URL],
        "domain": domain[:255],
        "reason_code": "web_fetch_unavailable",
    }


def _unavailable(url: Any, domain: str, reason_code: str) -> dict[str, Any]:
    return {
        **_base_result(str(url or ""), domain),
        "reason_code": str(reason_code or "web_fetch_unavailable")[:96],
    }


def _fetch_reason(reason_code: str) -> str:
    return reason_code or "web_url_not_allowed"


def _is_html(content_type: str) -> bool:
    lowered = str(content_type or "").lower()
    return not lowered or "text/html" in lowered or "application/xhtml+xml" in lowered


def _header(response: Any, name: str) -> int | None:
    value = _header_text(response, name)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _header_text(response: Any, name: str) -> str:
    headers = getattr(response, "headers", None)
    getter = getattr(headers, "get", None) if headers is not None else None
    value = getter(name) if callable(getter) else None
    return str(value or "")[:128]


def _read_bounded(response: Any, maximum: int) -> bytes:
    data = response.read(maximum + 1)
    if not isinstance(data, bytes):
        data = str(data or "").encode("utf-8", errors="replace")
    if len(data) > maximum:
        raise _WebFetchPolicyError("web_response_too_large")
    return data


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
    return max(minimum, min(parsed, maximum))


__all__ = [
    "WEB_FETCH_SCHEMA_VERSION",
    "WEB_FETCH_TOOL_NAME",
    "DOCUMENT_EVIDENCE_RESULT_TYPE",
    "WebFetchAdapter",
    "WebFetchConfig",
    "web_fetch_tool_definition",
]
