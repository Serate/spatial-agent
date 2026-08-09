"""Run the global acceptance matrix without hiding unavailable environments."""

from typing import Any, Dict, Iterable, List

from agent.service import AgentService
from evaluation.runner import evaluate_case
from run_demo import build_runtime


def run_global_cases(
    cases: Iterable[Dict[str, Any]],
    planner: str = "rule",
    backend: str = "memory",
    include_optional: bool = False,
) -> Dict[str, Any]:
    cases = list(cases)
    runtime = build_runtime(planner, backend)
    service = AgentService()
    results = []
    for case in cases:
        surface = case.get("surface", "runtime")
        if surface in {"gis-e2e", "live-model-e2e", "deployment"} and not include_optional:
            results.append(_skipped(case, f"{surface} 需要显式启用 optional 验收"))
            continue
        if surface == "runtime":
            evaluation = evaluate_case(runtime.run(case["input"]), case).to_dict()
            results.append({**evaluation, "surface": surface, "category": case.get("category")})
            continue
        if surface == "runtime-contract":
            results.append(_skipped(case, "由专门的合成后端契约测试验证"))
            continue
        if surface == "comparison-api":
            results.append(_run_comparison_case(service, case))
            continue
        if surface in {"gis-e2e", "live-model-e2e"}:
            case_backend = case.get("backend", backend)
            case_planner = "openai" if surface == "live-model-e2e" else planner
            evaluation = evaluate_case(
                build_runtime(case_planner, case_backend).run(case["input"]), case
            ).to_dict()
            results.append({**evaluation, "surface": surface, "category": case.get("category")})
            continue
        results.append(_skipped(case, "没有注册的验收 surface"))

    executed = [item for item in results if not item.get("skipped")]
    passed = sum(1 for item in executed if item.get("passed", _evaluation_passed(item)))
    return {
        "total": len(results),
        "executed": len(executed),
        "skipped": len(results) - len(executed),
        "passed": passed,
        "failed": len(executed) - passed,
        "pass_rate": round(passed / len(executed), 4) if executed else 0,
        "evaluation_context": {
            "environment": backend,
            "execution_mode": "optional" if include_optional else "offline",
            "planner": planner,
        },
        "results": results,
    }


def _run_comparison_case(service: AgentService, case: Dict[str, Any]) -> Dict[str, Any]:
    payload = case.get("input") or {}
    if case.get("id") == "threshold-comparison":
        result = service.compare_buildability(**payload, backend=case.get("backend", "memory"))
    else:
        result = service.compare_buildability_regions(**payload, backend=case.get("backend", "memory"))
    scenario = result.get("scenario") or {}
    passed = bool(scenario.get("operation") and result.get("results"))
    return {
        "case_id": case["id"],
        "surface": case.get("surface"),
        "category": case.get("category"),
        "status": "COMPLETED" if passed else "FAILED",
        "expected_status": case.get("expected_status", "COMPLETED"),
        "passed": passed,
        "scenario": scenario,
        "row_count": len(result.get("results") or []),
        "error": "" if passed else "comparison result has no normalized scenario or rows",
    }


def _skipped(case: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "case_id": case["id"],
        "surface": case.get("surface"),
        "category": case.get("category"),
        "skipped": True,
        "status": "SKIPPED",
        "reason": reason,
    }


def _evaluation_passed(item: Dict[str, Any]) -> bool:
    return bool(
        item.get("status_match")
        and item.get("tools_match")
        and item.get("result_type_match")
        and item.get("result_contract_valid")
        and item.get("within_max_steps")
    )
