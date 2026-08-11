"""Opt-in live model baseline with bounded, credential-free evidence.

The live baseline deliberately reuses the normal runtime boundary.  It records
whether a request reached the provider, produced a valid plan, passed tool
gates, and completed on the selected backend without copying raw responses or
exception text into the report.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from agent.models import AgentRunResult
from agent.runtime_capabilities import runtime_capability_snapshot
from evaluation.model_evaluation import (
    DEFAULT_MODEL_REPLAY_FIXTURE,
    classify_provider_error,
    evaluate_model_replay_suite_file,
    evaluate_plan_quality,
    sanitize_provider_metrics,
)
from run_demo import build_runtime


DEFAULT_LIVE_CASES = (
    {
        "id": "capability-driven-clarification",
        "request": "查询洪山区地下管线三维风险分布",
        "expected_status": "NEEDS_CLARIFICATION",
        "kind": "clarification",
    },
    {
        "id": "live-gis-spatial-overview",
        "request": "分析洪山区空间概况",
        "expected_status": "COMPLETED",
        "kind": "spatial_overview",
    },
)


def run_live_baseline(
    *,
    backend: str = "local",
    max_files: int = 10,
    attempts_per_case: int = 3,
    cases: Iterable[Mapping[str, Any]] = DEFAULT_LIVE_CASES,
    runtime_factory: Callable[[str, str], Any] = build_runtime,
    snapshot_provider: Callable[[int], Mapping[str, Any]] = runtime_capability_snapshot,
    replay_evaluator: Callable[[str | Path], Mapping[str, Any]] = evaluate_model_replay_suite_file,
    replay_fixture: str | Path = DEFAULT_MODEL_REPLAY_FIXTURE,
) -> Dict[str, Any]:
    """Run the opt-in live baseline and return only safe structured evidence."""

    if max_files < 1:
        raise ValueError("max_files must be positive")
    if attempts_per_case < 1:
        raise ValueError("attempts_per_case must be positive")

    snapshot = snapshot_provider(max_files)
    safe_snapshot = _safe_capability_snapshot(snapshot)
    replay = dict(replay_evaluator(replay_fixture))
    runtime = runtime_factory("openai", backend)
    results = []
    for case in cases:
        results.append(
            _run_case(
                runtime,
                case,
                safe_snapshot,
                attempts_per_case=attempts_per_case,
            )
        )

    passed = sum(1 for item in results if item["passed"])
    return {
        "schema_version": "m76-live-baseline-v1",
        "execution_mode": "live_model",
        "backend": backend,
        "capability_snapshot": safe_snapshot,
        "plan_repair_replay": replay,
        "cases": results,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 4) if results else 0,
            "error_classes": dict(
                Counter(item["error_class"] for item in results)
            ),
            "token_usage": _sum_metrics(results, "token_usage", "total_tokens"),
            "latency_ms": _latency_summary(results),
            "attempts": sum(item["metrics"].get("attempts", 0) for item in results),
            "retries": sum(item["metrics"].get("retries", 0) for item in results),
        },
        "passed": passed == len(results) and bool(replay.get("failed", 1) == 0),
    }


def _run_case(
    runtime: Any,
    case: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    attempts_per_case: int,
) -> Dict[str, Any]:
    case_id = str(case.get("id") or "unnamed")
    request = str(case.get("request") or "")
    expected_status = str(case.get("expected_status") or "COMPLETED")
    candidates = []
    for attempt in range(attempts_per_case):
        result = runtime.run(request, session_id="m76-live-baseline-" + case_id)
        evidence = _result_evidence(result, case, snapshot, attempt + 1)
        candidates.append(evidence)
        if evidence["passed"] or evidence["error_class"] not in {"provider_transient", "network", "timeout", "rate_limited"}:
            break
    selected = next((item for item in candidates if item["passed"]), candidates[-1])
    selected["attempt_count"] = len(candidates)
    selected["transient_attempts"] = [
        item["error_class"]
        for item in candidates
        if item["error_class"] in {"provider_transient", "network", "timeout", "rate_limited"}
    ]
    selected["expected_status"] = expected_status
    return selected


def _result_evidence(
    result: AgentRunResult,
    case: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    metrics = sanitize_provider_metrics(result.planner_metrics or {})
    provider_class = metrics["provider_error"]["class"]
    status = result.status.value
    plan = result.to_dict().get("plan") or {}
    actual_tools = [step.tool for step in result.steps]
    kind = str(case.get("kind") or "")
    quality = None
    if kind == "spatial_overview" and plan:
        expected_tools = _capability_tools(snapshot, "spatial_overview")
        quality = evaluate_plan_quality(
            plan,
            expected_tools=expected_tools,
            expected_result_type="spatial_overview_result",
            answer=result.answer,
        )
    status_match = status == str(case.get("expected_status") or "COMPLETED")
    error_class = provider_class if provider_class != "none" else _local_error_class(result)
    passed = status_match and (quality is None or quality["passed"])
    if kind == "clarification":
        passed = passed and not actual_tools
    return {
        "case_id": str(case.get("id") or "unnamed"),
        "request": str(case.get("request") or ""),
        "attempt": attempt,
        "status": status,
        "status_match": status_match,
        "error_class": error_class,
        "metrics": metrics,
        "actual_tools": actual_tools,
        "failed_steps": [
            {
                "tool": step.tool,
                "error_class": _step_error_class(step.error),
            }
            for step in result.steps
            if step.status == "FAILED"
        ],
        "result_type": (plan.get("output") or {}).get("type"),
        "plan_quality": quality,
        "answer_chinese": bool(result.answer and any("\u3400" <= char <= "\u9fff" for char in result.answer)),
        "passed": passed,
    }


def _safe_capability_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep capability evidence useful while removing machine-specific data."""
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    capabilities = []
    for item in snapshot.get("capabilities", []):
        if not isinstance(item, Mapping):
            continue
        capabilities.append(
            {
                "id": str(item.get("id") or ""),
                "tools": [str(value) for value in item.get("tools", []) if isinstance(value, str)][:20],
                "available": bool(item.get("available")),
                "capability_status": str(item.get("capability_status") or "unknown"),
                "dataset_gate": str(item.get("dataset_gate") or "unknown"),
                "missing_datasets": [str(value) for value in item.get("missing_datasets", [])][:10],
            }
        )
    datasets = []
    for item in snapshot.get("data_evidence", {}).values():
        if not isinstance(item, Mapping):
            continue
        datasets.append(
            {
                "status": str(item.get("status") or "unknown"),
                "file_count": int(item.get("file_count") or 0),
                "checked_files": int(item.get("checked_files") or 0),
            }
        )
    return {
        "environment": str(snapshot.get("environment") or "unknown"),
        "health_status": str(snapshot.get("health_status") or "unknown"),
        "data_readiness": str(snapshot.get("data_readiness") or "unknown"),
        "analysis_ready": _safe_analysis_ready(snapshot.get("analysis_ready")),
        "capabilities": capabilities,
        "dataset_statuses": datasets,
        "runtime": {
            key: bool(value)
            for key, value in (snapshot.get("runtime") or {}).items()
            if key in {"local_gis_backend", "geopandas", "rasterio"}
        },
    }


