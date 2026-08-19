"""Deterministic planner for the non-GIS Runtime replay."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from agent.errors import ClarificationNeeded
from agent.models import PlanStep, TaskPlan


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
        return TaskPlan(
            goal="summarize supplied text",
            steps=[PlanStep("summary", "summarize_text", {"text": text}, [])],
            output={
                "type": "text_summary_result",
                "title": "文本摘要",
                "summary": True,
            },
        )
