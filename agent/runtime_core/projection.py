"""Pure Runtime projections used by planning and lifecycle orchestration.

The public ``AgentRuntime`` facade keeps the historical private helper names,
but the behaviour lives behind this small, domain-neutral seam.  None of the
functions in this module build a planner, access a tool provider, or read
domain data; they only project bounded plans, results, and lifecycle facts.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from agent.errors import ToolError
from agent.models import AgentRunResult, RunStatus, TaskPlan
from agent.plan_quality import repair_context
from agent.replanning import failure_category
from agent.result_completeness import build_result_completeness


def plan_to_dict(plan: TaskPlan) -> Dict[str, Any]:
    return {
        "goal": plan.goal,
        "steps": [
            {
                "id": step.id,
                "tool": step.tool,
                "args": dict(step.args),
                "depends_on": list(step.depends_on),
            }
            for step in plan.steps
        ],
        "output": dict(plan.output),
        "assumptions": list(plan.assumptions),
    }


def plan_dag(plan: TaskPlan) -> Dict[str, Any]:
    nodes = [
        {
            "id": step.id,
            "tool": step.tool,
            "depends_on": list(step.depends_on),
            "arg_keys": sorted(step.args.keys()),
        }
        for step in plan.steps
    ]
    edges = [
        {"from": dependency, "to": step.id}
        for step in plan.steps
        for dependency in step.depends_on
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def compact_workflow_templates(
    templates: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Keep only selected workflow templates in the planner context."""
    if not isinstance(templates, Mapping) or not isinstance(selection, Mapping):
        return templates
    values = templates.get("templates")
    if not isinstance(values, list) or len(values) <= 1:
        return templates
    selected_ids = []
    for value in (
        selection.get("workflow_template_id"),
        selection.get("selected_capability_id"),
    ):
        text = str(value or "").strip()
        if text and text not in selected_ids:
            selected_ids.append(text)
    candidates = selection.get("candidate_workflow_ids")
    if isinstance(candidates, list):
        for value in candidates[:8]:
            text = str(value or "").strip()
            if text and text not in selected_ids:
                selected_ids.append(text)
    selected = [
        item
        for item in values
        if isinstance(item, Mapping)
        and str(item.get("id") or "") in selected_ids
    ][:2]
    compact = dict(templates)
    compact["templates"] = selected
    compact["returned_count"] = len(selected)
    compact["omitted_count"] = max(0, len(values) - len(selected))
    compact["selection_filtered"] = True
    return compact


def planner_source(planner_kind: str, workflow: Optional[Mapping[str, Any]]) -> str:
    if isinstance(workflow, Mapping) and workflow.get("template_id"):
        return "workflow_selection"
    lowered = planner_kind.lower()
    if "llm" in lowered or "openai" in lowered:
        return "llm"
    return "rule"


