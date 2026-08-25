"""Indicator Domain Pack using the shared Runtime/Planner/ToolRegistry seams."""

from __future__ import annotations

import re
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
    INDICATOR_CAPABILITIES,
    INDICATOR_DATASET_GROUPS,
    INDICATOR_DATASET_TOOL_CAPABILITIES,
    indicator_tool_definitions,
)
from .evidence import INDICATOR_EVIDENCE_PROVIDER
from .provider import IndicatorToolProvider
from .workflow_templates import KNOWN_RESULT_TYPES, KNOWN_TOOL_NAMES, workflow_template_catalog


INDICATOR_CATALOG_SPEC = DomainCatalogSpec(
    domain_id="indicators",
    capabilities=tuple(INDICATOR_CAPABILITIES),
    dataset_tool_capabilities=INDICATOR_DATASET_TOOL_CAPABILITIES,
    dataset_groups=INDICATOR_DATASET_GROUPS,
    workflow_templates=workflow_template_catalog(),
    known_tool_names=tuple(KNOWN_TOOL_NAMES),
    known_result_types=tuple(KNOWN_RESULT_TYPES),
)


class IndicatorsDomainPack:
    domain_id = "indicators"

    def action_specs(self):
        return ()

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        del action_id, payload, context
        raise ToolError("indicator domain action is not available", code="indicator_action_unavailable", retryable=False)

    def answer_composer(self) -> Any:
        from .composer import IndicatorsAnswerComposer

        return IndicatorsAnswerComposer()

    def default_permissions(self) -> set[str]:
        return {"indicator_data:read"}

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> Any:
        del backend_name, root
        from agent.tool_provider import NativeToolProvider

        return NativeToolProvider(indicator_tool_definitions(), IndicatorToolProvider())

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        del backend_name, root
        return {"id": "indicator-native", "tool_count": len(KNOWN_TOOL_NAMES)}

    def evidence_provider(self) -> Any:
        return INDICATOR_EVIDENCE_PROVIDER

    def result_registry(self) -> ResultContractRegistry:
        from .views import build_views

        return ResultContractRegistry({
            "indicator_catalog_result": ResultTypeSpec(title="指标目录", panels=("generic",), view_specs=(ViewSpec("generic", "table", "可用指标"),), data_kinds=("metrics",)),
            "indicator_metrics_result": ResultTypeSpec(title="指标统计", panels=("generic",), view_specs=(ViewSpec("generic", "metrics", "指标统计"),), data_kinds=("metrics",)),
            "indicator_timeseries_result": ResultTypeSpec(title="指标趋势", panels=("generic",), view_specs=(ViewSpec("generic", "chart", "指标趋势"),), data_kinds=("timeseries", "metrics")),
            "indicator_comparison_result": ResultTypeSpec(title="区域指标比较", panels=("generic",), view_specs=(ViewSpec("generic", "chart", "区域比较"),), data_kinds=("composite", "metrics")),
            "record_analysis_result": ResultTypeSpec(title="记录分析结果", panels=("generic",), view_specs=(ViewSpec("generic", "table", "结构化记录分析"),), data_kinds=("metrics", "timeseries", "composite")),
        }, fallback_title="指标结果", view_builder=build_views)

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().runtime_snapshot(max_files=max_files)

    def release_evidence(self, *, config_path: str | None = None, max_files: int = 10) -> Mapping[str, Any]:
        return self.evidence_provider().release_snapshot(config_path=config_path, max_files=max_files)

    def extract_request_facts(self, request: str) -> RequestFacts:
        text = str(request or "").strip()
        tasks = ("trend",) if any(term in text for term in ("趋势", "变化", "增长", "历年")) else ("compare",) if any(term in text for term in ("比较", "对比", "差异")) else ("discover",) if any(term in text for term in ("有哪些指标", "指标目录", "可用指标")) else ("latest",)
        regions = _regions(text)
        indicator = _indicator_id(text)
        return RequestFacts(text=text, admin_name=None, tasks=tasks, datasets=("regional_indicators",), constraints={"indicator": indicator, "regions": regions}, evidence=("answer", "provenance"), entities={"indicator": indicator, "regions": regions})

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        return build_domain_catalog(
            INDICATOR_CATALOG_SPEC,
            environment=environment,
            actions=domain_action_catalog(self),
        )

    def discover(self, request: str, request_facts: Any) -> Mapping[str, Any]:
        from agent.capability_discovery import discover_from_catalog

        return discover_from_catalog(request, request_facts, self.capability_catalog(environment="memory").get("capabilities", ()))

    def select_workflow(self, discovery: Any, request_facts: Any, *, workflow: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        context = discovery_context(discovery, domain_id=self.domain_id)
        if isinstance(workflow, Mapping) and workflow.get("template_id"):
            normalized = self.normalize_workflow(workflow)
            return {"source": "explicit_workflow", "selected_by": "user", **normalized}
        facts = request_facts if isinstance(request_facts, Mapping) else request_facts.as_dict()
        task = str((facts.get("tasks") or ["latest"])[0])
        template_id = "indicator_discovery" if task == "discover" else "indicator_" + task
        constraints = dict(facts.get("constraints") or {})
        constraints.setdefault("dataset", "regional_indicators")
        missing = [name for name in ("indicator", "regions") if not constraints.get(name)] if template_id != "indicator_discovery" else []
        return {"source": "domain_discovery", "selected_by": "domain", "selected_capability_id": context.get("selected_capability_id") or template_id, "candidate_ids": list(context.get("candidate_ids") or [template_id])[:8], "candidate_count": context.get("candidate_count", 1), "workflow_template_id": template_id, "workflow_template_version": "1.0.0", "constraints": constraints, "missing_fields": missing}

    def resolve_capability_selection(self, capability_id: str, *, request_facts: Any = None, selection: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        del selection
        if capability_id not in self.workflow_template_catalog():
            return None
        facts = request_facts if isinstance(request_facts, Mapping) else (request_facts.as_dict() if request_facts else {})
        constraints = dict(facts.get("constraints") or {})
        constraints.setdefault("dataset", "regional_indicators")
        return {"template_id": capability_id, "constraints": constraints, "evidence": ["summary", "provenance", "trace"]}

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(workflow, Mapping) or not workflow.get("template_id"):
            raise ValueError("indicator workflow.template_id is required")
        return normalize_workflow_selection(str(workflow["template_id"]), dict(workflow.get("constraints") or {}), workflow.get("evidence") or [], catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES)

    def validate_workflow_plan(self, plan: Any, workflow: Mapping[str, Any]) -> None:
        if not isinstance(workflow, Mapping) or not workflow.get("template_id"):
            raise WorkflowTemplateError("indicator workflow selection is incomplete")
        validate_workflow_plan(str(workflow["template_id"]), {"template_id": workflow["template_id"], "constraints": workflow.get("constraints") or {}, "steps": [{"id": step.id, "tool": step.tool, "args": step.args, "depends_on": list(step.depends_on)} for step in plan.steps], "output": dict(plan.output or {})}, catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES)

    def validate_plan(self, plan: Any) -> None:
        tools = {step.tool for step in getattr(plan, "steps", ())}
        if not tools.issubset(set(KNOWN_TOOL_NAMES)):
            raise WorkflowTemplateError("indicator workflow selected an unknown tool")

    def workflow_template_context(self, *, include_arg_shape: bool = False, compact: bool = True) -> Mapping[str, Any]:
        return workflow_template_context_summary(catalog=self.workflow_template_catalog(), known_tools=KNOWN_TOOL_NAMES, known_result_types=KNOWN_RESULT_TYPES, include_arg_shape=include_arg_shape, compact=compact)

    def workflow_template_catalog(self) -> Mapping[str, Mapping[str, Any]]:
        return copy_workflow_catalog(INDICATOR_CATALOG_SPEC)

    def planner_request_hint(self, request: str, workflow: Mapping[str, Any] | None = None) -> str:
        return workflow_request_hint(request, workflow)

    def planner_guidance(self) -> Mapping[str, Any]:
        from .planner_guidance import INDICATOR_PLANNER_GUIDANCE

        return INDICATOR_PLANNER_GUIDANCE

    def plan_policy(self, plan: Any, *, workflow: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        template_id = str((workflow or {}).get("template_id") or "")
        template = self.workflow_template_catalog().get(template_id)
        return {"schema_version": "spatial-agent.plan-policy.v1", "available": bool(template), "domain_id": self.domain_id, "policy_id": "indicators.workflow." + template_id if template_id else None, "source": "domain", "selected_by": "domain", "workflow_template_id": template_id or None, "workflow_template_version": template.get("version") if template else None, "allowed_tools": list(template.get("allowed_tools") or []) if template else [], "max_steps": template.get("max_steps") if template else None, "result_types": list(template.get("result_types") or []) if template else [str((getattr(plan, "output", {}) or {}).get("type"))]}

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        from .request_understanding import INDICATOR_REQUEST_UNDERSTANDING_GUIDANCE

        return INDICATOR_REQUEST_UNDERSTANDING_GUIDANCE

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        return {"missing_fields": ["indicator", "regions"], "next_actions": ["补充指标 ID", "补充区域"]} if request else {}

    def evidence_action_guidance(self, selection: Mapping[str, Any], *, request_facts: Any = None) -> Mapping[str, Any]:
        del request_facts
        missing = selection.get("missing_fields") if isinstance(selection, Mapping) else []
        return {"schema_version": "spatial-agent.evidence-action-guidance.v1", "state": "degraded" if missing else "ready", "reason_code": "indicator_facts_missing" if missing else "indicator_ready", "recommended_actions": ["provide_facts"] if missing else ["preview"], "source": "domain"}

    def rule_planner(self) -> Any:
        from .planner import IndicatorsRulePlanner

        return IndicatorsRulePlanner()


def _indicator_id(text: str) -> str:
    marked = re.search(r"指标(?:为|是|[:：])?\s*([A-Za-z0-9_.-]+)", str(text))
    if marked:
        return marked.group(1)[:96]
    for token in str(text).replace("：", " ").replace(":", " ").split():
        if token.startswith("demo_") or token.startswith("indicator_"):
            return token.strip("，,。；;")[:96]
    return ""


def _regions(text: str) -> list[str]:
    normalized = re.sub(r"(?:的(?:变化趋势|趋势分析|趋势|变化|增长|比较|对比|差异|最新|当前|概况|情况|分析|如何)|变化趋势|趋势分析|趋势|变化|增长|比较|对比|差异|最新|当前|概况|情况|分析|如何)\s*$", "", str(text))
    normalized = re.sub(r"(?:以及|和|与|、|及)(?=(?:区域|[\u4e00-\u9fffA-Za-z0-9]))", " ", normalized)
    matches = re.findall(r"区域[^和与、,，\s]+|[\u4e00-\u9fffA-Za-z0-9]+?(?:市|区|县)", normalized)
    return list(dict.fromkeys(item[:96] for item in matches))[:16]


INDICATORS_DOMAIN_PACK = IndicatorsDomainPack()
