"""Adaptive replanning during execution.

M80.1: when a step exhausts its retries and still fails, the runtime may ask
the planner to revise the *remaining* steps based on a bounded summary of what
already executed and why the step failed. The new steps still go through the
normal plan validation (registered tools, forward dependencies, step limit),
so replanning never bypasses the ToolRegistry or preflight gates.

The module owns the policy and the plan merge; the runtime owns when to call
it. All evidence written into ``replan_events`` is bounded and credential-free:
step ids, tool names, a failure category, new step ids, and timings. Raw error
text, provider responses, URLs, and keys are never copied.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Mapping, Optional

from .models import PlanStep, TaskPlan

_REPLAN_ENV = "SPATIAL_AGENT_REPLAN_LIMIT"
_DEFAULT_REPLAN_LIMIT = 1

_FAILURE_CATEGORY_TERMS = (
    ("unavailable", "preflight", "alignment", "门控", "不可用", "阻止"),
    ("missing required", "unknown tool", "must be", "dependency", "未注册", "依赖"),
    ("result reference", "not complete", "path not found", "引用"),
)


def replan_limit() -> int:
    """Max adaptive replan rounds per run (env override, default 1)."""
    raw = os.environ.get(_REPLAN_ENV)
    if raw is None or str(raw).strip() == "":
        return _DEFAULT_REPLAN_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{_REPLAN_ENV} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{_REPLAN_ENV} must be a non-negative integer")
    return value


def failure_category(error: Optional[str]) -> str:
    """Map a step error to a small stable taxonomy for replan feedback."""
    text = str(error or "").lower()
    if not text:
        return "unknown"
    if any(term in text for term in _FAILURE_CATEGORY_TERMS[0]):
        return "tool_gate"
    if any(term in text for term in _FAILURE_CATEGORY_TERMS[1]):
        return "tool_validation"
    if any(term in text for term in _FAILURE_CATEGORY_TERMS[2]):
        return "reference"
    return "backend_execution"


class ReplanningPolicy:
    """Decides whether and how the runtime replans remaining steps.

    A step failure only triggers replanning when:
    - the step actually failed (not cancelled/timed out),
    - the run has not exhausted its replan budget yet, and
    - the planner produced a valid replacement plan.
    """

    def __init__(self, limit: Optional[int] = None) -> None:
        self._limit = replan_limit() if limit is None else limit
        if self._limit < 0:
            raise ValueError("replan limit must be non-negative")

    @property
    def limit(self) -> int:
        return self._limit

    def should_replan(
        self,
        *,
        replan_count: int,
        step_status: str,
        step_error: Optional[str],
    ) -> bool:
        if step_status != "FAILED":
            return False
        if replan_count >= self._limit:
            return False
        return True

    def feedback_payload(
        self,
        *,
        request: str,
        completed_steps: List[Mapping[str, Any]],
        failed_step: Mapping[str, Any],
        remaining_tools: List[str],
        output_type: Optional[str],
    ) -> Dict[str, Any]:
        """Bounded feedback the planner uses to revise the remaining plan."""
        return {
            "stage": "replan",
            "original_request": request,
            "completed_steps": completed_steps,
            "failed_step": failed_step,
            "available_tools": remaining_tools,
            "output_type": output_type,
        }


def merge_replanned_plan(
    original: TaskPlan,
    replacement: TaskPlan,
    *,
    failed_step_id: str,
) -> TaskPlan:
    """Merge a replanned plan back into the original one.

    The original plan keeps every step up to and including the failed step
    (the failed step stays, marked FAILED by the runtime). Steps after the
    failed step are dropped: they were replaced by the replanning round.
    Replacement steps are appended with namespaced ids to avoid collisions,
    and dependencies are rewritten so references to kept original steps point
    at the real ids while references to dropped steps are removed.
    """
    kept: List[PlanStep] = []
    for step in original.steps:
        kept.append(PlanStep(step.id, step.tool, dict(step.args), list(step.depends_on)))
        if step.id == failed_step_id:
            break
    kept_ids = {step.id for step in kept}
    used = set(kept_ids)
    id_map: Dict[str, str] = {}
    new_steps: List[PlanStep] = []
    for index, step in enumerate(replacement.steps):
        step_id = step.id
        if step_id in used:
            step_id = "replan-{}-{}".format(failed_step_id, index)
            while step_id in used:
                step_id = "replan-{}-{}-{}".format(failed_step_id, index, len(used))
        used.add(step_id)
        id_map[step.id] = step_id
        new_steps.append(PlanStep(step_id, step.tool, dict(step.args), []))
    # Rewrite dependencies after all ids are known: keep references to kept
    # original steps, map replacement-internal references, drop everything else.
    for index, step in enumerate(replacement.steps):
        final_id = id_map.get(step.id, new_steps[index].id)
        depends = []
        for dependency in step.depends_on:
            if id_map.get(dependency) is not None:
                depends.append(id_map[dependency])
            elif dependency in kept_ids:
                depends.append(dependency)
        new_steps[index] = PlanStep(final_id, step.tool, dict(step.args), depends)
    merged = list(kept)
    merged.extend(new_steps)
    return TaskPlan(
        goal=replacement.goal or original.goal,
        steps=merged,
        output=dict(replacement.output or original.output),
        assumptions=list(replacement.assumptions or original.assumptions),
    )


def build_replan_event(
    *,
    failed_step_id: str,
    failed_tool: str,
    failure_category: str,
    new_step_ids: List[str],
    latency_ms: float,
) -> Dict[str, Any]:
    """Bounded, credential-free evidence for one replan round."""
    return {
        "failed_step_id": failed_step_id,
        "failed_tool": failed_tool,
        "failure_category": failure_category,
        "replanned_step_ids": new_step_ids,
        "latency_ms": round(latency_ms, 3),
        "occurred_at": time.time(),
    }


def rule_replan_plan(
    failed_step: Mapping[str, Any],
    completed_results: Mapping[str, Mapping[str, Any]],
) -> TaskPlan:
    """Deterministic downgrade replan for the rule planner.

    Keeps the runtime adaptive even when no model is involved. The replacement
    plan targets the same goal with tools that do not depend on what failed:

    - constrained buildability (roads/water)  -> plain buildability screening
    - joint-pixel buildability (grid alignment) -> separate slope + land use
    - anything else                              -> keep the original goal with a
      health-only plan so the run degrades gracefully instead of failing hard.
    """
    tool = str(failed_step.get("tool") or "")
    if tool == "get_zonal_constrained_buildability_analysis":
        args = dict(failed_step.get("args") or {})
        admin_ref = args.get("admin_name")
        args.pop("road_distance_m", None)
        args.pop("exclude_water", None)
        args["admin_name"] = admin_ref or {"$from": "filter-admin", "path": "first_name"}
        return TaskPlan(
            "downgrade constrained screening to plain buildability screening",
            [
                PlanStep(
                    "dataset-health",
                    "get_dataset_health_report",
                    {"dataset": "all", "max_files": 10},
                ),
                PlanStep(
                    "replan-buildability",
                    "get_zonal_buildability_analysis",
                    args,
                    ["dataset-health"],
                ),
            ],
            {"type": "buildability_result", "summary": True},
        )
    if tool == "get_zonal_buildability_analysis":
        args = dict(failed_step.get("args") or {})
        admin_ref = args.get("admin_name")
        args["admin_name"] = admin_ref or {"$from": "filter-admin", "path": "first_name"}
        return TaskPlan(
            "downgrade joint-pixel buildability to separate slope and land use analysis",
            [
                PlanStep(
                    "dataset-health",
                    "get_dataset_health_report",
                    {"dataset": "all", "max_files": 10},
                ),
                PlanStep(
                    "replan-slope",
                    "get_zonal_slope_statistics",
                    {"admin_name": args["admin_name"], "max_files": 10},
                    ["dataset-health"],
                ),
                PlanStep(
                    "replan-land-use",
                    "get_zonal_land_use_distribution",
                    {"admin_name": args["admin_name"], "max_files": 10},
                    ["dataset-health"],
                ),
            ],
            {"type": "terrain_land_use_analysis_result", "summary": True},
        )
    admin_ref = None
    for step in completed_results.values():
        if isinstance(step, Mapping) and step.get("admin_name"):
            admin_ref = step.get("admin_name")
            break
    return TaskPlan(
        "degrade to a dataset health summary after an execution failure",
        [
            PlanStep(
                "dataset-health",
                "get_dataset_health_report",
                {"dataset": "all", "max_files": 10},
            )
        ],
        {"type": "dataset_health_result", "summary": True},
    )
