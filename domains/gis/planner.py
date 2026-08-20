"""Deterministic Planner owned by the GIS Domain Pack."""

from typing import Any, Mapping, Optional

from agent.errors import ClarificationNeeded, RequestRejected
from agent.models import TaskPlan
from agent.request_model import RequestFacts
from agent.workflow_templates import workflow_request_hint

from .request_model import parse_spatial_request
from .rule_planning import PlanningFacts, RuleBasedPlanComposer


class RuleBasedPlanner:
    """GIS adapter that turns extracted facts into a validated TaskPlan."""

    def __init__(self, composer: Optional[RuleBasedPlanComposer] = None) -> None:
        self._composer = composer or RuleBasedPlanComposer()

    @property
    def capability_rules(self):
        return self._composer.rule_ids

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        resolved = workflow_request_hint(request, workflow)
        text = str(resolved or "").strip()
        if not text:
            raise ClarificationNeeded("empty spatial analysis request")
        if any(term in text for term in ("删除", "全中国", "任意 SQL", "导出全部")):
            raise RequestRejected("request contains destructive, unauthorized, or oversized operations")
        if "KNN" in text.upper() or "最近" in text:
            raise ClarificationNeeded("M1 does not support KNN yet; use an explicit range condition")
        lowered = text.lower()
        if lowered in ("你好", "您好", "嗨", "hello", "hi"):
            return TaskPlan("respond to greeting", [], {"type": "direct_answer", "message": "你好，我是空间智能体。你可以直接询问行政区边界、DEM 高程、坡度、土地利用或建设适宜性演示分析。"})
        if any(term in text for term in ("你能做什么", "帮助", "能力范围", "你是谁")):
            return TaskPlan("explain spatial agent capabilities", [], {"type": "direct_answer", "message": "我是空间智能体，可以查询行政区边界，分析 DEM 高程和坡度，统计土地利用，并进行建设适宜性演示筛选。需要真实栅格分析时，请选择本地 GIS 后端。"})
        return self._composer.compose(
            PlanningFacts(text, self._facts_from_context(text, context, workflow))
        )

    @staticmethod
    def _facts_from_context(
        text: str,
        context: Optional[Mapping[str, Any]],
        workflow: Optional[Mapping[str, Any]],
    ) -> RequestFacts:
        """Prefer Domain Pack facts already extracted by Runtime."""
        if workflow is not None:
            return parse_spatial_request(text)
        sections = context.get("sections") if isinstance(context, Mapping) else None
        payload = sections.get("spatial_request") if isinstance(sections, Mapping) else None
        if isinstance(payload, Mapping) and payload.get("schema_version"):
            tasks = tuple(str(item) for item in (payload.get("tasks") or [])[:32])
            datasets = tuple(str(item) for item in (payload.get("datasets") or [])[:32])
            constraints = payload.get("constraints")
            return RequestFacts(
                text=text,
                admin_name=(str(payload["admin_name"]) if payload.get("admin_name") else None),
                tasks=tasks,
                datasets=datasets,
                constraints=dict(constraints) if isinstance(constraints, Mapping) else {},
                evidence=tuple(str(item) for item in (payload.get("evidence") or [])[:16]),
            )
        return parse_spatial_request(text)
