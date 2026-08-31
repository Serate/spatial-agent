"""Bounded OpenAI-compatible provider transport and plan-response decoding.

This is the provider/transport seam split out of the planner orchestration.
It owns the HTTP client, URL construction, response decoding and bounded
failures for the model provider.  It never persists prompt text, raw model
responses, request headers or keys; everything crossing this module is the
planner's responsibility to keep safe.
"""

from __future__ import annotations

import errno
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from time import perf_counter
from typing import Any, Callable, Dict, Mapping, Optional

from agent.models import TaskPlan
from agent.errors import PlanningError
from agent.integration.provider_runtime import build_provider_health
from agent.integration.provider_structured_output import (
    build_structured_output_profile,
    project_structured_output_profile,
)



def _provider_progress(
    progress: Any,
    callback: Optional[Callable[[Mapping[str, Any]], None]],
    *,
    phase: str,
) -> Optional[Callable[[Mapping[str, Any]], None]]:
    """Bridge provider-safe progress into the optional Runtime coordinator."""

    if progress is None and not callable(callback):
        return None

    allowed = {
        "kind",
        "attempt",
        "retry_count",
        "recovery_attempt",
        "received_chars",
        "elapsed_ms",
        "timeout_seconds",
    }

    def emit(value: Mapping[str, Any]) -> None:
        if not isinstance(value, Mapping):
            return
        safe = {
            key: value[key]
            for key in allowed
            if key in value and isinstance(value[key], (str, int, float, bool))
        }
        safe["phase"] = phase
        if callable(callback):
            try:
                callback(dict(safe))
            except Exception:
                # Observability must not turn a valid provider response into a
                # failed plan because a UI/event sink is unavailable.
                pass
        update = getattr(progress, "progress", None)
        if callable(update):
            kind = str(safe.get("kind") or "provider_progress")
            message = {
                "provider_call_started": "正在请求真实模型",
                "provider_retry": "真实模型请求正在重试",
                "provider_stream_delta": "正在接收答案",
                "provider_call_completed": "真实模型响应已收到",
                "provider_call_failed": "真实模型请求失败",
                "structured_recovery_started": "正在修复结构化响应",
            }.get(kind, "真实模型处理中")
            try:
                update(message, data=safe)
            except Exception:
                pass

    return emit



