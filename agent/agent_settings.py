"""Product-facing defaults for the open Agent execution modes."""

from __future__ import annotations

import os
from typing import Any

from .runtime_core.execution_policy import DEFAULT_REACT_MAX_ACTIONS, DEFAULT_REACT_MAX_TURNS


REACT_MODE_ENV = "SPATIAL_AGENT_REACT_MODE"
WEB_SEARCH_ENABLED_ENV = "SPATIAL_AGENT_WEB_SEARCH_ENABLED"
TOOL_PROPOSALS_ENABLED_ENV = "SPATIAL_AGENT_TOOL_PROPOSALS_ENABLED"
REACT_MAX_TURNS_ENV = "SPATIAL_AGENT_REACT_MAX_TURNS"
REACT_MAX_ACTIONS_ENV = "SPATIAL_AGENT_REACT_MAX_ACTIONS"

DEFAULT_REACT_MODE = "full"
DEFAULT_WEB_SEARCH_ENABLED = True
DEFAULT_TOOL_PROPOSALS_ENABLED = True


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


__all__ = [
    "DEFAULT_REACT_MODE",
    "DEFAULT_TOOL_PROPOSALS_ENABLED",
    "DEFAULT_WEB_SEARCH_ENABLED",
    "REACT_MODE_ENV",
    "REACT_MAX_ACTIONS_ENV",
    "REACT_MAX_TURNS_ENV",
    "TOOL_PROPOSALS_ENABLED_ENV",
    "WEB_SEARCH_ENABLED_ENV",
    "open_agent_defaults",
]
