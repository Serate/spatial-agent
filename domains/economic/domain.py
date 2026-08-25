"""Economic Domain Pack backed by the shared Runtime seams."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from agent.domain_contract import domain_action_catalog, discovery_context
from agent.domain_catalog import DomainCatalogSpec, build_domain_catalog, workflow_catalog as copy_workflow_catalog
from agent.errors import ToolError
from agent.request_model import RequestFacts
from agent.result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec
from agent.workflow_templates import (
    WorkflowTemplateError,
    normalize_workflow_selection,
    validate_workflow_plan,
    workflow_request_hint,
    workflow_template_context_summary,
)

from .catalog import (
    ECONOMIC_CAPABILITIES,
    ECONOMIC_DATASET,
    ECONOMIC_DATASET_GROUPS,
    ECONOMIC_DATASET_TOOL_CAPABILITIES,
    economic_tool_definitions,
)
from .composer import EconomicAnswerComposer
from .evidence import ECONOMIC_EVIDENCE_PROVIDER
from .planner import EconomicRulePlanner
from .provider import DEFAULT_DATA_FILENAME, EconomicToolProvider
from .request_understanding import ECONOMIC_REQUEST_UNDERSTANDING_GUIDANCE
from .views import build_views
from .workflow_templates import KNOWN_RESULT_TYPES, KNOWN_TOOL_NAMES, workflow_template_catalog


ECONOMIC_CATALOG_SPEC = DomainCatalogSpec(
    domain_id="economic",
    capabilities=tuple(ECONOMIC_CAPABILITIES),
    dataset_tool_capabilities=ECONOMIC_DATASET_TOOL_CAPABILITIES,
    dataset_groups=ECONOMIC_DATASET_GROUPS,
    workflow_templates=workflow_template_catalog(),
    known_tool_names=tuple(KNOWN_TOOL_NAMES),
    known_result_types=tuple(KNOWN_RESULT_TYPES),
)


class EconomicDomainPack:
    domain_id = "economic"

    def action_specs(self):
        return ()

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        del action_id, payload, context
        raise ToolError("economic domain action is not available", code="economic_action_unavailable", retryable=False)

    def answer_composer(self) -> Any:
        return EconomicAnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"economic_data:read"}

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        del backend_name
        from agent.tool_provider import NativeToolProvider

        default_root = Path(root) if root else None
        return NativeToolProvider(
            economic_tool_definitions(),
            EconomicToolProvider(default_root=default_root),
        )

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        del backend_name, root
        return {"id": "economic-source-bound", "tool_count": len(KNOWN_TOOL_NAMES), "default_data": DEFAULT_DATA_FILENAME}

    def evidence_provider(self) -> Any:
        return ECONOMIC_EVIDENCE_PROVIDER

    def result_registry(self) -> ResultContractRegistry:
        return ResultContractRegistry(
            {
                "economic_catalog_result": ResultTypeSpec(title="经济指标目录", panels=("generic",), view_specs=(ViewSpec("generic", "table", "可用经济指标"),), data_kinds=("metrics",)),
                "economic_metrics_result": ResultTypeSpec(title="经济指标", panels=("generic",), view_specs=(ViewSpec("generic", "metrics", "经济指标"),), data_kinds=("metrics",)),
                "economic_timeseries_result": ResultTypeSpec(title="经济趋势", panels=("generic",), view_specs=(ViewSpec("generic", "chart", "经济趋势"),), data_kinds=("timeseries", "metrics")),
                "economic_comparison_result": ResultTypeSpec(title="区域经济比较", panels=("generic",), view_specs=(ViewSpec("generic", "chart", "区域比较"),), data_kinds=("composite", "metrics")),
                "economic_evidence_result": ResultTypeSpec(title="经济来源证据", panels=("generic",), view_specs=(ViewSpec("generic", "table", "来源证据"),), data_kinds=("document_evidence",)),
            },
            fallback_title="经济分析结果",
            view_builder=build_views,
        )

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().runtime_snapshot(max_files=max_files)

    def release_evidence(self, *, config_path: str | None = None, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().release_snapshot(config_path=config_path, max_files=max_files)

    def extract_request_facts(self, request: str) -> RequestFacts:
        text = str(request or "").strip()
        task = (
            "discover"
            if any(term in text for term in ("有哪些经济指标", "经济指标目录", "经济数据目录"))
            else "evidence"
            if any(term in text for term in ("来源", "出处", "统计口径"))
            else "trend"
            if any(term in text for term in ("趋势", "变化", "增长", "历年"))
            else "compare"
            if any(term in text for term in ("比较", "对比", "差异"))
            else "latest"
        )
        from .planner import _indicator_id, _period_type, _regions

        indicator = _indicator_id(text)
        regions = _regions(text)
        period_type = _period_type(text)
        constraints = {"dataset": ECONOMIC_DATASET, "indicator": indicator, "regions": regions, "period_type": period_type}
        return RequestFacts(text=text, admin_name=None, tasks=(task,), datasets=(ECONOMIC_DATASET,), constraints=constraints, evidence=("answer", "provenance", "source_evidence"), entities={"indicator": indicator, "regions": regions, "period_type": period_type})

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        return build_domain_catalog(
            ECONOMIC_CATALOG_SPEC,
            environment=environment,
            actions=domain_action_catalog(self),
        )

    def discover(self, request: str, request_facts: Any) -> Mapping[str, Any]:
        from agent.capability_discovery import discover_from_catalog

        return discover_from_catalog(request, request_facts, self.capability_catalog(environment="local").get("capabilities", ()))

    def select_workflow(self, discovery: Any, request_facts: Any, *, workflow: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        context = discovery_context(discovery, domain_id=self.domain_id)
        if isinstance(workflow, Mapping) and workflow.get("template_id"):
            normalized = self.normalize_workflow(workflow)
            return {"source": "explicit_workflow", "selected_by": "user", **normalized}
        facts = request_facts if isinstance(request_facts, Mapping) else request_facts.as_dict()
        task = str((facts.get("tasks") or ["latest"])[0])
        template_id = "economic_discovery" if task == "discover" else "economic_evidence" if task == "evidence" else "economic_" + task
        constraints = dict(facts.get("constraints") or {})
        constraints.setdefault("dataset", ECONOMIC_DATASET)
        if template_id != "economic_discovery":
            constraints.setdefault("period_type", "annual")
        missing = [name for name in ("indicator", "regions") if not constraints.get(name)] if template_id != "economic_discovery" else []
        return {"source": "domain_discovery", "selected_by": "domain", "selected_capability_id": context.get("selected_capability_id") or template_id, "candidate_ids": list(context.get("candidate_ids") or [template_id])[:8], "candidate_count": context.get("candidate_count", 1), "workflow_template_id": template_id, "workflow_template_version": "1.0.0", "constraints": constraints, "missing_fields": missing}

    def resolve_capability_selection(self, capability_id: str, *, request_facts: Any = None, selection: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        del selection
        if capability_id not in self.workflow_template_catalog():
            return None
        facts = request_facts if isinstance(request_facts, Mapping) else (request_facts.as_dict() if request_facts else {})
        constraints = dict(facts.get("constraints") or {})
        constraints.setdefault("dataset", ECONOMIC_DATASET)
        constraints.setdefault("period_type", "annual")
        return {"template_id": capability_id, "constraints": constraints, "evidence": ["summary", "provenance", "trace"]}

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(workflow, Mapping) or not workflow.get("template_id"):
            raise ValueError("economic workflow.template_id is required")
        return normalize_workflow_selection(str(workflow["template_id"]), dict(workflow.get("constraints") or {}), workflow.get("evidence") or [], catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES)

    def validate_workflow_plan(self, plan: Any, workflow: Mapping[str, Any]) -> None:
        if not isinstance(workflow, Mapping) or not workflow.get("template_id"):
            raise WorkflowTemplateError("economic workflow selection is incomplete")
        validate_workflow_plan(str(workflow["template_id"]), {"template_id": workflow["template_id"], "constraints": workflow.get("constraints") or {}, "steps": [{"id": step.id, "tool": step.tool, "args": step.args, "depends_on": list(step.depends_on)} for step in plan.steps], "output": dict(plan.output or {})}, catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES)

    def validate_plan(self, plan: Any) -> None:
        tools = {step.tool for step in getattr(plan, "steps", ())}
        if not tools.issubset(set(KNOWN_TOOL_NAMES)):
            raise WorkflowTemplateError("economic workflow selected an unknown tool")

    def workflow_template_context(self, *, include_arg_shape: bool = False, compact: bool = True) -> Mapping[str, Any]:
        return workflow_template_context_summary(catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES, include_arg_shape=include_arg_shape, compact=compact)

    def workflow_template_catalog(self) -> Mapping[str, Mapping[str, Any]]:
        return copy_workflow_catalog(ECONOMIC_CATALOG_SPEC)

    def planner_request_hint(self, request: str, workflow: Mapping[str, Any] | None = None) -> str:
        return workflow_request_hint(request, workflow)

    def planner_guidance(self) -> Mapping[str, Any]:
        from .planner_guidance import ECONOMIC_PLANNER_GUIDANCE

        return ECONOMIC_PLANNER_GUIDANCE

    def plan_policy(self, plan: Any, *, workflow: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        template_id = str((workflow or {}).get("template_id") or "")
        template = self.workflow_template_catalog().get(template_id)
        return {"schema_version": "spatial-agent.plan-policy.v1", "available": bool(template), "domain_id": self.domain_id, "policy_id": "economic.workflow." + template_id if template_id else None, "source": "domain", "selected_by": "domain", "workflow_template_id": template_id or None, "workflow_template_version": template.get("version") if template else None, "allowed_tools": list(template.get("allowed_tools") or []) if template else [], "max_steps": template.get("max_steps") if template else None, "result_types": list(template.get("result_types") or []) if template else [str((getattr(plan, "output", {}) or {}).get("type"))]}

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        return ECONOMIC_REQUEST_UNDERSTANDING_GUIDANCE

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        return {"missing_fields": ["indicator", "regions"], "next_actions": ["查询经济指标目录", "补充指标和统计区域"]} if request else {}

    def evidence_action_guidance(self, selection: Mapping[str, Any], *, request_facts: Any = None) -> Mapping[str, Any]:
        del request_facts
        missing = selection.get("missing_fields") if isinstance(selection, Mapping) else []
        return {"schema_version": "spatial-agent.evidence-action-guidance.v1", "state": "degraded" if missing else "ready", "reason_code": "economic_facts_missing" if missing else "economic_ready", "recommended_actions": ["provide_facts"] if missing else ["preview"], "source": "domain"}

    def rule_planner(self) -> Any:
        return EconomicRulePlanner()


ECONOMIC_DOMAIN_PACK = EconomicDomainPack()
