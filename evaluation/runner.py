import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from agent.models import AgentRunResult


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    status: str
    expected_status: str
    status_match: bool
    actual_tools: List[str]
    expected_tools: List[str]
    tools_match: bool
    step_count: int
    max_steps: int
    within_max_steps: bool
    total_latency_ms: float
    planner_latency_ms: float
    total_tokens: int
    lineage_valid: bool
    error: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "expected_status": self.expected_status,
            "status_match": self.status_match,
            "actual_tools": self.actual_tools,
            "expected_tools": self.expected_tools,
            "tools_match": self.tools_match,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "within_max_steps": self.within_max_steps,
            "total_latency_ms": self.total_latency_ms,
            "planner_latency_ms": self.planner_latency_ms,
            "total_tokens": self.total_tokens,
            "lineage_valid": self.lineage_valid,
            "error": self.error,
        }


def load_cases(path: str) -> List[Dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_cases(runtime, cases: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    results = [evaluate_case(runtime.run(case["input"]), case) for case in cases]
    return summarize(results)


def evaluate_case(run: AgentRunResult, case: Dict[str, Any]) -> EvaluationResult:
    actual_tools = [step.tool for step in run.steps]
    expected_tools = case.get("expected_tools", [])
    expected_status = _expected_status(case)
    max_steps = int(case.get("max_steps", 999))
    planner_metrics = run.planner_metrics or {}
    usage = planner_metrics.get("usage") if isinstance(planner_metrics, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    total_latency_ms = round(
        sum(float(step.latency_ms or 0) for step in run.steps), 3
    )
    planner_latency_ms = round(float(planner_metrics.get("latency_ms") or 0), 3)
    total_tokens = int(usage.get("total_tokens") or 0)
    return EvaluationResult(
        case_id=case["id"],
        status=run.status.value,
        expected_status=expected_status,
        status_match=run.status.value == expected_status,
        actual_tools=actual_tools,
        expected_tools=expected_tools,
        tools_match=_tools_match(actual_tools, expected_tools),
        step_count=len(run.steps),
        max_steps=max_steps,
        within_max_steps=len(run.steps) <= max_steps,
        total_latency_ms=total_latency_ms,
        planner_latency_ms=planner_latency_ms,
        total_tokens=total_tokens,
        lineage_valid=_lineage_valid(run),
        error=run.error or "",
    )


def summarize(results: List[EvaluationResult]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(
        1
        for result in results
        if result.status_match and result.tools_match and result.within_max_steps
    )
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "status_match_rate": _rate(result.status_match for result in results),
        "tool_match_rate": _rate(result.tools_match for result in results),
        "within_max_steps_rate": _rate(result.within_max_steps for result in results),
        "lineage_valid_rate": _rate(result.lineage_valid for result in results),
        "avg_total_latency_ms": _average(result.total_latency_ms for result in results),
        "avg_planner_latency_ms": _average(result.planner_latency_ms for result in results),
        "total_tokens": sum(result.total_tokens for result in results),
        "results": [result.to_dict() for result in results],
    }


def _expected_status(case: Dict[str, Any]) -> str:
    outcome = case.get("expected_outcome")
    if outcome == "needs_clarification":
        return "NEEDS_CLARIFICATION"
    if any(item.get("must_reject") for item in case.get("expected_constraints", [])):
        return "REJECTED"
    return "COMPLETED"


def _tools_match(actual_tools: List[str], expected_tools: List[str]) -> bool:
    if not expected_tools:
        return not actual_tools
    position = 0
    for tool in actual_tools:
        if position < len(expected_tools) and tool == expected_tools[position]:
            position += 1
    return position == len(expected_tools)


def _rate(values) -> float:
    values = list(values)
    if not values:
        return 0
    return round(sum(1 for value in values if value) / len(values), 4)


def _average(values) -> float:
    values = list(values)
    return round(sum(values) / len(values), 3) if values else 0


def _lineage_valid(run: AgentRunResult) -> bool:
    known = set()
    for step in run.steps:
        if any(dependency not in known for dependency in step.depends_on):
            return False
        known.add(step.id)
    return True
