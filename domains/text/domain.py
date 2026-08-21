"""Non-GIS Domain Pack used as an architectural integration fixture."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION, domain_action_catalog
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
        return {
            "schema_version": DOMAIN_DISCOVERY_SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "available": True,
            "selected_capability_id": "text_summary",
            "candidate_ids": ["text_summary"],
            "candidate_count": 1,
            "signals": ["text"],
            "tasks": ["summarize"],
            "constraints": [],
        }

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