def _safe_analysis_ready(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "unknown"}
    return {
        "status": str(value.get("status") or "unknown"),
        "required": bool(value.get("required")),
        "version": str(value.get("derived_version") or value.get("version") or "")[:80],
        "grid_alignment": _alignment_status(value.get("grid_alignment")),
    }


def _alignment_status(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status") or "unknown")
    return str(value or "unknown")


def _capability_tools(snapshot: Mapping[str, Any], capability_id: str) -> list[str]:
    # The runtime snapshot intentionally carries the static capability tools in
    # the capability entry only in newer deployments. Keep a stable fallback.
    for item in snapshot.get("capabilities", []):
        if isinstance(item, Mapping) and item.get("id") == capability_id:
            tools = item.get("tools")
            if isinstance(tools, list) and all(isinstance(value, str) for value in tools):
                normalized = list(tools)
                if capability_id == "spatial_overview" and normalized.count("get_zonal_vector_summary") == 1:
                    normalized.append("get_zonal_vector_summary")
                return normalized
    return [
        "get_dataset_health_report",
        "get_dataset_schema",
        "range_query",
        "get_zonal_raster_statistics",
        "get_zonal_slope_statistics",
        "get_zonal_land_use_distribution",
        "get_zonal_vector_summary",
        "get_zonal_vector_summary",
    ]


def _local_error_class(result: AgentRunResult) -> str:
    if result.status.value == "NEEDS_CLARIFICATION":
        return "clarification"
    if result.status.value == "REJECTED":
        return "policy_rejection"
    if result.plan is None:
        return "plan_validation"
    step_errors = [step.error or "" for step in result.steps if step.status == "FAILED"]
    joined = " ".join(step_errors).lower()
    if any(term in joined for term in ("unavailable", "preflight", "alignment", "不可用", "门控")):
        return "tool_gate"
    if any(term in joined for term in ("missing required", "unknown tool", "must be", "dependency")):
        return "tool_validation"
    if step_errors or result.status.value == "FAILED":
        return "backend_execution"
    return "none"


def _step_error_class(error: Optional[str]) -> str:
    text = str(error or "").lower()
    if not text:
        return "none"
    if any(term in text for term in ("unavailable", "preflight", "alignment", "不可用", "门控")):
        return "tool_gate"
    if any(term in text for term in ("missing required", "unknown tool", "must be", "dependency")):
        return "tool_validation"
    return "backend_execution"


def _sum_metrics(results: list[Mapping[str, Any]], group: str, key: str) -> int:
    return sum(int(((item.get("metrics") or {}).get(group) or {}).get(key) or 0) for item in results)


def _latency_summary(results: list[Mapping[str, Any]]) -> Dict[str, Optional[float]]:
    values = [
        float(((item.get("metrics") or {}).get("latency") or {}).get("latency_ms"))
        for item in results
        if ((item.get("metrics") or {}).get("latency") or {}).get("latency_ms") is not None
    ]
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(sum(values) / len(values), 3),
    }
