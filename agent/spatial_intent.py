"""Legacy compatibility facade for the GIS intent policy.

The implementation lives in ``domains.gis.intent``.  This module remains a
lazy import boundary for historical callers and old artifacts.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict


CLARIFICATION_SCHEMA_VERSION = "spatial-agent.clarification.v1"


def _gis_intent_module() -> Any:
    return importlib.import_module("domains.gis.intent")


def classify_spatial_intent(request: str) -> Dict[str, Any]:
    return _gis_intent_module().classify_spatial_intent(request)


def clarification_message(request: str) -> str:
    return _gis_intent_module().clarification_message(request)


def clarification_details(request: str) -> Dict[str, Any]:
    return _gis_intent_module().clarification_details(request)


__all__ = [
    "CLARIFICATION_SCHEMA_VERSION",
    "classify_spatial_intent",
    "clarification_message",
    "clarification_details",
]
