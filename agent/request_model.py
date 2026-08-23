"""Domain-neutral RequestFacts value object and legacy GIS parser facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


REQUEST_FACTS_SCHEMA_VERSION = "spatial-agent.request-facts.v1"


@dataclass(frozen=True)
class RequestFacts:
    """Planner-neutral facts shared by domain-owned request extractors.

    ``entities`` is the generic entity bag. ``admin_name`` remains as a
    bounded compatibility field for historical GIS artifacts; new Domains
    should put their named entities in ``entities`` instead of adding shared
    fields to this module.
    """

    text: str
    admin_name: Optional[str]
    tasks: Tuple[str, ...]
    datasets: Tuple[str, ...]
    constraints: Dict[str, Any]
    evidence: Tuple[str, ...]
    entities: Dict[str, Any] = field(default_factory=dict)

    def entity_snapshot(self) -> Dict[str, Any]:
        """Return bounded generic entities with the legacy GIS alias merged."""
        result = {}
        for key, value in (self.entities or {}).items():
            text = str(key or "").strip()[:80]
            if text and value is not None and len(result) < 16:
                result[text] = value
        if self.admin_name and "admin_name" not in result:
            result["admin_name"] = self.admin_name
        return result

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": REQUEST_FACTS_SCHEMA_VERSION,
            "text": self.text,
            "admin_name": self.admin_name,
            "entities": self.entity_snapshot(),
            "tasks": list(self.tasks),
            "datasets": list(self.datasets),
            "constraints": dict(self.constraints),
            "evidence": list(self.evidence),
        }

    def as_context_dict(self) -> Dict[str, Any]:
        """Return bounded, non-verbatim facts safe for planner context."""
        return {
            "schema_version": REQUEST_FACTS_SCHEMA_VERSION,
            "admin_name": self.admin_name,
            "entities": self.entity_snapshot(),
            "tasks": list(self.tasks),
            "datasets": list(self.datasets),
            "constraints": dict(self.constraints),
            "evidence": list(self.evidence),
        }


def parse_spatial_request(request: str) -> RequestFacts:
    """Legacy import facade; the implementation belongs to the GIS Domain."""
    from domains.gis.request_model import parse_spatial_request as parse_gis_request

    return parse_gis_request(request)


# Compatibility name retained for old planner and capability adapters.
SpatialRequest = RequestFacts
