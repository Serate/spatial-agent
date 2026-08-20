"""GIS adapter for the generic Agent Runtime domain-pack seam."""

from __future__ import annotations

import os
import json
from typing import Any, Mapping

from agent.capability_catalog import capability_catalog
from agent.workflow_templates import workflow_template_catalog, workflow_template_context_summary
from agent.domain_contract import domain_action_catalog

from .catalog import (
    GIS_CAPABILITIES,
    GIS_DATASET_GROUPS,
    GIS_DATASET_TOOL_CAPABILITIES,
)
from .evidence import GIS_EVIDENCE_PROVIDER


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
        from .composer import AnswerComposer

        return AnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"spatial_data:read"}

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        """Build the GIS provider behind the generic Runtime Factory seam."""
        from pathlib import Path

        from agent.dataset_catalog import DatasetCatalog
        from agent.spatial_backend import (
            HybridSpatialBackend,
            InMemorySpatialBackend,
            SpatialToolAdapter,
        )
        from agent.tool_provider import NativeToolProvider

        project_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        if backend_name == "local":
            catalog_path = os.environ.get(
                "SPATIAL_AGENT_DATASET_CONFIG",
                str(project_root / "config" / "datasets.local.example.json"),
            )
            catalog = DatasetCatalog.from_json(catalog_path)
            adapter = SpatialToolAdapter(HybridSpatialBackend(catalog))
        else:
            adapter = SpatialToolAdapter(InMemorySpatialBackend())
        return NativeToolProvider.from_json(
            str(project_root / "tools" / "schema" / "tool-definitions.json"),
            adapter,
        )

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        """Describe the provider without opening a GIS backend or data volume."""
        from pathlib import Path

        project_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        path = project_root / "tools" / "schema" / "tool-definitions.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            tools = payload.get("tools") if isinstance(payload, Mapping) else []
            tool_count = len(tools) if isinstance(tools, list) else 0
        except (OSError, ValueError, TypeError):
            tool_count = 0
        return {"id": "native", "tool_count": tool_count}

    def evidence_provider(self) -> Any:
        """Return the GIS-owned provider for versioned evidence projections."""
        return GIS_EVIDENCE_PROVIDER

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
        snapshot = GIS_EVIDENCE_PROVIDER.runtime_snapshot(max_files=max_files)
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

    def release_evidence(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Expose GIS publication checks through the Domain Pack seam."""
        snapshot = GIS_EVIDENCE_PROVIDER.release_snapshot(
            config_path=config_path,
            max_files=max_files,
        )
        result = dict(snapshot) if isinstance(snapshot, Mapping) else {}
        result.setdefault("domain_id", self.domain_id)
        return result

    def extract_request_facts(self, request: str) -> Any:
        from .request_model import parse_spatial_request

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
        from .routing import GisCapabilityRouter

        return GisCapabilityRouter().discover(request, request_facts)

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

    def planner_guidance(self) -> Mapping[str, Any]:
        from .planner_guidance import GIS_PLANNER_GUIDANCE

        return GIS_PLANNER_GUIDANCE

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        from .request_understanding import GIS_REQUEST_UNDERSTANDING_GUIDANCE

        return GIS_REQUEST_UNDERSTANDING_GUIDANCE

    def rule_planner(self) -> Any:
        # Kept lazy so importing the domain catalog does not initialize the
        # Planner or spatial backend graph.
        from .planner import RuleBasedPlanner

        return RuleBasedPlanner()


GIS_DOMAIN_PACK = GisDomainPack()