class OpenAIPlannerClient:
    """Minimal OpenAI Responses API client using the standard library."""

    supports_react = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_url: Optional[str] = None,
        base_url: Optional[str] = None,
        wire_api: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff_seconds: Optional[float] = None,
        retry_backoff_max_seconds: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        auth_location: Optional[str] = None,
        api_key_query_param: Optional[str] = None,
        structured_output_mode: Optional[str] = None,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise PlanningError("OPENAI_API_KEY is required for OpenAIPlannerClient")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
        self._wire_api = wire_api or os.environ.get("OPENAI_WIRE_API", "responses")
        if self._wire_api not in ("responses", "chat_completions"):
            raise PlanningError("OPENAI_WIRE_API must be responses or chat_completions")
        self._structured_output_profile = build_structured_output_profile(
            wire_api=self._wire_api,
            structured_mode=structured_output_mode
            or os.environ.get("OPENAI_STRUCTURED_OUTPUT_MODE", "json_schema"),
            source="config",
        )
        self._url = _planner_url(
            api_url=api_url or os.environ.get("OPENAI_API_URL"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com",
            wire_api=self._wire_api,
        )
        self._reasoning_effort = reasoning_effort or os.environ.get(
            "OPENAI_REASONING_EFFORT", "medium"
        )
        self._max_output_tokens = _first_not_none(
            max_output_tokens, _env_int("OPENAI_MAX_OUTPUT_TOKENS")
        )
        self._timeout_seconds = _first_not_none(
            timeout_seconds, _env_float("OPENAI_TIMEOUT_SECONDS"), 60.0
        )
        # Keep the default bounded for interactive runs.  A second retry can
        # make a slow relay look like a frozen planning stage for several
        # minutes; callers can still opt into a different explicit budget.
        self._max_retries = _first_not_none(max_retries, _env_int("OPENAI_MAX_RETRIES"), 1)
        self._retry_backoff_seconds = _first_not_none(
            retry_backoff_seconds,
            _env_float("OPENAI_RETRY_BACKOFF_SECONDS"),
            0.5,
        )
        self._retry_backoff_max_seconds = _first_not_none(
            retry_backoff_max_seconds,
            _env_float("OPENAI_RETRY_BACKOFF_MAX_SECONDS"),
            8.0,
        )
        _validate_request_settings(
            self._timeout_seconds,
            self._max_output_tokens,
            self._max_retries,
            self._retry_backoff_seconds,
            self._retry_backoff_max_seconds,
        )
        self._auth_location = auth_location or os.environ.get("OPENAI_AUTH_LOCATION", "header")
        self._api_key_query_param = api_key_query_param or os.environ.get(
            "OPENAI_API_KEY_QUERY_PARAM", "key"
        )
        self._provider_health = build_provider_health(
            {
                "provider": "openai-compatible",
                "model": self._model,
                "api_key": self._api_key,
                "api_url": self._url,
                "wire_api": self._wire_api,
                "structured_output_mode": self._structured_output_profile[
                    "structured_mode"
                ],
            }
        )
        self._last_metrics = {
            "provider": "openai-compatible",
            "wire_api": self._wire_api,
            **project_structured_output_profile(self._structured_output_profile),
            "model": self._model,
            "execution_mode": "live_model",
            "timeout_seconds": self._timeout_seconds,
            "max_output_tokens": self._max_output_tokens,
            "max_retries": self._max_retries,
            "retry_backoff_seconds": self._retry_backoff_seconds,
            "retry_backoff_max_seconds": self._retry_backoff_max_seconds,
            "provider_health": self._provider_health,
        }

    def complete_json(
        self,
        messages,
        schema: Mapping[str, Any],
        *,
        schema_name: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        deterministic: bool = False,
        timeout_seconds: Optional[float] = None,
        deadline: Optional[float] = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> Mapping[str, Any]:
        structured_schema_name = _structured_schema_name(schema_name)
        structured_mode = self._structured_output_profile["structured_mode"]
        if structured_mode == "unavailable":
            raise PlanningError("structured output mode is unavailable")
        if self._wire_api == "chat_completions":
            response_format: Dict[str, Any] = {"type": "json_object"}
            if structured_mode == "json_schema":
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": structured_schema_name,
                        "schema": schema,
                        "strict": True,
                    },
                }
            body = {
                "model": self._model,
                "messages": messages,
                "response_format": response_format,
            }
            output_limit = (
                max_output_tokens
                if max_output_tokens is not None
                else self._max_output_tokens
            )
            if output_limit is not None:
                body["max_tokens"] = output_limit
            if deterministic:
                body["temperature"] = 0
        else:
            response_format = {
                "type": "json_schema",
                "name": structured_schema_name,
                "schema": schema,
                "strict": True,
            }
            if structured_mode == "json_object":
                response_format = {"type": "json_object"}
            body = {
                "model": self._model,
                "input": messages,
                "reasoning": {"effort": self._reasoning_effort},
                "text": {"format": response_format},
            }
            output_limit = (
                max_output_tokens
                if max_output_tokens is not None
                else self._max_output_tokens
            )
            if output_limit is not None:
                body["max_output_tokens"] = output_limit
            if deterministic:
                body["temperature"] = 0
        url = self._request_url()
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        started = perf_counter()
        attempts = 0
        self._last_metrics = dict(self._last_metrics)
        for key in ("usage", "error_type", "response_status", "latency_ms"):
            self._last_metrics.pop(key, None)
        self._last_metrics.update({"attempts": 0, "retries": 0, "status": "in_progress"})
        while attempts <= self._max_retries:
            attempts += 1
            self._last_metrics["attempts"] = attempts
            try:
                request_timeout = _effective_request_timeout(
                    self._timeout_seconds, timeout_seconds, deadline
                )
                if request_timeout <= 0:
                    raise socket.timeout()
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_started",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "timeout_seconds": request_timeout,
                    },
                )
                with urllib.request.urlopen(request, timeout=request_timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self._record_success(started, attempts, payload)
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_completed",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "elapsed_ms": self._last_metrics.get("latency_ms"),
                    },
                )
                break
            except json.JSONDecodeError as exc:
                self._record_error(started, "response_json_error", attempts)
                raise _planner_error(
                    "OpenAI response was not valid JSON",
                    "response_json_error",
                ) from exc
            except urllib.error.HTTPError as exc:
                if _retryable_http_status(exc.code) and self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "http_error", attempts, exc.code)
                # Do not copy provider response bodies into the run error or
                # artifact; gateways sometimes echo credentials or private
                # request details.  The status and bounded failure contract
                # are sufficient for diagnosis and recovery.
                raise _planner_error(
                    "OpenAI request failed (HTTP {})".format(exc.code),
                    "http_error",
                    response_status=exc.code,
                    retryable=_retryable_http_status(exc.code),
                ) from exc
            except urllib.error.URLError as exc:
                is_retryable = _retryable_url_error(exc)
                if is_retryable and self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "url_error", attempts)
                raise _planner_error(
                    "OpenAI request failed (network)",
                    "url_error",
                    retryable=is_retryable,
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                if self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "timeout", attempts)
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_failed",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "elapsed_ms": self._last_metrics.get("latency_ms"),
                    },
                )
                raise _planner_error(
                    "OpenAI request timed out",
                    "timeout",
                    retryable=True,
                ) from exc

        try:
            text = self._extract_text(payload)
        except PlanningError as exc:
            self._record_error(started, "response_shape_error", attempts)
            raise _planner_error(str(exc), "response_shape_error") from exc
        try:
            return _decode_structured_json(text)
        except (json.JSONDecodeError, ValueError) as exc:
            self._record_error(started, "response_json_error", attempts)
            raise _planner_error(
                "OpenAI response was not valid JSON",
                "response_json_error",
            ) from exc

    def complete_compact_json(
        self,
        messages,
        schema: Mapping[str, Any],
        *,
        schema_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        deadline: Optional[float] = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> Mapping[str, Any]:
        """Retry one truncated plan with a larger, deterministic JSON budget."""

        configured = self._max_output_tokens or 0
        # A truncated 2048-token response needs headroom for providers that
        # spend part of the completion budget on invisible planning. This is
        # only used after a malformed response and remains bounded.
        # A configured 10k budget is used by complex open-domain planning;
        # do not make its one-shot recovery smaller than the original call.
        # The upper bound remains finite so malformed provider output cannot
        # turn into an unbounded completion request.
        recovery_limit = min(max(configured * 2, 4096), 12_000)
        return self.complete_json(
            messages,
            schema,
            schema_name=schema_name,
            max_output_tokens=recovery_limit,
            deterministic=True,
            timeout_seconds=timeout_seconds,
            deadline=deadline,
            on_progress=on_progress,
        )

    def stream_text(
        self,
        messages,
        *,
        max_chars: int = 1800,
        timeout_seconds: Optional[float] = None,
        deadline: Optional[float] = None,
        on_progress: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ):
        """Yield only user-facing text deltas from an OpenAI-compatible stream.

        This path is deliberately separate from ``complete_json``.  Plans and
        tool arguments continue to use the non-streaming structured contract;
        only the already-selected answer surface may use text deltas.
        """

        if self._wire_api == "chat_completions":
            body: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "stream": True,
            }
            if self._max_output_tokens is not None:
                body["max_tokens"] = self._max_output_tokens
        else:
            body = {
                "model": self._model,
                "input": messages,
                "stream": True,
                "reasoning": {"effort": self._reasoning_effort},
            }
            if self._max_output_tokens is not None:
                body["max_output_tokens"] = self._max_output_tokens
        request = urllib.request.Request(
            self._request_url(),
            data=json.dumps(body).encode("utf-8"),
            headers={**self._headers(), "Accept": "text/event-stream"},
            method="POST",
        )
        started = perf_counter()
        attempts = 0
        emitted = 0
        usage: Mapping[str, Any] = {}
        self._last_metrics = dict(self._last_metrics)
        for key in ("usage", "error_type", "response_status", "latency_ms"):
            self._last_metrics.pop(key, None)
        self._last_metrics.update({"attempts": 0, "retries": 0, "status": "in_progress"})
        while attempts <= self._max_retries:
            attempts += 1
            self._last_metrics["attempts"] = attempts
            emitted = 0
            try:
                request_timeout = _effective_request_timeout(
                    self._timeout_seconds, timeout_seconds, deadline
                )
                if request_timeout <= 0:
                    raise socket.timeout()
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_started",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "timeout_seconds": request_timeout,
                    },
                )
                with urllib.request.urlopen(request, timeout=request_timeout) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload_text = line[5:].strip()
                        if payload_text == "[DONE]":
                            break
                        try:
                            payload = json.loads(payload_text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(payload, Mapping) and isinstance(payload.get("usage"), Mapping):
                            usage = payload["usage"]
                        delta = _stream_text_delta(payload, self._wire_api)
                        if not delta:
                            continue
                        remaining = max(0, int(max_chars) - emitted)
                        if not remaining:
                            break
                        delta = str(delta)[:remaining]
                        emitted += len(delta)
                        if delta:
                            _notify_provider_progress(
                                on_progress,
                                {
                                    "kind": "provider_stream_delta",
                                    "attempt": attempts,
                                    "retry_count": attempts - 1,
                                    "received_chars": emitted,
                                },
                            )
                            yield delta
                if not emitted:
                    self._record_error(started, "response_shape_error", attempts)
                    raise _planner_error(
                        "OpenAI stream did not contain answer text",
                        "response_shape_error",
                    )
                self._record_success(started, attempts, {"usage": usage})
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_completed",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "received_chars": emitted,
                        "elapsed_ms": self._last_metrics.get("latency_ms"),
                    },
                )
                return
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 404, 405, 501):
                    self._record_error(started, "stream_unsupported", attempts, exc.code)
                    raise PlanningError(
                        "OpenAI provider does not support text streaming",
                        category="provider",
                        code="stream_unsupported",
                        retryable=False,
                    ) from exc
                if _retryable_http_status(exc.code) and self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "http_error", attempts, exc.code)
                raise _planner_error(
                    "OpenAI stream request failed (HTTP {})".format(exc.code),
                    "http_error",
                    response_status=exc.code,
                    retryable=_retryable_http_status(exc.code),
                ) from exc
            except urllib.error.URLError as exc:
                is_retryable = _retryable_url_error(exc)
                if is_retryable and self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "url_error", attempts)
                raise _planner_error(
                    "OpenAI stream request failed (network)",
                    "url_error",
                    retryable=is_retryable,
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                if self._can_retry(attempts, deadline):
                    _notify_provider_progress(
                        on_progress,
                        {"kind": "provider_retry", "attempt": attempts + 1, "retry_count": attempts},
                    )
                    self._wait_before_retry(attempts, deadline=deadline)
                    continue
                self._record_error(started, "timeout", attempts)
                _notify_provider_progress(
                    on_progress,
                    {
                        "kind": "provider_call_failed",
                        "attempt": attempts,
                        "retry_count": attempts - 1,
                        "received_chars": emitted,
                        "elapsed_ms": self._last_metrics.get("latency_ms"),
                    },
                )
                raise _planner_error(
                    "OpenAI stream request timed out",
                    "timeout",
                    retryable=True,
                ) from exc

    def metrics(self) -> Dict[str, Any]:
        return dict(self._last_metrics)

    def _record_success(self, started: float, attempts: int, payload: Mapping[str, Any]) -> None:
        self._last_metrics = dict(self._last_metrics)
        self._last_metrics.update(
            {
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                "attempts": attempts,
                "retries": attempts - 1,
                "status": "success",
                "usage": _usage_summary(payload.get("usage")),
            }
        )
        finish_reason = _completion_finish_reason(payload)
        if finish_reason:
            self._last_metrics["finish_reason"] = finish_reason

    def _record_error(
        self,
        started: float,
        error_type: str,
        attempts: int,
        response_status: Optional[int] = None,
    ) -> None:
        self._last_metrics = dict(self._last_metrics)
        self._last_metrics.update(
            {
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                "attempts": attempts,
                "retries": attempts - 1,
                "status": "error",
                "error_type": error_type,
            }
        )
        if response_status is not None:
            self._last_metrics["response_status"] = response_status

    def _can_retry(self, attempt: int, deadline: Optional[float]) -> bool:
        return attempt <= self._max_retries and (
            deadline is None or deadline - perf_counter() > 0
        )

    def _wait_before_retry(self, attempt: int, *, deadline: Optional[float] = None) -> None:
        delay = min(
            self._retry_backoff_seconds * (2 ** (attempt - 1)),
            self._retry_backoff_max_seconds,
        )
        if deadline is not None:
            delay = min(delay, max(0.0, deadline - perf_counter()))
        if delay > 0:
            time.sleep(delay)

    def _extract_text(self, payload: Mapping[str, Any]) -> str:
        if self._wire_api == "chat_completions":
            choices = payload.get("choices", [])
            if choices and isinstance(choices[0], Mapping):
                message = choices[0].get("message", {})
                if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                    return message["content"]
            raise PlanningError("Chat Completions response did not contain message content")
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        chunks = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        if chunks:
            return "".join(chunks)
        raise PlanningError("OpenAI response did not contain output text")

    def _request_url(self) -> str:
        if self._auth_location == "query":
            return _append_query_param(self._url, self._api_key_query_param, self._api_key)
        return self._url

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "spatial-agent/0.1",
        }
        if self._auth_location == "header":
            headers["Authorization"] = "Bearer " + self._api_key
        elif self._auth_location != "query":
            raise PlanningError("OPENAI_AUTH_LOCATION must be one of: header, query")
        return headers


