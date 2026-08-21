"""GIS adapter for the generic Agent Runtime domain-pack seam."""

from __future__ import annotations

import os
import json
from typing import Any, Mapping

from agent.capability_catalog import capability_catalog
from agent.workflow_templates import (
    WorkflowTemplateError,
    workflow_template_catalog,
    workflow_template_context_summary,
)
from agent.domain_contract import domain_action_catalog, discovery_context

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

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Expose discovery/explicit selection metadata to the generic Runtime."""
        del request_facts
        context = discovery_context(discovery, domain_id=self.domain_id)
        return {
            "source": "explicit_workflow" if workflow and workflow.get("template_id") else "domain_discovery",
            "selected_by": "user" if workflow and workflow.get("template_id") else "domain",
            "selected_capability_id": context.get("selected_capability_id"),
            "candidate_ids": list(context.get("candidate_ids") or [])[:8],
            "candidate_count": context.get("candidate_count"),
        }

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize GIS workflow input inside the GIS Domain Pack."""
        from agent.workflow_templates import normalize_workflow_selection

        if not isinstance(workflow, Mapping):
            raise ValueError("workflow must be an object")
        template_id = workflow.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValueError("workflow.template_id must be a non-empty string")
        return normalize_workflow_selection(
            template_id.strip(),
            workflow.get("constraints", {}),
            workflow.get("evidence"),
        )

    def validate_workflow_plan(
        self,
        plan: Any,
        workflow: Mapping[str, Any],
    ) -> None:
        """Validate a generated plan against the GIS-owned template catalog."""
        from agent.workflow_templates import validate_workflow_plan

        if not isinstance(workflow, Mapping):
            raise WorkflowTemplateError("workflow selection is incomplete")
        template_id = workflow.get("template_id")
        constraints = workflow.get("constraints")
        evidence = workflow.get("evidence")
        if not template_id or not isinstance(constraints, Mapping):
            raise WorkflowTemplateError("workflow selection is incomplete")
        payload = {
            "template_id": template_id,
            "template_version": workflow.get("template_version"),
            "goal": plan.goal,
            "constraints": constraints,
            "evidence": evidence or [],
            "steps": [
                {
                    "id": step.id,
                    "tool": step.tool,
                    "args": step.args,
                    "depends_on": list(step.depends_on),
                }
                for step in getattr(plan, "steps", ())
            ],
            "output": dict(plan.output),
            "assumptions": list(plan.assumptions),
        }
        validate_workflow_plan(str(template_id), payload)

    def resolve_capability_selection(
        self,
        capability_id: str,
        *,
        request_facts: Any = None,
        selection: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        """Map only template-backed GIS capabilities to workflows."""
        del request_facts, selection
        aliases = {
            "constrained_buildability_screening": "constrained_buildability",
        }
        template_id = aliases.get(
            str(capability_id or "").strip(), str(capability_id or "").strip()
        )
        if template_id not in workflow_template_catalog():
            return None
        return {"template_id": template_id, "constraints": {}, "evidence": []}

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

    def validate_plan(self, plan: Any) -> None:
        """Apply the selected GIS workflow's bounded tool policy.

        Open-ended LLM planning does not always receive an explicit workflow
        selection.  When a result type maps to exactly one declared blueprint,
        keep that capability's allowlist as an execution-time policy.  This
        remains Domain-owned; generic Runtime only invokes the optional seam.
        """
        output = getattr(plan, "output", None)
        output_type = output.get("type") if isinstance(output, Mapping) else None
        if not output_type:
            return
        candidates = [
            template
            for template in workflow_template_catalog().values()
            if output_type in (template.get("result_types") or [])
            and template.get("step_blueprint")
        ]
        if len(candidates) != 1:
            return
        template = candidates[0]
        tools = [str(step.tool) for step in getattr(plan, "steps", ())]
        allowed = {str(item) for item in (template.get("allowed_tools") or [])}
        unexpected = sorted(set(tools) - allowed)
        if unexpected:
            raise WorkflowTemplateError(
                "domain workflow policy rejected tools: " + ", ".join(unexpected)
            )
        max_steps = template.get("max_steps")
        if isinstance(max_steps, int) and len(tools) > max_steps:
            raise WorkflowTemplateError(
                "domain workflow policy exceeded max steps: {} > {}".format(
                    len(tools), max_steps
                )
            )

    def plan_policy(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Describe the GIS policy selected for a plan without validating it.

        Validation remains in ``validate_plan``.  This companion seam only
        exposes enough declarative metadata for the generic Runtime to
        explain whether a policy was explicit or automatically matched.
        """
        output = getattr(plan, "output", None)
        output_type = output.get("type") if isinstance(output, Mapping) else None
        catalog = workflow_template_catalog()
        explicit_id = (
            str(workflow.get("template_id"))
            if isinstance(workflow, Mapping) and workflow.get("template_id")
            else None
        )
        candidates = [
            template
            for template in catalog.values()
            if isinstance(template, Mapping)
            and output_type in (template.get("result_types") or [])
            and template.get("step_blueprint")
        ]
        selected = catalog.get(explicit_id) if explicit_id else None
        source = "explicit_workflow" if selected is not None else "domain_auto_match"
        if selected is None and len(candidates) == 1:
            selected = candidates[0]
        candidate_ids = [
            str(item.get("id"))
            for item in candidates[:8]
            if isinstance(item, Mapping) and item.get("id")
        ]
        if not isinstance(selected, Mapping):
            return {
                "schema_version": "spatial-agent.plan-policy.v1",
                "available": False,
                "domain_id": self.domain_id,
                "source": "none",
                "candidate_policy_ids": [
                    "gis.workflow." + item for item in candidate_ids
                ],
                "reason_code": "workflow_policy_unavailable",
            }
        template_id = str(selected.get("id"))
        return {
            "schema_version": "spatial-agent.plan-policy.v1",
            "available": True,
            "domain_id": self.domain_id,
            "policy_id": "gis.workflow." + template_id,
            "source": source,
            "selected_by": "user" if explicit_id else "domain",
            "workflow_template_id": template_id,
            "workflow_template_version": str(selected.get("version") or "1.0.0"),
            "allowed_tools": [str(item) for item in (selected.get("allowed_tools") or [])[:24]],
            "max_steps": selected.get("max_steps"),
            "result_types": [str(item) for item in (selected.get("result_types") or [])[:8]],
            "required_constraints": [
                str(item) for item in (selected.get("required_constraints") or [])[:16]
            ],
            "candidate_policy_ids": [
                "gis.workflow." + item for item in candidate_ids
            ],
        }

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        from .request_understanding import GIS_REQUEST_UNDERSTANDING_GUIDANCE

        return GIS_REQUEST_UNDERSTANDING_GUIDANCE

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        from .intent import clarification_details

        return clarification_details(request)

    def rule_planner(self) -> Any:
        # Kept lazy so importing the domain catalog does not initialize the
        # Planner or spatial backend graph.
        from .planner import RuleBasedPlanner

        return RuleBasedPlanner()


GIS_DOMAIN_PACK = GisDomainPack()
