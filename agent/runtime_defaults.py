"""Product-facing defaults for the Agent Runtime.

The lower-level ``AgentService`` and Runtime APIs keep their explicit
selection parameters so offline callers can choose deterministic rule/memory
execution.  This small, domain-neutral seam supplies defaults only where a
user-facing product boundary receives an omitted selection.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


DEFAULT_PLANNER = "openai"
DEFAULT_BACKEND = "local"
PLANNER_ENV = "SPATIAL_AGENT_DEFAULT_PLANNER"
BACKEND_ENV = "SPATIAL_AGENT_DEFAULT_BACKEND"

_PLANNERS = frozenset({"openai", "rule"})
_BACKENDS = frozenset({"local", "memory"})


def product_defaults() -> dict[str, str]:
    """Return the validated defaults for one product process.

    Environment variables are deliberately an allowlisted configuration
    switch, not an arbitrary value passthrough.  Reading them at call time
    keeps tests and explicitly managed development processes predictable.
    """

    return {
        "planner": _configured_value(
            PLANNER_ENV,
            default=DEFAULT_PLANNER,
            allowed=_PLANNERS,
        ),
        "backend": _configured_value(
            BACKEND_ENV,
            default=DEFAULT_BACKEND,
            allowed=_BACKENDS,
        ),
    }


def resolve_product_selection(
    planner: Any = None,
    backend: Any = None,
) -> tuple[str, str]:
    """Resolve omitted product selections while preserving explicit values.

    Explicit non-empty values are bounded but not allowlisted here; the
    existing Runtime/Service validation remains authoritative for invalid
    request values.  Only environment-provided *defaults* are allowlisted.
    """

    defaults = product_defaults()
    return (
        _request_value(planner, defaults["planner"]),
        _request_value(backend, defaults["backend"]),
    )


def with_product_defaults(payload: Any) -> dict[str, Any]:
    """Copy a request/query mapping and fill its omitted selection fields."""

    body = dict(payload) if isinstance(payload, Mapping) else {}
    planner, backend = resolve_product_selection(
        body.get("planner"),
        body.get("backend"),
    )
    body["planner"] = planner
    body["backend"] = backend
    return body


def _configured_value(name: str, *, default: str, allowed: frozenset[str]) -> str:
    value = os.environ.get(name)
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _request_value(value: Any, default: str) -> str:
    normalized = str(value or "").strip()
    return normalized[:32] if normalized else default


__all__ = [
    "BACKEND_ENV",
    "DEFAULT_BACKEND",
    "DEFAULT_PLANNER",
    "PLANNER_ENV",
    "product_defaults",
    "resolve_product_selection",
    "with_product_defaults",
]
