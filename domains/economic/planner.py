"""Deterministic fallback Planner for the Economic Domain Pack."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from agent.errors import ClarificationNeeded
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import compile_workflow_plan

from .catalog import ECONOMIC_DATASET, indicator_aliases
from .workflow_templates import KNOWN_RESULT_TYPES, KNOWN_TOOL_NAMES, workflow_template_catalog


class EconomicRulePlanner:
    capability_rules = ("economic", ECONOMIC_DATASET)

    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        del context
        if isinstance(workflow, Mapping):
            template_id = str(workflow.get("template_id") or "").strip()
            constraints = dict(workflow.get("constraints") or {})
            if template_id:
                if template_id != "economic_discovery":
                    self._require_facts(constraints)
                return self._compile(template_id, constraints)
        text = str(request or "").strip()
        if any(term in text for term in ("有哪些经济指标", "经济指标目录", "经济数据目录")):
            return self._compile("economic_discovery", {})
        indicator = _indicator_id(text)
        regions = _regions(text)
        if not indicator or not regions:
            missing = []
            if not indicator:
                missing.append("indicator")
            if not regions:
                missing.append("regions")
            raise ClarificationNeeded(
                "经济分析需要明确指标和统计区域；可以先询问‘有哪些经济指标’。",
                {"missing_fields": missing, "next_actions": ["查询经济指标目录", "补充指标 ID 或指标名称", "补充统计区域"]},
            )
        operation = (
            "evidence"
            if any(term in text for term in ("来源", "出处", "统计口径"))
            else "trend"
            if any(term in text for term in ("趋势", "变化", "增长", "历年"))
            else "compare"
            if any(term in text for term in ("比较", "对比", "差异"))
            else "latest"
        )
        period_type = _period_type(text)
        template = "economic_" + operation
        return self._compile(
            template,
            {"dataset": ECONOMIC_DATASET, "indicator": indicator, "regions": regions, "period_type": period_type},
        )

    @staticmethod
    def _require_facts(constraints: Mapping[str, Any]) -> None:
        missing = [field for field in ("indicator", "regions") if not constraints.get(field)]
        if missing:
            raise ClarificationNeeded(
                "经济分析需要明确指标和统计区域。",
                {"missing_fields": missing, "next_actions": ["查询经济指标目录", "补充指标和区域"]},
            )

    @staticmethod
    def _compile(template_id: str, constraints: Mapping[str, Any]) -> TaskPlan:
        compiled = compile_workflow_plan(
            template_id,
            constraints,
            catalog=workflow_template_catalog(),
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
        )
        return TaskPlan(
            str(compiled["goal"]),
            [PlanStep(str(item["id"]), str(item["tool"]), dict(item["args"]), list(item.get("depends_on", []))) for item in compiled["steps"]],
            dict(compiled["output"]),
        )


def _indicator_id(text: str) -> str:
    marked = re.search(r"(?:指标|经济指标)(?:为|是|[:：])?\s*([A-Za-z][A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    if marked:
        return marked.group(1)[:96]
    for indicator, aliases in indicator_aliases().items():
        if any(alias in text for alias in aliases):
            return indicator
    for token in re.findall(r"\b[a-z][a-z0-9_]{2,64}\b", text.lower()):
        if token.startswith(("gdp", "retail", "fixed_", "urban_")):
            return token
    return ""


def _regions(text: str) -> list[str]:
    matches = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{1,32}?(?:市|区|县)", str(text))
    cleaned = []
    for item in matches:
        value = re.sub(
            r"^(?:请|帮我|查询|分析|了解|查看|统计|评估|研究|判断|说明|对|的)+",
            "",
            item,
        )
        value = value.lstrip("和与及、,，")
        # “地区生产总值” is an indicator label, not a region named“地区”。
        if value in {"地区", "区域"}:
            continue
        if value:
            cleaned.append(value[:96])
    return list(dict.fromkeys(cleaned))[:16]


def _period_type(text: str) -> str:
    if any(term in text for term in ("半年", "上半年", "1-6月", "1—6月")):
        return "half_year"
    if any(term in text for term in ("季度", "一季度", "二季度", "三季度", "四季度")):
        return "quarter"
    if any(term in text for term in ("月度", "每月")):
        return "month"
    return "annual"
