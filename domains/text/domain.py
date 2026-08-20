"""Non-GIS Domain Pack used as an architectural integration fixture."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domain_contract import DOMAIN_DISCOVERY_SCHEMA_VERSION, domain_action_catalog
from agent.request_model import REQUEST_FACTS_SCHEMA_VERSION, RequestFacts
from agent.capability_catalog import capability_catalog
from agent.result_registry import ResultContractRegistry, ResultTypeSpec

from .catalog import (
    TEXT_CAPABILITIES,
    TEXT_DATASET_GROUPS,
    TEXT_DATASET_TOOL_CAPABILITIES,
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

    def evidence_provider(self) -> Any:
        from .evidence import TEXT_EVIDENCE_PROVIDER

        return TEXT_EVIDENCE_PROVIDER

    def result_registry(self) -> ResultContractRegistry:
        return ResultContractRegistry(
            {
                "text_summary_result": ResultTypeSpec(
                    title="文本摘要",
                    panels=("generic",),
                ),
            },
            fallback_title="运行结果",
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


TEXT_DOMAIN_PACK = TextDomainPack()
