"""Domain-neutral Runtime adapter backed by :mod:`general_capability_host`.

This adapter is the bridge between the existing AgentRuntime lifecycle and
the aggregated Host.  It owns no GIS, economic, indicator or text policy; it
only merges bounded facts/discovery and delegates typed result rendering back
to the Domain that owns a result type.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from .capability_discovery import discover_from_catalog
from .domain_contract import discovery_context
from .errors import ToolError
from .general_capability_host import GeneralCapabilityHost
from .models import AgentRunResult, TaskPlan
from .request_model import RequestFacts
from .result_registry import ResultContractRegistry, ResultTypeSpec, ViewSpec


class GeneralAnswerComposer:
    """Small, honest fallback for a Runtime without a Domain composer."""

    def compose(self, result: AgentRunResult) -> str:
        usable = [
            item
            for item in result.steps
            if isinstance(item.result, dict)
            and str(item.result.get("status") or "ready") != "unavailable"
        ]
        if usable:
            return (
                f"已完成这次请求，得到 {len(usable)} 项可用结果。"
                "详细内容和数据来源已整理在结果区域。"
            )
        if result.plan and result.plan.output.get("type") == "direct_answer":
            return "当前使用的是离线规则模式，无法生成开放式回答；请切换真实模型后重试。"
        return "请求已处理，但当前没有可展示的结果。请检查数据或工具状态后重试。"

    def compose_failure(self, result: AgentRunResult) -> str:
        if result.status.value == "NEEDS_CLARIFICATION":
            return "这次请求还缺少必要信息，请补充对象、范围或目标后继续。"
        if result.status.value == "WAITING_FOR_DECISION":
            return "这次请求需要你的确认后才能继续。"
        return "这次请求没有完成，系统已保留可恢复的执行状态；请检查提示后重试。"


class GeneralResultRegistry(ResultContractRegistry):
    """Route result views/provenance to the unique Domain owner."""

    def __init__(self, host: GeneralCapabilityHost):
        self._host = host
        specs: dict[str, ResultTypeSpec] = {}
        for raw in host.capability_catalog().get("result_types") or []:
            if not isinstance(raw, Mapping):
                continue
            result_type = str(raw.get("type") or "").strip()
            if not result_type:
                continue
            view_specs = tuple(
                ViewSpec(
                    str(item.get("id") or "generic"),
                    renderer=str(item.get("renderer") or "generic"),
                    title=str(item.get("title") or "") or None,
                    schema_version=str(item.get("schema_version") or "spatial-agent.view.v1"),
                )
                for item in (raw.get("view_specs") or [])
                if isinstance(item, Mapping)
            )
            specs[result_type] = ResultTypeSpec(
                title=str(raw.get("title") or "") or None,
                panels=tuple(str(item) for item in (raw.get("panels") or []) if str(item)),
                requires_geometry=bool(raw.get("requires_geometry")),
                view_specs=view_specs,
                data_kinds=tuple(str(item) for item in (raw.get("data_kinds") or []) if str(item)),
            )
        super().__init__(specs, fallback_title="运行结果")

    def build_views(self, result_type: str, **kwargs: Any) -> dict[str, Any]:
        owner = self._host.result_owner_for(result_type)
        pack = self._host.domain_pack_for(owner) if owner else None
        registry = pack.result_registry() if pack is not None else None
        builder = getattr(registry, "build_views", None) if registry is not None else None
        if callable(builder):
            value = builder(result_type, **kwargs)
            if isinstance(value, Mapping):
                return dict(value)
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}

    def project_provenance(
        self,
        result: Mapping[str, Any],
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        result_type = str(result.get("result_type") or "")
        owner = self._host.result_owner_for(result_type)
        pack = self._host.domain_pack_for(owner) if owner else None
        registry = pack.result_registry() if pack is not None else None
        projector = getattr(registry, "project_provenance", None) if registry is not None else None
        if callable(projector):
            value = projector(result, summary)
            if isinstance(value, Mapping):
                return dict(value)
        return dict(summary)

    def evidence_specs_for(self, result_type: str) -> list[dict[str, Any]]:
        owner = self._host.result_owner_for(result_type)
        pack = self._host.domain_pack_for(owner) if owner else None
        registry = pack.result_registry() if pack is not None else None
        reader = getattr(registry, "evidence_specs_for", None) if registry is not None else None
        if callable(reader):
            value = reader(result_type)
            return [dict(item) for item in value if isinstance(item, Mapping)][:12]
        return []


class GeneralRuntimePack:
    """Adapter implementing the Domain Pack interface for open requests."""

    domain_id = "general"
    # The aggregate Host publishes one complete result registry.  Open ReAct
    # therefore rejects model-invented output labels before any tool runs.
    strict_result_contract = True

    def __init__(self, host: GeneralCapabilityHost):
        self._host = host
        self._result_registry = GeneralResultRegistry(host)

    @property
    def host(self) -> GeneralCapabilityHost:
        return self._host

    def action_specs(self):
        return ()

    def execute_action(self, action_id: str, payload: Mapping[str, Any], *, context: Any = None):
        del action_id, payload, context
        raise ToolError("general Domain actions are not available", code="action_unavailable")

    def answer_composer(self) -> GeneralAnswerComposer:
        return GeneralAnswerComposer()

    def default_permissions(self) -> set[str]:
        return set(self._host.capability_catalog().get("permissions") or ())

    def tool_provider(self, *, backend_name: str = "memory", root: Any = None) -> GeneralCapabilityHost:
        del backend_name, root
        return self._host

    def tool_provider_info(self, *, backend_name: str = "memory", root: Any = None) -> Mapping[str, Any]:
        del backend_name, root
        return self._host.provider_info()

    def preflight_tool(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        completed_results: Mapping[str, Mapping[str, Any]],
        *,
        required_datasets: Iterable[str] = (),
        require_dependency_evidence: bool = False,
    ) -> Any:
        return self._host.preflight_tool(
            tool,
            arguments,
            completed_results,
            required_datasets=required_datasets,
            require_dependency_evidence=require_dependency_evidence,
        )

    def result_registry(self) -> GeneralResultRegistry:
        return self._result_registry

    def evidence_provider(self) -> Any:
        return None

    def runtime_evidence(self, *, max_files: int = 10) -> Mapping[str, Any]:
        domains = []
        readiness = []
        for domain_id in self._host.domain_ids:
            pack = self._host.domain_pack_for(domain_id)
            if pack is None:
                domains.append({"domain_id": domain_id, "status": "unavailable"})
                readiness.append("unavailable")
                continue
            reader = getattr(pack, "runtime_evidence", None)
            try:
                value = reader(max_files=max_files) if callable(reader) else {}
            except Exception:
                value = {"health_status": "unavailable", "data_readiness": "unavailable"}
            safe = _safe_evidence(value)
            status = str(safe.get("health_status") or safe.get("status") or "unknown")
            domains.append({"domain_id": domain_id, "status": status, "data_readiness": safe.get("data_readiness")})
            readiness.append(str(safe.get("data_readiness") or status))
        return {
            "health_status": self._host.health().get("status", "unknown"),
            "data_readiness": _aggregate_readiness(readiness),
            "domains": domains,
            "capabilities_runtime": [],
        }

    def release_evidence(self, *, config_path: str | None = None, max_files: int = 10) -> Mapping[str, Any]:
        domains = []
        statuses = []
        for domain_id in self._host.domain_ids:
            pack = self._host.domain_pack_for(domain_id)
            reader = getattr(pack, "release_evidence", None) if pack is not None else None
            try:
                value = reader(config_path=config_path, max_files=max_files) if callable(reader) else {}
            except Exception:
                value = {"status": "unavailable"}
            safe = _safe_evidence(value)
            status = str(safe.get("status") or "unknown")
            statuses.append(status)
            domains.append({"domain_id": domain_id, "status": status})
        return {
            "schema_version": "spatial-agent.general-release-evidence.v1",
            "domain_id": self.domain_id,
            "status": _aggregate_readiness(statuses),
            "domains": domains,
        }

    def extract_request_facts(self, request: str) -> RequestFacts:
        facts = []
        for domain_id in self._host.domain_ids:
            pack = self._host.domain_pack_for(domain_id)
            reader = getattr(pack, "extract_request_facts", None) if pack is not None else None
            if not callable(reader):
                continue
            try:
                value = reader(str(request or ""))
            except Exception:
                continue
            if isinstance(value, RequestFacts):
                facts.append((domain_id, value))
        return _merge_facts(str(request or ""), facts)

    def analysis_intent(self, request: str, request_facts: Any) -> Mapping[str, Any] | None:
        del request, request_facts
        return None

    def capability_catalog(self, *, environment: str = "unknown") -> Mapping[str, Any]:
        value = self._host.capability_catalog()
        result = deepcopy(value)
        result["environment"] = str(environment or self._host.backend_name)[:80]
        return result

    def discover(self, request: str, request_facts: Any) -> Any:
        catalog = self.capability_catalog(environment=self._host.backend_name)
        result = discover_from_catalog(
            str(request or ""),
            request_facts,
            catalog.get("capabilities") or [],
        )
        value = dict(discovery_context(result, domain_id=self.domain_id))
        value["source"] = "general"
        return value

    def select_workflow(
        self,
        discovery: Any,
        request_facts: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        del request_facts
        if isinstance(workflow, Mapping) and workflow.get("template_id"):
            return {"source": "explicit_workflow", "selected_by": "user", **dict(workflow)}
        context = discovery_context(discovery, domain_id=self.domain_id)
        candidates = [str(item) for item in (context.get("candidate_ids") or []) if str(item).strip()][:16]
        selected = str(context.get("selected_capability_id") or "").strip() or None
        # Open ReAct owns the final selection.  Keeping this state selected
        # prevents lexical ambiguity from becoming a hard workflow gate.
        return {
            "source": "domain_discovery",
            "selected_by": "model",
            "state": "selected" if candidates else "unavailable",
            "selected_capability_id": selected,
            "candidate_ids": candidates,
            "candidate_count": len(candidates),
        }

    def resolve_capability_selection(self, capability_id: str, *, request_facts: Any = None, selection: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        del selection
        catalog = self._host.capability_catalog()
        owner = next(
            (
                str(item.get("owner_domain_id"))
                for item in (catalog.get("capabilities") or [])
                if isinstance(item, Mapping) and str(item.get("id") or "") == str(capability_id)
            ),
            None,
        )
        pack = self._host.domain_pack_for(owner) if owner else None
        resolver = getattr(pack, "resolve_capability_selection", None) if pack is not None else None
        if callable(resolver):
            return resolver(str(capability_id), request_facts=request_facts, selection=None)
        return None

    def normalize_workflow(self, workflow: Mapping[str, Any]) -> Mapping[str, Any]:
        template_id = str(workflow.get("template_id") or "").strip() if isinstance(workflow, Mapping) else ""
        domain_id, separator, local_id = template_id.partition(":")
        if not separator or domain_id not in self._host.domain_ids:
            raise ValueError("general workflow must use a namespaced template id")
        pack = self._host.domain_pack_for(domain_id)
        normalizer = getattr(pack, "normalize_workflow", None) if pack is not None else None
        if not callable(normalizer):
            raise ValueError("selected Domain does not expose workflow normalization")
        payload = dict(workflow)
        payload["template_id"] = local_id
        result = normalizer(payload)
        normalized = dict(result) if isinstance(result, Mapping) else {}
        normalized["domain_id"] = domain_id
        normalized["template_id"] = template_id
        return normalized

    def validate_workflow_plan(self, plan: Any, workflow: Mapping[str, Any]) -> None:
        normalized = self.normalize_workflow(workflow)
        domain_id = normalized.get("domain_id")
        pack = self._host.domain_pack_for(str(domain_id or ""))
        validator = getattr(pack, "validate_workflow_plan", None) if pack is not None else None
        if callable(validator):
            validator(plan, {**dict(workflow), "template_id": str(normalized["template_id"]).split(":", 1)[-1]})

    def validate_open_react_plan(self, plan: Any) -> None:
        del plan

    def plan_policy(self, plan: Any, *, workflow: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        del plan, workflow
        return {
            "schema_version": "spatial-agent.plan-policy.v1",
            "available": False,
            "domain_id": self.domain_id,
            "source": "general_runtime",
            "reason_code": "open_react_policy",
        }

    def workflow_template_catalog(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            str(key): deepcopy(dict(value))
            for key, value in (self._host.capability_catalog().get("workflow_templates") or {}).items()
            if isinstance(value, Mapping)
        }

    def workflow_template_context(self, *, include_arg_shape: bool = False, compact: bool = True) -> Mapping[str, Any]:
        del include_arg_shape, compact
        templates = []
        for key, value in self.workflow_template_catalog().items():
            item = deepcopy(dict(value))
            item["id"] = key
            templates.append(item)
        return {
            "schema_version": "spatial-agent.workflow-templates.v1",
            "templates": templates[:64],
            "known_tools": list(self._host.names),
            "known_result_types": sorted(self._host.capability_catalog().get("result_type_owners") or {}),
        }

    def planner_guidance(self) -> Mapping[str, Any]:
        return {
            "domain_id": self.domain_id,
            "domain_description": "开放式通用分析运行时；按需直接回答或使用受控能力。",
            "tool_semantics": {},
            "result_types": {},
            "planning_rules": [
                "没有必要事实或工具时可以直接回答，但不能伪造外部事实。",
                "需要事实时只使用已登记且通过 Registry 校验的工具。",
                "多个领域能力可以组合，工具失败时保留已完成结果并说明限制。",
            ],
            "clarification_policy": ["仅在缺少执行所需的关键事实时请求澄清。"],
            "rejection_policy": ["拒绝越权、未注册工具和未通过安全校验的行动。"],
        }

    def planner_request_hint(self, request: str, workflow: Mapping[str, Any] | None = None) -> str:
        del workflow
        return str(request or "")

    def request_understanding_guidance(self) -> Mapping[str, Any]:
        return {
            "schema_version": "spatial-agent.request-understanding.v1",
            "domain_id": self.domain_id,
            "required_fields": [],
            "optional_fields": ["entities", "tasks", "datasets", "constraints", "evidence"],
            "policy": "facts are hints; the validated plan and tool schemas are authoritative",
        }

    def clarification_details(self, request: str) -> Mapping[str, Any]:
        del request
        return {}

    def evidence_action_guidance(self, selection: Mapping[str, Any], *, request_facts: Any = None) -> Mapping[str, Any]:
        del request_facts
        has_candidates = bool(selection.get("candidate_ids")) if isinstance(selection, Mapping) else False
        return {
            "schema_version": "spatial-agent.evidence-action-guidance.v1",
            "state": "ready" if has_candidates else "unknown",
            "reason_code": "general_model_selection" if has_candidates else "no_matching_capability",
            "recommended_actions": ["preview"] if has_candidates else ["answer_or_clarify"],
            "source": "runtime",
        }

    def rule_planner(self) -> Any:
        return _GeneralRulePlanner()


class _GeneralRulePlanner:
    def plan(self, request: str, workflow: Mapping[str, Any] | None = None, context: Mapping[str, Any] | None = None) -> TaskPlan:
        del workflow, context
        return TaskPlan(
            goal=str(request or "")[:400],
            steps=[],
            output={
                "type": "direct_answer",
                "message": "当前使用离线规则模式，无法生成开放式回答；请切换真实模型后重试。",
            },
        )


def _merge_facts(request: str, values: list[tuple[str, RequestFacts]]) -> RequestFacts:
    tasks: list[str] = []
    datasets: list[str] = []
    evidence: list[str] = []
    constraints: dict[str, Any] = {}
    entities: dict[str, Any] = {}
    admin_name = None
    for domain_id, facts in values:
        admin_name = admin_name or facts.admin_name
        for target, source in ((tasks, facts.tasks), (datasets, facts.datasets), (evidence, facts.evidence)):
            for item in source or ():
                text = str(item).strip()
                if text and text not in target and len(target) < 32:
                    target.append(text)
        for key, value in (facts.constraints or {}).items():
            _merge_fact( constraints, str(key), value, domain_id)
        for key, value in facts.entity_snapshot().items():
            _merge_fact(entities, str(key), value, domain_id)
    return RequestFacts(
        text=request,
        admin_name=admin_name,
        tasks=tuple(tasks[:32]),
        datasets=tuple(datasets[:32]),
        constraints=constraints,
        evidence=tuple(evidence[:32]),
        entities=entities,
    )


def _merge_fact(target: dict[str, Any], key: str, value: Any, domain_id: str) -> None:
    if value is None:
        return
    if key not in target or target[key] == value:
        target[key] = deepcopy(value)
        return
    target[f"{domain_id}:{key}"] = deepcopy(value)


def _safe_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key]
        for key in ("status", "health_status", "data_readiness")
        if value.get(key) is not None
    }


def _aggregate_readiness(values: Iterable[str]) -> str:
    statuses = [str(item).lower() for item in values if str(item).strip()]
    if not statuses or all(item in {"unavailable", "not_ready"} for item in statuses):
        return "unavailable"
    if all(item in {"ready", "passed", "completed"} for item in statuses):
        return "ready"
    return "degraded"


__all__ = ["GeneralAnswerComposer", "GeneralResultRegistry", "GeneralRuntimePack"]
