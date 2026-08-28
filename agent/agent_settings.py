"""Product-facing defaults for the open Agent execution modes."""

from __future__ import annotations

import os
from typing import Any

from .runtime_core.execution_policy import DEFAULT_REACT_MAX_ACTIONS, DEFAULT_REACT_MAX_TURNS


REACT_MODE_ENV = "SPATIAL_AGENT_REACT_MODE"
WEB_SEARCH_ENABLED_ENV = "SPATIAL_AGENT_WEB_SEARCH_ENABLED"
WEB_SEARCH_URL_ENV = "SPATIAL_AGENT_WEB_SEARCH_URL"
WEB_ALLOWED_DOMAINS_ENV = "SPATIAL_AGENT_WEB_ALLOWED_DOMAINS"
WEB_SEARCH_TIMEOUT_ENV = "SPATIAL_AGENT_WEB_SEARCH_TIMEOUT_SECONDS"
WEB_SEARCH_MAX_RESPONSE_BYTES_ENV = "SPATIAL_AGENT_WEB_SEARCH_MAX_RESPONSE_BYTES"
WEB_SEARCH_MAX_SOURCES_ENV = "SPATIAL_AGENT_WEB_SEARCH_MAX_SOURCES"
TOOL_PROPOSALS_ENABLED_ENV = "SPATIAL_AGENT_TOOL_PROPOSALS_ENABLED"
REACT_MAX_TURNS_ENV = "SPATIAL_AGENT_REACT_MAX_TURNS"
REACT_MAX_ACTIONS_ENV = "SPATIAL_AGENT_REACT_MAX_ACTIONS"

DEFAULT_REACT_MODE = "full"
DEFAULT_WEB_SEARCH_ENABLED = True
DEFAULT_TOOL_PROPOSALS_ENABLED = True
DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS = 8.0
DEFAULT_WEB_SEARCH_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_WEB_SEARCH_MAX_SOURCES = 8


def open_agent_defaults() -> dict[str, Any]:
    """Read allowlisted product defaults without exposing arbitrary settings."""

    mode = str(os.environ.get(REACT_MODE_ENV) or DEFAULT_REACT_MODE).strip().lower()
    if mode not in {"full", "hybrid", "off"}:
        mode = DEFAULT_REACT_MODE
    return {
        "react_mode": mode,
        "web_search_enabled": _bool_env(
            WEB_SEARCH_ENABLED_ENV, DEFAULT_WEB_SEARCH_ENABLED
        ),
        "web_search_provider_url": str(
            os.environ.get(WEB_SEARCH_URL_ENV) or ""
        ).strip()[:2048],
        "web_allowed_domains": _csv_env(WEB_ALLOWED_DOMAINS_ENV),
        "web_search_timeout_seconds": _bounded_float(
            WEB_SEARCH_TIMEOUT_ENV,
            DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS,
            1.0,
            30.0,
        ),
        "web_search_max_response_bytes": _bounded_int(
            WEB_SEARCH_MAX_RESPONSE_BYTES_ENV,
            DEFAULT_WEB_SEARCH_MAX_RESPONSE_BYTES,
            1024,
            20 * 1024 * 1024,
        ),
        "web_search_max_sources": _bounded_int(
            WEB_SEARCH_MAX_SOURCES_ENV,
            DEFAULT_WEB_SEARCH_MAX_SOURCES,
            1,
            8,
        ),
        "tool_proposals_enabled": _bool_env(
            TOOL_PROPOSALS_ENABLED_ENV, DEFAULT_TOOL_PROPOSALS_ENABLED
        ),
        "react_max_turns": _bounded_int(
            REACT_MAX_TURNS_ENV, DEFAULT_REACT_MAX_TURNS, 1, 32
        ),
        "react_max_actions": _bounded_int(
            REACT_MAX_ACTIONS_ENV, DEFAULT_REACT_MAX_ACTIONS, 1, 128
        ),
    }


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    if value != value or value in {float("inf"), float("-inf")}:
        return default
    return max(minimum, min(value, maximum))


def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()[:255]
        for item in str(os.environ.get(name) or "").split(",")
        if item.strip()
    )[:32]


__all__ = [
    "DEFAULT_REACT_MODE",
    "DEFAULT_TOOL_PROPOSALS_ENABLED",
    "DEFAULT_WEB_SEARCH_ENABLED",
    "DEFAULT_WEB_SEARCH_MAX_RESPONSE_BYTES",
    "DEFAULT_WEB_SEARCH_MAX_SOURCES",
    "DEFAULT_WEB_SEARCH_TIMEOUT_SECONDS",
    "REACT_MODE_ENV",
    "REACT_MAX_ACTIONS_ENV",
    "REACT_MAX_TURNS_ENV",
    "TOOL_PROPOSALS_ENABLED_ENV",
    "WEB_ALLOWED_DOMAINS_ENV",
    "WEB_SEARCH_ENABLED_ENV",
    "WEB_SEARCH_MAX_RESPONSE_BYTES_ENV",
    "WEB_SEARCH_MAX_SOURCES_ENV",
    "WEB_SEARCH_TIMEOUT_ENV",
    "WEB_SEARCH_URL_ENV",
    "open_agent_defaults",
]