def matched_template_ids(
    templates_section: Mapping[str, Any],
    *,
    output_type: str,
    tool_names: list[str],
    step_count: int,
    steps: list[Mapping[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    exact: list[str] = []
    templates = templates_section.get("templates")
    if not isinstance(templates, list):
        return matched, exact
    for template in templates:
        if not isinstance(template, Mapping):
            continue
        template_id = template.get("id")
        if not isinstance(template_id, str) or not template_id:
            continue
        result_types = template.get("result_types") or []
        allowed_tools = set(template.get("allowed_tools") or [])
        try:
            max_steps = int(template.get("max_steps") or 0)
        except (TypeError, ValueError):
            max_steps = 0
        if output_type not in result_types:
            continue
        if max_steps and step_count > max_steps:
            continue
        if any(tool not in allowed_tools for tool in tool_names):
            continue
        matched.append(template_id)
        blueprint_steps = [
            step
            for step in template.get("step_blueprint") or []
            if isinstance(step, Mapping)
        ]
        if blueprint_steps and blueprint_steps_match(blueprint_steps, steps or []):
            exact.append(template_id)
    return matched, exact


def blueprint_steps_match(
    blueprint_steps: list[Mapping[str, Any]],
    actual_steps: list[Mapping[str, Any]],
) -> bool:
    if len(blueprint_steps) != len(actual_steps):
        return False
    for expected, actual in zip(blueprint_steps, actual_steps):
        if actual.get("id") != expected.get("id"):
            return False
        if actual.get("tool") != expected.get("tool"):
            return False
        if list(actual.get("depends_on") or []) != list(expected.get("depends_on") or []):
            return False
        expected_arg_keys = sorted(expected.get("arg_keys") or [])
        if expected_arg_keys and sorted(actual.get("arg_keys") or []) != expected_arg_keys:
            return False
    return True


def safe_small_mapping(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, Any] = {}
    for key, item in list(value.items())[:12]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)[:80]] = item
        else:
            result[str(key)[:80]] = str(item)[:160]
    return result


def append_execution_degradation_notice(result: AgentRunResult, answer: str) -> str:
    """Keep completion and evidence degradation visible in a short answer."""

    notices: list[str] = []
    if result.status == RunStatus.COMPLETED:
        completeness = build_result_completeness(result.to_dict())
        if completeness.get("state") == "partial":
            notices.append(
                "本次只完成了部分分析，当前结论仅基于已获得的证据；"
                "未完成部分的结果未知，修复相关条件后可以重新执行。"
            )

    # Keep this import lazy: the Runtime projection module is imported by the
    # result/answer stack, while the summary itself is a separate public seam.
    try:
        from agent.evidence.bundle import evidence_quality_limitations
        from agent.evidence.composite import normalize_alignment
        from agent.result_summary import build_result_summary

        summary = build_result_summary(result.to_dict())
        evidence = summary.get("evidence")
        if isinstance(evidence, Mapping):
            bundle = evidence.get("evidence_bundle")
            if isinstance(bundle, Mapping):
                quality_notices = evidence_quality_limitations(bundle)
                kinds = set(
                    bundle.get("coverage", {}).get("kinds", [])
                    if isinstance(bundle.get("coverage"), Mapping)
                    else []
                )
                temporal_kinds = {"web", "document_evidence", "metrics", "timeseries"}
                if not kinds.intersection(temporal_kinds):
                    quality_notices = [
                        item
                        for item in quality_notices
                        if "缺少时间信息" not in item
                        and "缺少可用时间信息" not in item
                        and "无法判断是否最新" not in item
                        and "无法判断新鲜度" not in item
                    ]
                notices.extend(quality_notices)
            if isinstance(evidence.get("alignment"), Mapping):
                alignment = normalize_alignment(evidence["alignment"])
                if alignment.get("status") == "conflict":
                    notices.append(
                        "不同数据来源存在范围或单位差异，系统未进行隐式拼接。"
                    )
                elif alignment.get("status") == "unknown":
                    notices.append(
                        "部分数据来源缺少可对齐信息，系统未进行隐式拼接。"
                    )
    except Exception:
        # A user-facing answer must not fail because an optional summary
        # projection is unavailable on a legacy result object.
        pass

    unique: list[str] = []
    for notice in notices:
        if notice and notice not in answer and notice not in unique:
            unique.append(notice)
        if len(unique) >= 4:
            break
    if not unique:
        return answer
    return answer.rstrip() + "\n\n证据提示：" + "；".join(unique)


def unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def replan_context(feedback: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "feedback": feedback,
        "workflow_repair": repair_context(feedback.get("plan_quality")),
        "note": "Adaptive replan: revise only the remaining steps needed to finish the request.",
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capability_evidence_cache_ttl() -> float:
    value = os.environ.get("SPATIAL_AGENT_CAPABILITY_EVIDENCE_TTL_SECONDS")
    if value is None or not str(value).strip():
        return 15.0
    try:
        return max(0.0, min(float(value), 300.0))
    except (TypeError, ValueError):
        return 15.0


def resolve_result_references(value: Any, results: Dict[str, Dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$from", "path"}:
            source = value["$from"]
            path = value["path"]
            if source not in results:
                raise ToolError("result reference source is not complete: " + source)
            current: Any = results[source]
            for part in path.split("."):
                if not isinstance(current, dict) or part not in current:
                    raise ToolError("result reference path not found: " + source + "." + path)
                current = current[part]
            return current
        return {key: resolve_result_references(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_result_references(item, results) for item in value]
    return value


def result_type_for_observability(result: AgentRunResult) -> str:
    plan = result.plan
    if plan is not None:
        output_type = (plan.output or {}).get("type")
        if output_type:
            return str(output_type)
    return "unknown"


def run_duration_ms(result: AgentRunResult) -> Optional[float]:
    values = [step.latency_ms for step in result.steps if step.latency_ms is not None]
    if not values:
        return None
    return round(sum(float(value) for value in values), 3)


def run_error_category(result: AgentRunResult) -> Optional[str]:
    status = result.status
    if status == RunStatus.COMPLETED:
        return None
    if status == RunStatus.CANCELLED:
        return "cancelled"
    if status == RunStatus.TIMED_OUT:
        return "timeout"
    if status == RunStatus.REJECTED:
        return "rejected"
    if status == RunStatus.NEEDS_CLARIFICATION:
        return "clarification"
    return failure_category(result.error)
