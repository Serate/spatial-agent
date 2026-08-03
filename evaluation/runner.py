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