def _stream_text_delta(payload: Any, wire_api: str) -> str:
    """Extract only visible answer text from known SSE payload shapes."""

    if not isinstance(payload, Mapping):
        return ""
    if wire_api == "chat_completions":
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            delta = choices[0].get("delta")
            if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
                return delta["content"]
        return ""
    event_type = str(payload.get("type") or "")
    if event_type in {"response.output_text.delta", "response.text.delta"}:
        delta = payload.get("delta")
        return delta if isinstance(delta, str) else ""
    return ""


def _effective_request_timeout(
    configured_seconds: Optional[float],
    call_seconds: Optional[float],
    deadline: Optional[float],
) -> float:
    """Bound one socket call by adapter, caller and absolute deadlines."""

    values: list[float] = []
    for value in (configured_seconds, call_seconds):
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed != parsed or parsed in {float("inf"), float("-inf")}:
            continue
        values.append(max(0.0, parsed))
    if deadline is not None:
        try:
            values.append(max(0.0, float(deadline) - perf_counter()))
        except (TypeError, ValueError, OverflowError):
            pass
    # The client constructor always has a valid timeout, but retaining a small
    # fallback makes custom test/configuration adapters deterministic.
    return min(values) if values else 60.0


def _notify_provider_progress(
    callback: Optional[Callable[[Mapping[str, Any]], None]],
    value: Mapping[str, Any],
) -> None:
    """Send only bounded provider state; callback failures are non-fatal."""

    if not callable(callback):
        return
    try:
        safe: dict[str, Any] = {}
        for key in (
            "kind",
            "attempt",
            "retry_count",
            "recovery_attempt",
            "received_chars",
            "elapsed_ms",
            "timeout_seconds",
        ):
            item = value.get(key)
            if isinstance(item, (str, int, float, bool)):
                safe[key] = item
        callback(safe)
    except Exception:
        pass


