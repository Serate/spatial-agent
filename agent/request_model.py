"""Domain-neutral RequestFacts value object and legacy GIS parser facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


REQUEST_FACTS_SCHEMA_VERSION = "spatial-agent.request-facts.v1"


@dataclass(frozen=True)
class RequestFacts:
    """Planner-neutral facts shared by domain-owned request extractors.

    ``admin_name`` remains as a bounded compatibility field for historical
    GIS artifacts.  New domains should represent named entities in their own
    facts implementation rather than adding another shared field here.
    """

    text: str
    admin_name: Optional[str]
    tasks: Tuple[str, ...]
    datasets: Tuple[str, ...]
    constraints: Dict[str, Any]
    evidence: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": REQUEST_FACTS_SCHEMA_VERSION,
            "text": self.text,
            "admin_name": self.admin_name,
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
