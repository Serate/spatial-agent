"""Run the global acceptance matrix without hiding unavailable environments."""

from typing import Any, Dict, Iterable, List

from agent.service import AgentService
from agent.capability_catalog import capability_catalog
from evaluation.model_evaluation import DEFAULT_MODEL_FIXTURE, evaluate_model_fixture_file
from evaluation.runner import evaluate_case
from run_demo import build_runtime


def run_global_cases(
    cases: Iterable[Dict[str, Any]],
    planner: str = "rule",
    backend: str = "memory",
    include_optional: bool = False,
    model_fixture: Any = DEFAULT_MODEL_FIXTURE,
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
            evaluation = _annotate_capability(evaluation, case)
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
    result_payload = {
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
    if model_fixture is not None:
        result_payload["model_evaluation"] = evaluate_model_fixture_file(model_fixture)
    return result_payload


def _run_comparison_case(service: AgentService, case: Dict[str, Any]) -> Dict[str, Any]:
    payload = case.get("input") or {}
    if case.get("id") == "threshold-comparison":
        result = service.compare_buildability(**payload, backend=case.get("backend", "memory"))
    else:
        result = service.compare_buildability_regions(**payload, backend=case.get("backend", "memory"))
    scenario = result.get("scenario") or {}
    passed = bool(scenario.get("operation") and result.get("results"))
    result_payload = {
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
    return _annotate_capability(result_payload, case)


def _annotate_capability(result: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    capability_id = case.get("capability_id")
    if not capability_id:
        return result
    definitions = capability_catalog()["capabilities"]
    definition = next((item for item in definitions if item["id"] == capability_id), None)
    if definition is None:
        result["capability_contract_match"] = False
        result["capability_error"] = "unknown capability: " + str(capability_id)
        return result
    expected_tools = set(case.get("expected_tools") or [])
    actual_tools = set(result.get("actual_tools") or [])
    expected_types = set(definition["result_types"])
    result_type = result.get("result_type") or case.get("expected_result_type")
    result["capability_id"] = capability_id
    result["capability_contract_match"] = (
        expected_tools.issubset(actual_tools)
        and (not expected_types or result_type in expected_types)
    )
    environment = case.get("backend", "memory")
    result["capability_environment"] = environment
    result["capability_environment_supported"] = (
        environment in definition["environments"]
    )
    result["execution_claim"] = (
        "environment_supported"
        if result["capability_contract_match"] and result["capability_environment_supported"]
        else "contract_only_or_environment_mismatch"
    )
    result["geometry_evidence"] = "unknown"
    return result


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
        and item.get("capability_contract_match", True)
    )