def _planner_url(api_url: Optional[str], base_url: str, wire_api: str = "responses") -> str:
    if api_url:
        return api_url.rstrip("/")
    if wire_api == "chat_completions":
        return _chat_completions_url(base_url)
    return _responses_url(base_url)


def _decode_structured_json(text: str) -> Any:
    """Decode JSON while tolerating two bounded provider presentation wrappers.

    Some OpenAI-compatible gateways return an otherwise valid JSON document
    inside a Markdown fence or after a complete ``<think>`` block. Only a
    full, explicitly bounded wrapper is accepted; schema validation remains
    the caller's responsibility and wrapper text is never persisted.
    """
    if not isinstance(text, str):
        raise ValueError("structured response must be text")
    candidate = text.strip().lstrip("\ufeff")
    if not candidate:
        raise ValueError("structured response is empty")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        original_error = exc

    think_match = re.fullmatch(
        r"<think>.*?</think>\s*(?P<body>.+)",
        candidate,
        flags=re.DOTALL,
    )
    if think_match:
        candidate = think_match.group("body").strip()

    fence_match = re.fullmatch(
        r"```(?:json)?\s*(?P<body>.*?)\s*```",
        candidate,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence_match:
        candidate = fence_match.group("body").strip()

    if candidate == text.strip().lstrip("\ufeff"):
        raise original_error
    return json.loads(candidate)


def _responses_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/responses"):
        return clean
    if clean.endswith("/v1"):
        return clean + "/responses"
    return clean + "/v1/responses"


def _chat_completions_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return clean + "/chat/completions"
    return clean + "/chat/completions"


def _structured_schema_name(value: Optional[str]) -> str:
    name = value or "task_plan"
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]{0,63}", name
    ):
        raise PlanningError("structured output schema name is invalid")
    return name


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not any(item_key == key for item_key, _ in query):
        query.append((key, value))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


