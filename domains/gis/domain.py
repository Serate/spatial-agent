"""GIS adapter for the generic Agent Runtime domain-pack seam."""

from __future__ import annotations

from typing import Any, Mapping

from agent.capability_catalog import capability_catalog
from agent.capability_routing import CapabilityRouter
from agent.workflow_templates import workflow_template_catalog, workflow_template_context_summary
from agent.request_model import parse_spatial_request
from agent.domain_contract import domain_action_catalog

from .catalog import (
    GIS_CAPABILITIES,
    GIS_DATASET_GROUPS,
    GIS_DATASET_TOOL_CAPABILITIES,
)


class GisDomainPack:
    """Provide GIS discovery/catalog behavior without embedding it in Runtime."""

    domain_id = "gis"

    def action_specs(self):
        from .actions import GIS_ACTION_SPECS

        return GIS_ACTION_SPECS

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        from .actions import execute_action

        return execute_action(action_id, payload, service=context)

    def answer_composer(self) -> Any:
        from agent.answer_composer import AnswerComposer

        return AnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"spatial_data:read"}

    def preflight_tool(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        completed_results: Mapping[str, Mapping[str, Any]],
        *,
        required_datasets=(),
        require_dependency_evidence: bool = False,
    ) -> None:
        from .preflight import preflight_tool

        preflight_tool(
            tool,
            arguments,
            completed_results,
            required_datasets=required_datasets,
            require_dependency_evidence=require_dependency_evidence,
        )

    def result_registry(self) -> Any:
        from .result_registry import GIS_RESULT_REGISTRY

        return GIS_RESULT_REGISTRY

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        """Adapt the legacy GIS data probe to the generic evidence seam."""
        from agent.runtime_capabilities import runtime_capability_snapshot

        snapshot = runtime_capability_snapshot(max_files=max_files)
        keys = (
            "health_status",
            "core_health_status",
            "optional_health_status",
            "data_readiness",
            "data_evidence",
            "data_provenance",
            "relationships",
            "manifest",
            "analysis_ready",
            "config_path",
            "runtime",
            "updated_at",
            "error",
        )
        evidence = {
            key: snapshot[key]
            for key in keys
            if key in snapshot
        }
        evidence["capabilities_runtime"] = snapshot.get("capabilities", [])
        return evidence

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
            actions=domain_action_catalog(self),
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
