"""GIS adapter for the generic Agent Runtime domain-pack seam."""

from __future__ import annotations

from typing import Any, Mapping

from agent.capability_catalog import capability_catalog
from agent.capability_routing import CapabilityRouter
from agent.workflow_templates import workflow_template_catalog, workflow_template_context_summary
from agent.request_model import parse_spatial_request

from .catalog import (
    GIS_CAPABILITIES,
    GIS_DATASET_GROUPS,
    GIS_DATASET_TOOL_CAPABILITIES,
)


class GisDomainPack:
    """Provide GIS discovery/catalog behavior without embedding it in Runtime."""

    domain_id = "gis"

    def extract_request_facts(self, request: str) -> Any:
        return parse_spatial_request(request)

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        catalog = capability_catalog(
            environment=environment,
            domain_id=self.domain_id,
            capability_definitions=GIS_CAPABILITIES,
            dataset_tool_capabilities=GIS_DATASET_TOOL_CAPABILITIES,
            dataset_groups=GIS_DATASET_GROUPS,
            workflow_templates=workflow_template_catalog(),
        )
        result = dict(catalog)
        result["domain_id"] = self.domain_id
        return result

    def discover(self, request: str, request_facts: Any) -> Any:
        return CapabilityRouter().discover(request, request_facts)

    def workflow_template_context(
        self,
        *,
        include_arg_shape: bool = False,
        compact: bool = True,
    ) -> Mapping[str, Any]:
        return workflow_template_context_summary(
            include_arg_shape=include_arg_shape,
            compact=compact,
        )


GIS_DOMAIN_PACK = GisDomainPack()
