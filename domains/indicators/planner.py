"""Deterministic planner for the generic indicator Domain Pack."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from agent.errors import ClarificationNeeded
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import compile_workflow_plan

from .workflow_templates import KNOWN_RESULT_TYPES, KNOWN_TOOL_NAMES, workflow_template_catalog


class IndicatorsRulePlanner:
    capability_rules = ("indicator", "regional_indicators")

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
                if template_id != "indicator_discovery" and (
                    not constraints.get("indicator") or not constraints.get("regions")
                ):
                    raise ClarificationNeeded(
                        "指标查询需要明确指标 ID 和至少一个区域。",
                        {"missing_fields": [field for field in ("indicator", "regions") if not constraints.get(field)], "next_actions": ["补充指标 ID", "补充区域"]},
                    )
                return self._compile(template_id, constraints)
        text = str(request or "").strip()
        lowered = text.lower()
        if any(term in text for term in ("有哪些指标", "指标目录", "可用指标")):
            return self._compile("indicator_discovery", {})
        indicator = _indicator_id(text)
        regions = _regions(text)
        if not indicator or not regions:
            raise ClarificationNeeded(
                "指标查询需要明确指标 ID 和至少一个区域。",
                {"missing_fields": [field for field, value in (("indicator", indicator), ("regions", regions)) if not value], "next_actions": ["补充指标 ID", "补充区域"]},
            )
        operation = "trend" if any(term in text for term in ("趋势", "变化", "增长", "历年")) else "compare" if any(term in text for term in ("比较", "对比", "差异")) else "latest"
        template = "indicator_" + operation
        return self._compile(template, {"dataset": "regional_indicators", "indicator": indicator, "regions": regions})

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
    import re

    marked = re.search(r"指标(?:为|是|[:：])?\s*([A-Za-z0-9_.-]+)", str(text))
    if marked:
        return marked.group(1)[:96]
    for token in str(text).replace("：", " ").replace(":", " ").split():
        if token.startswith("demo_") or token.startswith("indicator_"):
            return token.strip("，,。；;")[:96]
    return ""


def _regions(text: str) -> list[str]:
    import re

    matches = re.findall(r"区域[^和与、,，\s]+|[\u4e00-\u9fffA-Za-z0-9]+(?:市|区|县)", str(text))
    return list(dict.fromkeys(item[:96] for item in matches))[:16]
