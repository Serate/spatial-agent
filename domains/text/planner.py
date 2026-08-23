"""Deterministic planner for the non-GIS Runtime replay."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from agent.errors import ClarificationNeeded
from agent.models import PlanStep, TaskPlan
from agent.workflow_templates import compile_workflow_composition, compile_workflow_plan

from .workflow_templates import (
    KNOWN_RESULT_TYPES,
    KNOWN_TOOL_NAMES,
    TEXT_TASK_TEMPLATE_IDS,
    build_text_workflow_components,
    workflow_template_catalog,
)


class TextSummaryPlanner:
    def plan(
        self,
        request: str,
        workflow: Optional[Mapping[str, Any]] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> TaskPlan:
        text = str(request or "").strip()
        if not text:
            raise ClarificationNeeded("empty text request")
        catalog = workflow_template_catalog()
        if isinstance(workflow, Mapping):
            return self._compile_workflow(text, workflow, catalog)
        sections = context.get("sections") if isinstance(context, Mapping) else None
        discovery = sections.get("capability_discovery") if isinstance(sections, Mapping) else None
        selection = sections.get("workflow_selection") if isinstance(sections, Mapping) else None
        selected = (
            discovery.get("selected_capability_id")
            if isinstance(discovery, Mapping)
            and discovery.get("selection_state", "selected") == "selected"
            else None
        )
        if isinstance(selection, Mapping):
            selected = selection.get("selected_capability_id") or selected
            components = selection.get("workflow_components")
            if selected == "text_analysis" and isinstance(components, list):
                task_components = [
                    item
                    for item in components
                    if isinstance(item, Mapping)
                    and str(item.get("template_id") or "") in catalog
                ]
                if len(task_components) >= 2:
                    template_to_task = {
                        template_id: task
                        for task, template_id in TEXT_TASK_TEMPLATE_IDS.items()
                    }
                    materialized = build_text_workflow_components(
                        [
                            template_to_task.get(str(item.get("template_id") or ""), "")
                            for item in task_components
                        ],
                        text,
                    )
                    if len(materialized) >= 2:
                        return self._compile_workflow(
                            text,
                            {"components": materialized},
                            catalog,
                        )
        if selected in catalog:
            return self._compile_template(
                selected,
                {"text": text},
                catalog,
            )
        return TaskPlan(
            goal="summarize supplied text",
            steps=[PlanStep("summary", "summarize_text", {"text": text}, [])],
            output={
                "type": "text_summary_result",
                "title": "文本摘要",
                "summary": True,
            },
        )

    @staticmethod
    def _compile_template(
        template_id: str,
        constraints: Mapping[str, Any],
        catalog: Mapping[str, Mapping[str, Any]],
    ) -> TaskPlan:
        compiled = compile_workflow_plan(
            template_id,
            constraints,
            catalog=catalog,
            known_tools=KNOWN_TOOL_NAMES,
            known_result_types=KNOWN_RESULT_TYPES,
        )
        return TaskPlan(
            str(compiled["goal"]),
            [
                PlanStep(
                    str(step["id"]),
                    str(step["tool"]),
                    dict(step["args"]),
                    list(step.get("depends_on", [])),
                )
                for step in compiled["steps"]
            ],
            dict(compiled["output"]),
            list(compiled.get("assumptions") or []),
        )

    def _compile_workflow(
        self,
        request: str,
        workflow: Mapping[str, Any],
        catalog: Mapping[str, Mapping[str, Any]],
    ) -> TaskPlan:
        if isinstance(workflow.get("components"), (list, tuple)):
            compiled = compile_workflow_composition(
                workflow["components"],
                catalog=catalog,
                known_tools=KNOWN_TOOL_NAMES,
                known_result_types=KNOWN_RESULT_TYPES,
                output_type="text_analysis_result",
                goal="compose selected text workflow components",
                output_overrides={
                    "evidence": list(workflow.get("evidence") or []),
                    "constraints": dict(workflow.get("constraints") or {}),
                },
            )
            return TaskPlan(
                str(compiled["goal"]),
                [
                    PlanStep(
                        str(step["id"]),
                        str(step["tool"]),
                        dict(step["args"]),
                        list(step.get("depends_on", [])),
                    )
                    for step in compiled["steps"]
                ],
                dict(compiled["output"]),
                list(compiled.get("assumptions") or []),
            )
        template_id = str(workflow.get("template_id") or "").strip()
        if not template_id:
            raise ValueError("workflow.template_id must be a non-empty string")
        constraints = workflow.get("constraints")
        constraints = dict(constraints) if isinstance(constraints, Mapping) else {}
        constraints.setdefault("text", request)
        return self._compile_template(template_id, constraints, catalog)
