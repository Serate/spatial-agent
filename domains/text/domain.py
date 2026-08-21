"""Non-GIS Domain Pack used as an architectural integration fixture."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import domain_action_catalog, discovery_context
from agent.request_model import RequestFacts
from agent.capability_catalog import capability_catalog
from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec

from .catalog import (
    TEXT_CAPABILITIES,
    TEXT_DATASET_GROUPS,
    TEXT_DATASET_TOOL_CAPABILITIES,
    TEXT_TOOL_DEFINITIONS,
)


class TextDomainPack:
    domain_id = "text"

    def action_specs(self):
        from .actions import TEXT_ACTION_SPECS

        return TEXT_ACTION_SPECS

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        from .actions import execute_action

        return execute_action(action_id, payload, service=context)

    def answer_composer(self) -> Any:
        from .composer import TextAnswerComposer

        return TextAnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"text_data:read"}

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        """Return the text provider through the shared Runtime Factory seam."""
        from .provider import TextToolProvider

        return TextToolProvider()

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        return {
            "id": "text-native",
            "tool_count": len(TEXT_TOOL_DEFINITIONS),
        }

    def evidence_provider(self) -> Any:
        from .evidence import TEXT_EVIDENCE_PROVIDER

        return TEXT_EVIDENCE_PROVIDER

    def result_registry(self) -> ResultContractRegistry:
        from .views import build_views

        return ResultContractRegistry(
            {
                "text_summary_result": ResultTypeSpec(
                    title="文本摘要",
                    panels=("generic",),
                    view_specs=(ViewSpec("generic", "generic", "摘要概览"),),
                ),
            },
            fallback_title="运行结果",
            view_builder=build_views,
        )

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().runtime_snapshot(max_files=max_files)

    def release_evidence(
        self,
        *,
        config_path: str | None = None,
        max_files: int = 10,
    ) -> Mapping[str, Any]:
        """Text has no configured GIS volume or release manifest."""
        return self.evidence_provider().release_snapshot(
            config_path=config_path,
            max_files=max_files,
        )

    def extract_request_facts(self, request: str) -> RequestFacts:
        return RequestFacts(
            text=str(request or "").strip(),
            admin_name=None,
            tasks=("summarize",),
            datasets=("documents",),
            constraints={},
            evidence=("answer",),
        )

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        return capability_catalog(
            environment=environment,
            domain_id=self.domain_id,
            capability_definitions=TEXT_CAPABILITIES,
            dataset_tool_capabilities=TEXT_DATASET_TOOL_CAPABILITIES,
            dataset_groups=TEXT_DATASET_GROUPS,
            analysis_ready_capability_ids=(),
            workflow_templates={},
            actions=domain_action_catalog(self),
        )

    def discover(self, request: str, request_facts: Any) -> Mapping[str, Any]:
        from agent.capability_discovery import discover_from_catalog

        catalog = self.capability_catalog(environment="memory")
        return discover_from_catalog(
            request,
            request_facts,
            catalog.get("capabilities", ()),
        )

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Expose text selection metadata without importing spatial policy."""
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
        """Normalize a text workflow without importing GIS templates."""
        if not isinstance(workflow, Mapping):
            raise ValueError("workflow must be an object")
        template_id = str(workflow.get("template_id") or "").strip()
        if not template_id:
            raise ValueError("workflow.template_id must be a non-empty string")
        constraints = workflow.get("constraints", {})
        if not isinstance(constraints, Mapping):
            raise ValueError("workflow.constraints must be an object")
        evidence = workflow.get("evidence")
        if evidence is None:
            evidence = []
        if not isinstance(evidence, (list, tuple)):
            raise ValueError("workflow.evidence must be an array")
        return {
            "template_id": template_id[:96],
            "template_version": "1.0.0",
            "constraints": dict(constraints),
            "evidence": [str(item)[:96] for item in evidence[:16]],
        }

    def validate_workflow_plan(self, plan: Any, workflow: Mapping[str, Any]) -> None:
        """Validate only the public Text workflow shape."""
        del plan
        if not isinstance(workflow, Mapping) or not workflow.get("template_id"):
            raise ValueError("text workflow selection is incomplete")

    def resolve_capability_selection(
        self,
        capability_id: str,
        *,
        request_facts: Any = None,
        selection: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        del request_facts, selection
        if str(capability_id or "").strip() != "text_summary":
            return None
        return {"template_id": "text_summary", "constraints": {}, "evidence": []}

    def workflow_template_context(
        self,
        *,
        include_arg_shape: bool = False,
        compact: bool = True,
    ) -> Mapping[str, Any]:
        return {}

    def planner_guidance(self) -> Mapping[str, Any]:
        from .planner_guidance import TEXT_PLANNER_GUIDANCE

        return TEXT_PLANNER_GUIDANCE

    def plan_policy(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Text has no GIS workflow policy; generic Runtime validation applies."""
        del plan, workflow
        return {
            "schema_version": "spatial-agent.plan-policy.v1",
            "available": False,
            "domain_id": self.domain_id,
            "source": "none",
            "reason_code": "no_domain_workflow_policy",
        }

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        from .request_understanding import TEXT_REQUEST_UNDERSTANDING_GUIDANCE

        return TEXT_REQUEST_UNDERSTANDING_GUIDANCE

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        """Text has no spatial clarification policy."""
        return {}

    def rule_planner(self) -> Any:
        from .planner import TextSummaryPlanner

        return TextSummaryPlanner()


TEXT_DOMAIN_PACK = TextDomainPack()
