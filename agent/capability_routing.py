"""Compatibility facade for the former GIS capability router.

New domain code should import ``agent.capability_discovery`` for value
objects and its own Domain Pack router.  This module remains for old planner
and test imports and delegates to the GIS adapter lazily.
"""

from __future__ import annotations

from typing import Any, Iterable

from .capability_discovery import (
    CAPABILITY_DISCOVERY_SCHEMA_VERSION,
    CapabilityDiscovery,
    CapabilityMatch,
    CapabilityRoute,
)


def _gis_routing():
    from domains.gis import routing

    return routing


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return _gis_routing().contains_any(text, terms)


def signal_terms(signal: str):
    return _gis_routing().signal_terms(signal)


def request_signals(text: str, spatial: Any):
    return _gis_routing().request_signals(text, spatial)


class CapabilityRouter:
    """Legacy GIS router adapter; prefer ``GisCapabilityRouter`` in GIS code."""

    def __init__(self, routes=None) -> None:
        self._router = _gis_routing().GisCapabilityRouter(routes)

    @property
    def route_ids(self):
        return self._router.route_ids

    def select(self, text: str, spatial: Any):
        return self._router.select(text, spatial)

    def discover(self, text: str, spatial: Any):
        return self._router.discover(text, spatial)


def __getattr__(name: str):
    if name in {"SIGNAL_TERMS", "RASTER_TASKS", "VECTOR_TASKS", "DEFAULT_ROUTES"}:
        return getattr(_gis_routing(), name)
    raise AttributeError(name)