def _env_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    return int(value) if value else None


def _env_float(name: str) -> Optional[float]:
    value = os.environ.get(name)
    return float(value) if value else None


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _validate_request_settings(
    timeout_seconds: float,
    max_output_tokens: Optional[int],
    max_retries: int,
    retry_backoff_seconds: float,
    retry_backoff_max_seconds: float,
) -> None:
    if timeout_seconds <= 0:
        raise PlanningError("OPENAI_TIMEOUT_SECONDS must be positive")
    if max_output_tokens is not None and max_output_tokens <= 0:
        raise PlanningError("OPENAI_MAX_OUTPUT_TOKENS must be positive")
    if max_retries < 0:
        raise PlanningError("OPENAI_MAX_RETRIES must be non-negative")
    if retry_backoff_seconds < 0 or retry_backoff_max_seconds < 0:
        raise PlanningError("OpenAI retry backoff must be non-negative")
    if retry_backoff_max_seconds < retry_backoff_seconds:
        raise PlanningError("OPENAI_RETRY_BACKOFF_MAX_SECONDS must not be below the base backoff")


def _retryable_http_status(status: int) -> bool:
    return status in (408, 425, 429) or 500 <= status <= 599


def _retryable_url_error(error: urllib.error.URLError) -> bool:
    reason = getattr(error, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout, ConnectionResetError,
                           ConnectionAbortedError, ConnectionRefusedError)):
        return True
    return getattr(reason, "errno", None) in {
        errno.ETIMEDOUT,
        errno.ECONNRESET,
        errno.ECONNABORTED,
        errno.ECONNREFUSED,
    }


