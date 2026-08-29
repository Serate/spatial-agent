"""Controlled provider selection for automatic Domain routing."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from time import perf_counter
from threading import RLock
from typing import Any, Protocol

from .domain_selector import (
    CatalogDomainSelector,
    DomainRoutingDecision,
    DomainSelector,
    FallbackDomainSelector,
    ModelDomainSelector,
    normalize_domain_discovery_snapshot,
)
from .llm_planner import OpenAIPlannerClient
from agent.integration.openai_config import load_openai_config


DOMAIN_SELECTOR_PROVIDER_STATUS_SCHEMA_VERSION = (
    "spatial-agent.domain-selector-provider-status.v1"
)
DOMAIN_SELECTOR_PROVIDER_METRICS_SCHEMA_VERSION = (
    "spatial-agent.domain-selector-provider-metrics.v1"
)
DOMAIN_SELECTOR_MODE_ENV = "SPATIAL_AGENT_DOMAIN_SELECTOR_MODE"
_MODES = frozenset({"catalog", "model"})
_SAFE_ERROR_CODES = frozenset(
    {
        "provider_authentication",
        "provider_http_error",
        "provider_network",
        "provider_rate_limited",
        "provider_timeout",
        "provider_transient_http",
        "invalid_model_response",
        "invalid_domain_selector_output",
    }
)
_SAFE_CLIENT_STATUSES = frozenset({"in_progress", "success", "error"})
_SAFE_CLIENT_ERROR_TYPES = frozenset(
    {
        "http_error",
        "url_error",
        "timeout",
        "response_json_error",
        "response_shape_error",
    }
)


class DomainSelectorProviderError(ValueError):
    """Bounded configuration error that never includes a configured value."""

    def __init__(self, message: str, *, code: str):
        self.code = str(code)[:64]
        super().__init__(message)


class StructuredJSONClient(Protocol):
    def complete_json(
        self,
        messages: Any,
        schema: Mapping[str, Any],
        *,
        schema_name: str | None = None,
    ) -> Mapping[str, Any]:
        ...


def domain_selection_identity_schema() -> dict[str, Any]:
    """Schema containing only allowlisted Domain/capability identities."""

    candidate = {
        "type": "object",
        "properties": {
            "domain_id": {"type": "string", "maxLength": 96},
            "capability_ids": {
                "type": "array",
                "items": {"type": "string", "maxLength": 96},
                "maxItems": 8,
            },
        },
        "required": ["domain_id", "capability_ids"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["selected", "ambiguous", "unmatched"],
            },
            "domain_id": {
                "anyOf": [{"type": "string", "maxLength": 96}, {"type": "null"}]
            },
            "capability_ids": {
                "type": "array",
                "items": {"type": "string", "maxLength": 96},
                "maxItems": 8,
            },
            "candidates": {"type": "array", "items": candidate, "maxItems": 8},
        },
        "required": ["status", "domain_id", "capability_ids", "candidates"],
        "additionalProperties": False,
    }


class OpenAIDomainSelectorAdapter:
    """Adapt the existing structured model transport to identity-only selection."""

    def __init__(self, client: StructuredJSONClient) -> None:
        self._client = client
        self._lock = RLock()
        self._calls = 0
        self._last_status = "not_called"
        self._last_error_code: str | None = None

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        discovery = normalize_domain_discovery_snapshot(payload.get("catalog", {}))
        request = str(payload.get("request") or "").strip()[:4000]
        messages = [
            {
                "role": "system",
                "content": (
                    "Select only identities present in discovery. Return only JSON matching "
                    "the identity schema. Use null and empty arrays for fields that do not apply."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"discovery": discovery, "request": request},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]
        with self._lock:
            self._calls += 1
        try:
            # Some OpenAI-compatible gateways accept the planner's generic
            # JSON-object mode but reject a nested strict json_schema with
            # HTTP 400.  Keep the identity schema in the application call so
            # ModelDomainSelector can validate it locally, while asking the
            # provider for the broadly supported JSON-object wire format.
            result = self._client.complete_json(
                messages,
                domain_selection_identity_schema(),
                schema_name=None,
            )
        except Exception as exc:
            error_code = _safe_error_code(exc)
            with self._lock:
                self._last_status = "error"
                self._last_error_code = error_code
            raise DomainSelectorProviderError(
                "model domain selector request failed",
                code=error_code,
            ) from None
        with self._lock:
            self._last_status = "success"
            self._last_error_code = None
        return result

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {
                "calls": self._calls,
                "status": self._last_status,
            }
            if self._last_error_code:
                result["error_code"] = self._last_error_code
        client_metrics = getattr(self._client, "metrics", None)
        if callable(client_metrics):
            try:
                raw = client_metrics()
            except Exception:
                raw = None
            if isinstance(raw, Mapping):
                result["client"] = _safe_client_metrics(raw)
        return result


class DomainSelectorProvider:
    """Safe configuration/status wrapper around one Domain selector."""

    def __init__(
        self,
        mode: str,
        selector: DomainSelector,
        *,
        adapter: OpenAIDomainSelectorAdapter | None = None,
    ) -> None:
        self.mode = mode
        self.selector = selector
        self._adapter = adapter
        self._lock = RLock()
        self._selections = 0
        self._fallbacks = 0
        self._last_latency_ms: float | None = None
        self._last_fallback_reason: str | None = None

    @property
    def selector_id(self) -> str:
        return self.selector.selector_id

    def select(self, request: str, snapshot: Mapping[str, Any]) -> DomainRoutingDecision:
        started = perf_counter()
        decision = self.selector.select(request, snapshot)
        latency_ms = round((perf_counter() - started) * 1000, 3)
        with self._lock:
            self._selections += 1
            self._last_latency_ms = latency_ms
            if decision.selector_id == "fallback.v1":
                self._fallbacks += 1
                self._last_fallback_reason = (
                    decision.reason_code.partition(":")[2][:64] or "unknown"
                )
            else:
                self._last_fallback_reason = None
        return decision

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": DOMAIN_SELECTOR_PROVIDER_STATUS_SCHEMA_VERSION,
            "status": "ready",
            "mode": self.mode,
            "selector_id": self.selector.selector_id,
            "model_enabled": self.mode == "model",
            "fallback_enabled": self.mode == "model",
        }

    def configuration_status(self) -> dict[str, Any]:
        """Return the same bounded projection under an explicit public name."""

        return self.status()

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {
                "schema_version": DOMAIN_SELECTOR_PROVIDER_METRICS_SCHEMA_VERSION,
                "mode": self.mode,
                "selections": self._selections,
                "fallbacks": self._fallbacks,
            }
            if self._last_latency_ms is not None:
                result["last_latency_ms"] = self._last_latency_ms
            if self._last_fallback_reason:
                result["last_fallback_reason"] = self._last_fallback_reason
        if self._adapter is not None:
            adapter_metrics = self._adapter.metrics()
            result["adapter"] = {
                key: value for key, value in adapter_metrics.items() if key != "client"
            }
            if "client" in adapter_metrics:
                result["client"] = adapter_metrics["client"]
        return result


def build_domain_selector_provider(
    *,
    mode: str | None = None,
    environ: Mapping[str, str] | None = None,
    client: Any = None,
    client_factory: Callable[[], StructuredJSONClient] | None = None,
) -> DomainSelectorProvider:
    """Build the explicitly selected adapter; unknown modes fail closed."""

    source = os.environ if environ is None else environ
    selected_mode = str(
        mode or source.get(DOMAIN_SELECTOR_MODE_ENV) or "catalog"
    ).strip().lower()
    if selected_mode not in _MODES:
        raise DomainSelectorProviderError(
            "unsupported domain selector mode",
            code="invalid_domain_selector_mode",
        )
    if selected_mode == "model":
        if client is None:
            try:
                client = (
                    client_factory()
                    if client_factory is not None
                    else OpenAIPlannerClient(
                        **{
                            **load_openai_config(),
                            "reasoning_effort": "medium",
                        }
                    )
                )
            except Exception:
                raise DomainSelectorProviderError(
                    "model domain selector is not configured",
                    code="domain_selector_model_not_configured",
                ) from None
        if not callable(getattr(client, "complete_json", None)):
            raise DomainSelectorProviderError(
                "model domain selector is not configured",
                code="domain_selector_model_not_configured",
            )
        adapter = OpenAIDomainSelectorAdapter(client)
        selector = FallbackDomainSelector(
            ModelDomainSelector(adapter),
            CatalogDomainSelector(),
        )
        return DomainSelectorProvider("model", selector, adapter=adapter)
    return DomainSelectorProvider("catalog", CatalogDomainSelector())


def domain_selector_from_environment(**kwargs: Any) -> DomainSelectorProvider:
    """Explicit environment factory alias for application composition roots."""

    return build_domain_selector_provider(**kwargs)


def _safe_error_code(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "")
    if code in _SAFE_ERROR_CODES:
        return code
    if isinstance(exc, TimeoutError):
        return "provider_timeout"
    return "domain_selector_model_error"


def _safe_client_metrics(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    status = value.get("status")
    if status in _SAFE_CLIENT_STATUSES:
        result["status"] = status
    error_type = value.get("error_type")
    if error_type in _SAFE_CLIENT_ERROR_TYPES:
        result["error_type"] = error_type
    for key in ("attempts", "retries"):
        item = value.get(key)
        if type(item) is int and 0 <= item <= 100:
            result[key] = item
    latency = value.get("latency_ms")
    if type(latency) in (int, float) and 0 <= latency <= 3_600_000:
        result["latency_ms"] = round(float(latency), 3)
    response_status = value.get("response_status")
    if type(response_status) is int and 100 <= response_status <= 599:
        result["response_status"] = response_status
    usage = value.get("usage")
    if isinstance(usage, Mapping):
        result["usage"] = {
            key: count
            for key, count in usage.items()
            if key in {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
            }
            and type(count) is int
            and count >= 0
        }
    return result


__all__ = [
    "DOMAIN_SELECTOR_MODE_ENV",
    "DOMAIN_SELECTOR_PROVIDER_METRICS_SCHEMA_VERSION",
    "DOMAIN_SELECTOR_PROVIDER_STATUS_SCHEMA_VERSION",
    "DomainSelectorProvider",
    "DomainSelectorProviderError",
    "OpenAIDomainSelectorAdapter",
    "build_domain_selector_provider",
    "domain_selection_identity_schema",
    "domain_selector_from_environment",
]