def _planner_error(
    message: str,
    error_type: str,
    *,
    response_status: Optional[int] = None,
    retryable: Optional[bool] = None,
) -> PlanningError:
    """Create a bounded Planner failure with stable recovery metadata."""
    category, code, default_retryable = _planner_failure_metadata(
        error_type,
        response_status,
    )
    return PlanningError(
        message,
        category=category,
        code=code,
        retryable=default_retryable if retryable is None else retryable,
    )


def _planner_failure_metadata(
    error_type: str,
    response_status: Optional[int] = None,
) -> tuple[str, str, bool]:
    """Map provider-specific transport failures to bounded Agent semantics."""
    if error_type == "http_error":
        if response_status in (401, 403):
            return "provider", "provider_authentication", False
        if response_status == 429:
            return "provider", "provider_rate_limited", True
        if response_status in (408, 425) or (
            response_status is not None and response_status >= 500
        ):
            return "provider", "provider_transient_http", True
        return "provider", "provider_http_error", False
    if error_type == "timeout":
        return "provider", "provider_timeout", True
    if error_type == "url_error":
        return "provider", "provider_network", False
    if error_type in {"response_json_error", "response_shape_error"}:
        return "planning", "invalid_model_response", False
    return "planning", "planner_error", False


def _usage_summary(usage: Any) -> Dict[str, int]:
    if not isinstance(usage, Mapping):
        return {}
    keys = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    )
    return {
        key: usage[key]
        for key in keys
        if type(usage.get(key)) is int and usage[key] >= 0
    }


def _completion_finish_reason(payload: Mapping[str, Any]) -> Optional[str]:
    """Return a bounded completion finish reason for diagnostics only."""

    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        value = choices[0].get("finish_reason")
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", value):
            return value
    value = payload.get("status")
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", value):
        return value
    return None


def _normalize_shortcut_plan(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Expand the known single-tool response shape before TaskPlan validation."""
    if "goal" in payload or "steps" in payload:
        normalized = dict(payload)
        if isinstance(payload.get("steps"), list):
            normalized["steps"] = [
                _normalize_step_arguments(step) for step in payload["steps"]
            ]
        if isinstance(payload.get("output"), str):
            normalized["output"] = {"type": payload["output"]}
            return normalized
        return normalized
    if payload.get("outcome") not in (None, "success"):
        return payload
    tool = payload.get("tool")
    args = payload.get("args")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return payload
    args = _normalize_step_arguments({"tool": tool, "args": args})["args"]
    return {
        "goal": "execute " + tool,
        "steps": [{"id": "step-1", "tool": tool, "args": args, "depends_on": []}],
        "output": {},
    }


def _has_output_type(payload: Mapping[str, Any]) -> bool:
    output = payload.get("output")
    return isinstance(output, Mapping) and isinstance(output.get("type"), str) and bool(output["type"].strip())


def _normalize_step_arguments(step: Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize the known Chat Completions range_query shortcut."""
    if step.get("tool") != "range_query" or not isinstance(step.get("args"), dict):
        return step
    args = dict(step["args"])
    # Some OpenAI-compatible models abbreviate the canonical schema key to
    # ``op`` even when the surrounding condition shape is correct.  Normalize
    # that unambiguous alias at the planner boundary; ToolRegistry still
    # validates the resulting canonical arguments and conflicting aliases are
    # deliberately left invalid rather than guessed.
    if "operator" not in args and "op" in args:
        args["operator"] = args.pop("op")
    conditions = args.get("conditions")
    if isinstance(conditions, list):
        normalized_conditions = []
        for condition in conditions:
            if isinstance(condition, Mapping):
                condition = dict(condition)
                if "operator" not in condition and "op" in condition:
                    condition["operator"] = condition.pop("op")
                if "operator" in condition:
                    condition["operator"] = _normalize_range_operator(
                        condition["operator"]
                    )
            normalized_conditions.append(condition)
        args["conditions"] = normalized_conditions
    if "conditions" not in args and "field" in args and "value" in args:
        field = args.pop("field")
        value = args.pop("value")
        operator = args.pop("operator", "eq")
        args["conditions"] = [{"field": field, "operator": operator, "value": value}]
    if "conditions" in args and "limit" not in args:
        args["limit"] = 100
    normalized = dict(step)
    normalized["args"] = args
    return normalized


def _normalize_range_operator(value: Any) -> Any:
    """Map common symbolic comparison operators to the tool vocabulary."""
    aliases = {
        "=": "eq",
        "==": "eq",
        "!=": "neq",
        ">": "gt",
        ">=": "gte",
        "<": "lt",
        "<=": "lte",
    }
    return aliases.get(value, value)
