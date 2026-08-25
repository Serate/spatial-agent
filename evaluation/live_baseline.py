"""Opt-in live model baseline with bounded, credential-free evidence.

The live baseline deliberately reuses the normal runtime boundary.  It records
whether a request reached the provider, produced a valid plan, passed tool
gates, and completed on the selected backend without copying raw responses or
exception text into the report.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from agent.models import AgentRunResult
from agent.runtime_capabilities import runtime_capability_snapshot
from agent.plan_quality import project_plan_quality_evidence
from agent.evidence_registry import project_evidence_registry_completeness
from evaluation.model_evaluation import (
    DEFAULT_MODEL_REPLAY_FIXTURE,
    evaluate_model_replay_suite_file,
    evaluate_plan_quality,
    evaluate_capability_guided_repair,
    project_repair_evidence,
    sanitize_provider_metrics,
    summarize_selection_evidence,
    summarize_capability_repair_quality,
    summarize_evidence_projection,
    summarize_repair_evidence,
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
    {
        "id": "live-gis-buildability-screening",
        "request": "筛选洪山区坡度不超过15度的建设候选区域",
        "expected_status": "COMPLETED",
        "kind": "buildability",
    },
    {
        "id": "live-gis-constrained-buildability",
        "request": "使用 DEM、土地利用、道路和水体数据，筛选洪山区坡度不超过15度、距道路1000米内、排除水体的建设候选区域",
        "expected_status": "COMPLETED",
        "kind": "constrained_buildability",
    },
    {
        "id": "live-gis-region-comparison",
        "request": {"admin_names": ["洪山区", "江夏区"], "threshold": 15},
        "expected_status": "COMPLETED",
        "kind": "region_comparison",
    },
    {
        "id": "live-gis-comparison-matrix",
        "request": {"admin_names": ["洪山区", "江夏区", "武昌区"], "thresholds": [10, 20, 30]},
        "expected_status": "COMPLETED",
        "kind": "comparison_matrix",
    },
    {
        "id": "live-gis-constrained-matrix",
        "request": {
            "admin_names": ["洪山区", "江夏区"],
            "slope_limit_degrees": 15,
            "road_distances": [200, 500, 1000],
        },
        "expected_status": "COMPLETED",
        "kind": "constrained_matrix",
    },
    {
        "id": "live-economic-gdp-trend",
        "request": "查询洪山区 gdp_total 2022至2025年度趋势",
        "expected_status": "COMPLETED",
        "kind": "economic_timeseries",
        "domain_id": "economic",
        "expected_tools": ["economic_indicator_query", "economic_source_evidence"],
        "expected_result_type": "economic_timeseries_result",
    },
)


def run_live_baseline(
    *,
    backend: str = "local",
    max_files: int = 10,
    attempts_per_case: int = 3,
    cases: Iterable[Mapping[str, Any]] = DEFAULT_LIVE_CASES,
    runtime_factory: Callable[..., Any] = build_runtime,
    service_factory: Callable[[], Any] | None = None,
    snapshot_provider: Callable[[int], Mapping[str, Any]] = runtime_capability_snapshot,
    replay_evaluator: Callable[[str | Path], Mapping[str, Any]] = evaluate_model_replay_suite_file,
    replay_fixture: str | Path = DEFAULT_MODEL_REPLAY_FIXTURE,
    deadline_seconds: float | None = 180.0,
    heartbeat_seconds: float = 10.0,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    """Run the opt-in live baseline and return only safe structured evidence."""

    if max_files < 1:
        raise ValueError("max_files must be positive")
    if attempts_per_case < 1:
        raise ValueError("attempts_per_case must be positive")
    if deadline_seconds is not None and deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be positive or None")
    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")

    snapshot = snapshot_provider(max_files)
    safe_snapshot = _safe_capability_snapshot(snapshot)
    replay = dict(replay_evaluator(replay_fixture))
    replay_registry_completeness = replay.get("evidence_registry_completeness")
    if not isinstance(replay_registry_completeness, Mapping):
        replay_registry_completeness = project_evidence_registry_completeness(None)
    runtimes: dict[str, Any] = {}
    service = service_factory() if service_factory is not None else None
    results = []
    baseline_started = monotonic()
    deadline = (
        baseline_started + float(deadline_seconds)
        if deadline_seconds is not None
        else None
    )
    for case in cases:
        case_id = str(case.get("id") or "unnamed")
        domain_id = _case_domain_id(case)
        runtime_key = domain_id or "default"
        if runtime_key not in runtimes:
            runtimes[runtime_key] = _build_live_runtime(
                runtime_factory,
                backend=backend,
                domain_id=domain_id,
            )
        runtime = runtimes[runtime_key]
        _emit_progress(
            progress_callback,
            {
                "event": "started",
                "case_id": case_id,
                "phase": "case_runtime_call",
                "elapsed_ms": _elapsed_ms(baseline_started),
            },
        )
        try:
            result = _run_with_deadline(
                lambda: _run_case(
                    runtime,
                    service,
                    case,
                    safe_snapshot,
                    backend=backend,
                    attempts_per_case=attempts_per_case,
                ),
                deadline=deadline,
                heartbeat_seconds=heartbeat_seconds,
                progress_callback=progress_callback,
                case_id=case_id,
                started=baseline_started,
            )
        except _LiveBaselineTimeout as exc:
            result = _timeout_evidence(case, exc)
        results.append(result)
        _emit_progress(
            progress_callback,
            {
                # A provider may report its own timeout before the harness
                # deadline.  Only the bounded receipt itself is a harness
                # timeout; keep provider failures as completed case calls
                # with status=FAILED so the two failure planes stay distinct.
                "event": "timeout" if result.get("deadline_exceeded") else "completed",
                "case_id": case_id,
                "phase": str(result.get("phase") or "case_runtime_call"),
                "status": str(result.get("status") or "FAILED"),
                "elapsed_ms": _elapsed_ms(baseline_started),
            },
        )

    passed = sum(1 for item in results if item["passed"])
    return {
        "schema_version": "m76-live-baseline-v1",
        "execution_mode": "live_model",
        "backend": backend,
        "capability_snapshot": safe_snapshot,
        "plan_repair_replay": replay,
        "evidence_registry_completeness": replay_registry_completeness,
        "repair_evidence": summarize_repair_evidence(replay),
        "selection_evidence": summarize_selection_evidence(results),
        "evidence_projection": summarize_evidence_projection(results),
        "capability_repair_evaluation": summarize_capability_repair_quality(results),
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
        "passed": (
            passed == len(results)
            and bool(replay.get("failed", 1) == 0)
            and bool(replay_registry_completeness.get("passed"))
        ),
    }


class _LiveBaselineTimeout(TimeoutError):
    """Internal bounded timeout carrying only safe receipt fields."""

    def __init__(self, *, case_id: str, phase: str, elapsed_ms: int):
        super().__init__("live baseline deadline exceeded")
        self.case_id = str(case_id)[:96]
        self.phase = str(phase)[:64]
        self.elapsed_ms = int(max(0, elapsed_ms))


def run_bounded_operation(
    operation: Callable[[], Dict[str, Any]],
    *,
    deadline: float | None,
    heartbeat_seconds: float,
    progress_callback: Callable[[Mapping[str, Any]], None] | None,
    case_id: str,
    started: float,
) -> Dict[str, Any]:
    """Shared bounded-operation seam for explicit live acceptance modules."""

    return _run_with_deadline(
        operation,
        deadline=deadline,
        heartbeat_seconds=heartbeat_seconds,
        progress_callback=progress_callback,
        case_id=case_id,
        started=started,
    )


def _run_with_deadline(
    operation: Callable[[], Dict[str, Any]],
    *,
    deadline: float | None,
    heartbeat_seconds: float,
    progress_callback: Callable[[Mapping[str, Any]], None] | None,
    case_id: str,
    started: float,
) -> Dict[str, Any]:
    """Run one live case without waiting indefinitely on a provider thread."""

    if deadline is None:
        return operation()
    if monotonic() >= deadline:
        raise _LiveBaselineTimeout(
            case_id=case_id,
            phase="case_deadline_before_start",
            elapsed_ms=_elapsed_ms(started),
        )
    outcome: Dict[str, Any] = {}
    completed = Event()

    def invoke() -> None:
        try:
            outcome["result"] = operation()
        except BaseException as exc:  # re-raise on the caller thread
            outcome["error"] = exc
        finally:
            completed.set()

    Thread(
        target=invoke,
        name="spatial-agent-live-" + str(case_id),
        daemon=True,
    ).start()
    while not completed.is_set():
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise _LiveBaselineTimeout(
                case_id=case_id,
                phase="case_runtime_call",
                elapsed_ms=_elapsed_ms(started),
            )
        completed.wait(min(float(heartbeat_seconds), remaining))
        if not completed.is_set():
            _emit_progress(
                progress_callback,
                {
                    "event": "heartbeat",
                    "case_id": case_id,
                    "phase": "case_runtime_call",
                    "elapsed_ms": _elapsed_ms(started),
                },
            )
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result") or {}


def _timeout_evidence(case: Mapping[str, Any], timeout: _LiveBaselineTimeout) -> Dict[str, Any]:
    """Return a stable, credential-free case receipt for a harness timeout."""

    receipt = {
        "case_id": str(case.get("id") or timeout.case_id)[:96],
        "kind": str(case.get("kind") or "")[:64],
        "status": "FAILED",
        "expected_status": str(case.get("expected_status") or "COMPLETED")[:48],
        "status_match": False,
        "error_class": "timeout",
        "phase": timeout.phase,
        "deadline_exceeded": True,
        "elapsed_ms": timeout.elapsed_ms,
        "metrics": sanitize_provider_metrics({"attempts": 1, "retries": 0}),
        "actual_tools": [],
        "failed_steps": [],
        "result_type": None,
        "plan_quality": None,
        "answer_chinese": False,
        "passed": False,
        "attempt_count": 1,
        "transient_attempts": ["timeout"],
    }
    domain_id = _case_domain_id(case)
    if domain_id:
        receipt["domain_id"] = domain_id
    return receipt


def _build_live_runtime(
    runtime_factory: Callable[..., Any],
    *,
    backend: str,
    domain_id: str,
) -> Any:
    if domain_id:
        return runtime_factory("openai", backend, domain_id=domain_id)
    return runtime_factory("openai", backend)


def _case_domain_id(case: Mapping[str, Any]) -> str:
    value = str(case.get("domain_id") or "").strip()
    return value[:80]


def _elapsed_ms(started: float) -> int:
    return int(max(0.0, monotonic() - started) * 1000)


def _emit_progress(
    callback: Callable[[Mapping[str, Any]], None] | None,
    event: Mapping[str, Any],
) -> None:
    if not callable(callback):
        return
    safe = {
        "event": str(event.get("event") or "unknown")[:32],
        "case_id": str(event.get("case_id") or "")[:96],
        "phase": str(event.get("phase") or "unknown")[:64],
        "status": str(event.get("status") or "")[:32],
        "elapsed_ms": int(event.get("elapsed_ms") or 0),
    }
    try:
        callback(safe)
    except Exception:
        # Observability must never change the live result or create a second
        # failure class when a terminal consumer is unavailable.
        return


def _run_case(
    runtime: Any,
    service: Any,
    case: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    backend: str,
    attempts_per_case: int,
) -> Dict[str, Any]:
    case_id = str(case.get("id") or "unnamed")
    kind = str(case.get("kind") or "")
    if kind == "region_comparison":
        return _run_comparison_case(
            service, case, snapshot, backend=backend, attempts_per_case=attempts_per_case
        )
    if kind == "comparison_matrix":
        return _run_comparison_matrix_case(
            service, case, backend=backend, attempts_per_case=attempts_per_case
        )
    if kind == "constrained_matrix":
        return _run_constrained_matrix_case(
            service, case, backend=backend, attempts_per_case=attempts_per_case
        )
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


def _run_comparison_case(
    service: Any,
    case: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    backend: str,
    attempts_per_case: int,
) -> Dict[str, Any]:
    """Run the opt-in cross-region comparison baseline through the service layer."""
    case_id = str(case.get("id") or "unnamed")
    expected_status = str(case.get("expected_status") or "COMPLETED")
    if service is None:
        return {
            "case_id": case_id,
            "kind": "region_comparison",
            "status": "SKIPPED",
            "status_match": False,
            "error_class": "service_unavailable",
            "metrics": sanitize_provider_metrics({}),
            "actual_tools": [],
            "failed_steps": [],
            "result_type": None,
            "plan_quality": None,
            "answer_chinese": False,
            "passed": False,
            "reason": "region_comparison requires service_factory",
        }
    request = case.get("request") or {}
    if not isinstance(request, Mapping):
        request = {}
    admin_names = list(request.get("admin_names") or [])
    threshold = float(request.get("threshold") or 20.0)
    candidates = []
    for attempt in range(attempts_per_case):
        try:
            result = service.compare_buildability_regions(
                admin_names=admin_names,
                threshold=threshold,
                planner="openai",
                backend=backend,
            )
        except Exception:
            candidates.append({
                "case_id": case_id,
                "kind": "region_comparison",
                "attempt": attempt + 1,
                "status": "FAILED",
                "status_match": False,
                "error_class": "service_error",
                "metrics": sanitize_provider_metrics({}),
                "actual_tools": [],
                "failed_steps": [],
                "result_type": None,
                "plan_quality": None,
                "answer_chinese": False,
                "passed": False,
            })
            continue
        evidence = _comparison_evidence(result, case, attempt + 1)
        candidates.append(evidence)
        if evidence["passed"]:
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


def _comparison_evidence(
    result: Mapping[str, Any],
    case: Mapping[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    """Keep bounded, credential-free evidence for one comparison run."""
    rows = result.get("results") or []
    statuses = [str(row.get("status") or "") for row in rows if isinstance(row, Mapping)]
    passed = bool(rows) and all(status == "COMPLETED" for status in statuses)
    token_total = 0
    latency_values = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        metrics = sanitize_provider_metrics(row.get("planner_metrics") or {})
        token_total += int(metrics["token_usage"].get("total_tokens") or 0)
        latency = metrics["latency"].get("latency_ms")
        if latency is not None:
            latency_values.append(float(latency))
    metrics = sanitize_provider_metrics({})
    metrics["token_usage"]["total_tokens"] = token_total
    metrics["latency"] = {
        "status": "valid" if latency_values else "missing",
        "latency_ms": round(sum(latency_values) / len(latency_values), 3) if latency_values else None,
    }
    return {
        "case_id": str(case.get("id") or "unnamed"),
        "kind": "region_comparison",
        "request": {"admin_names": [str(row.get("admin_name")) for row in rows if isinstance(row, Mapping)] or result.get("admin_names") or [], "slope_limit_degrees": result.get("slope_limit_degrees")},
        "attempt": attempt,
        "status": "COMPLETED" if passed else "FAILED",
        "status_match": passed,
        "error_class": "none" if passed else _comparison_error_class(rows),
        "metrics": metrics,
        "actual_tools": sorted({str(tool) for row in rows for tool in (row.get("actual_tools") or []) if isinstance(row, Mapping)}),
        "failed_steps": [
            {"tool": str(step.get("tool")), "error_class": _step_error_class(step.get("error"))}
            for row in rows
            if isinstance(row, Mapping)
            for step in (row.get("failed_steps") or [])
            if isinstance(step, Mapping)
        ],
        "result_type": "buildability_comparison",
        "plan_quality": None,
        "answer_chinese": False,
        "rows": [
            {
                "admin_name": str(row.get("admin_name")),
                "status": str(row.get("status")),
                "candidate_pixel_count": row.get("candidate_pixel_count"),
                "candidate_ratio": row.get("candidate_ratio"),
            }
            for row in rows
            if isinstance(row, Mapping)
        ],
        "passed": passed,
    }


def _comparison_error_class(rows: list) -> str:
    statuses = [str(row.get("status") or "") for row in rows if isinstance(row, Mapping)]
    if any(status == "NEEDS_CLARIFICATION" for status in statuses):
        return "clarification"
    if any(status == "REJECTED" for status in statuses):
        return "policy_rejection"
    return "backend_execution"


def _run_comparison_matrix_case(
    service: Any,
    case: Mapping[str, Any],
    *,
    backend: str,
    attempts_per_case: int,
) -> Dict[str, Any]:
    """Run the opt-in multi-region x multi-threshold comparison matrix.

    Each region runs one ``compare_buildability`` call covering all thresholds,
    so the evidence can assert that candidate ratio is monotonic non-decreasing
    with the slope limit (a wider slope allowance can only add candidates).
    """
    case_id = str(case.get("id") or "unnamed")
    expected_status = str(case.get("expected_status") or "COMPLETED")
    if service is None:
        return {
            "case_id": case_id,
            "kind": "comparison_matrix",
            "status": "SKIPPED",
            "status_match": False,
            "error_class": "service_unavailable",
            "metrics": sanitize_provider_metrics({}),
            "actual_tools": [],
            "failed_steps": [],
            "result_type": None,
            "plan_quality": None,
            "answer_chinese": False,
            "passed": False,
            "reason": "comparison_matrix requires service_factory",
        }
    request = case.get("request") or {}
    if not isinstance(request, Mapping):
        request = {}
    admin_names = list(request.get("admin_names") or [])
    thresholds = list(request.get("thresholds") or [])
    candidates = []
    for attempt in range(attempts_per_case):
        try:
            by_region = {}
            for admin_name in admin_names:
                result = service.compare_buildability(
                    admin_name=admin_name,
                    thresholds=thresholds,
                    planner="openai",
                    backend=backend,
                )
                by_region[admin_name] = list(result.get("results") or [])
        except Exception:
            candidates.append({
                "case_id": case_id,
                "kind": "comparison_matrix",
                "attempt": attempt + 1,
                "status": "FAILED",
                "status_match": False,
                "error_class": "service_error",
                "metrics": sanitize_provider_metrics({}),
                "actual_tools": [],
                "failed_steps": [],
                "result_type": None,
                "plan_quality": None,
                "answer_chinese": False,
                "passed": False,
            })
            continue
        evidence = _matrix_evidence(by_region, case, attempt + 1)
        candidates.append(evidence)
        if evidence["passed"]:
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


def _matrix_evidence(
    by_region: Mapping[str, Any],
    case: Mapping[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    """Build bounded matrix evidence and assert monotonic candidate ratio."""
    all_rows = []
    token_total = 0
    latency_values = []
    monotonic = True
    for admin_name, rows in by_region.items():
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            all_rows.append(row)
            metrics = sanitize_provider_metrics(row.get("planner_metrics") or {})
            token_total += int(metrics["token_usage"].get("total_tokens") or 0)
            latency = metrics["latency"].get("latency_ms")
            if latency is not None:
                latency_values.append(float(latency))
        ratios = [
            float(row.get("candidate_ratio"))
            for row in rows
            if isinstance(row, Mapping)
            and row.get("status") == "COMPLETED"
            and row.get("candidate_ratio") is not None
        ]
        if len(ratios) >= 2 and any(
            later < earlier for earlier, later in zip(ratios, ratios[1:])
        ):
            monotonic = False
    statuses = [str(row.get("status") or "") for row in all_rows if isinstance(row, Mapping)]
    passed = bool(all_rows) and all(status == "COMPLETED" for status in statuses) and monotonic
    metrics = sanitize_provider_metrics({})
    metrics["token_usage"]["total_tokens"] = token_total
    metrics["latency"] = {
        "status": "valid" if latency_values else "missing",
        "latency_ms": round(sum(latency_values) / len(latency_values), 3) if latency_values else None,
    }
    return {
        "case_id": str(case.get("id") or "unnamed"),
        "kind": "comparison_matrix",
        "request": {
            "admin_names": list(by_region),
            "thresholds": sorted({
                float(row.get("slope_limit_degrees"))
                for rows in by_region.values()
                for row in rows
                if isinstance(row, Mapping) and row.get("slope_limit_degrees") is not None
            }),
        },
        "attempt": attempt,
        "status": "COMPLETED" if passed else "FAILED",
        "status_match": passed,
        "error_class": "none" if passed else _matrix_error_class(by_region),
        "metrics": metrics,
        "actual_tools": sorted({
            str(tool)
            for rows in by_region.values()
            for row in rows
            if isinstance(row, Mapping)
            for tool in (row.get("actual_tools") or [])
        }),
        "failed_steps": [
            {"tool": str(step.get("tool")), "error_class": _step_error_class(step.get("error"))}
            for rows in by_region.values()
            for row in rows
            if isinstance(row, Mapping)
            for step in (row.get("failed_steps") or [])
            if isinstance(step, Mapping)
        ],
        "result_type": "buildability_comparison",
        "plan_quality": None,
        "answer_chinese": False,
        "monotonic_ratio": monotonic,
        "regions": {
            str(name): [
                {
                    "slope_limit_degrees": row.get("slope_limit_degrees"),
                    "status": str(row.get("status")),
                    "candidate_pixel_count": row.get("candidate_pixel_count"),
                    "candidate_ratio": row.get("candidate_ratio"),
                }
                for row in rows
                if isinstance(row, Mapping)
            ]
            for name, rows in by_region.items()
        },
        "passed": passed,
    }


def _matrix_error_class(by_region: Mapping[str, Any]) -> str:
    for rows in by_region.values():
        statuses = [str(row.get("status") or "") for row in rows if isinstance(row, Mapping)]
        if any(status == "NEEDS_CLARIFICATION" for status in statuses):
            return "clarification"
        if any(status == "REJECTED" for status in statuses):
            return "policy_rejection"
    return "monotonicity" if by_region else "backend_execution"


def _run_constrained_matrix_case(
    service: Any,
    case: Mapping[str, Any],
    *,
    backend: str,
    attempts_per_case: int,
) -> Dict[str, Any]:
    """Run the opt-in road-distance sensitivity matrix.

    Each region runs one ``compare_constrained_buildability`` call covering all
    road distances, so the evidence can assert that eligible constrained
    candidates are monotonic non-decreasing as the road distance widens (a
    wider distance can only keep or add candidates).
    """
    case_id = str(case.get("id") or "unnamed")
    expected_status = str(case.get("expected_status") or "COMPLETED")
    if service is None:
        return {
            "case_id": case_id,
            "kind": "constrained_matrix",
            "status": "SKIPPED",
            "status_match": False,
            "error_class": "service_unavailable",
            "metrics": sanitize_provider_metrics({}),
            "actual_tools": [],
            "failed_steps": [],
            "result_type": None,
            "plan_quality": None,
            "answer_chinese": False,
            "passed": False,
            "reason": "constrained_matrix requires service_factory",
        }
    request = case.get("request") or {}
    if not isinstance(request, Mapping):
        request = {}
    admin_names = list(request.get("admin_names") or [])
    road_distances = list(request.get("road_distances") or [])
    slope_limit_degrees = request.get("slope_limit_degrees", 15.0)
    candidates = []
    for attempt in range(attempts_per_case):
        try:
            by_region = {}
            for admin_name in admin_names:
                result = service.compare_constrained_buildability(
                    admin_name=admin_name,
                    road_distances=road_distances,
                    slope_limit_degrees=slope_limit_degrees,
                    planner="openai",
                    backend=backend,
                )
                by_region[admin_name] = list(result.get("results") or [])
        except Exception:
            candidates.append({
                "case_id": case_id,
                "kind": "constrained_matrix",
                "attempt": attempt + 1,
                "status": "FAILED",
                "status_match": False,
                "error_class": "service_error",
                "metrics": sanitize_provider_metrics({}),
                "actual_tools": [],
                "failed_steps": [],
                "result_type": None,
                "plan_quality": None,
                "answer_chinese": False,
                "passed": False,
            })
            continue
        evidence = _constrained_matrix_evidence(by_region, case, attempt + 1)
        candidates.append(evidence)
        if evidence["passed"]:
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


def _constrained_matrix_evidence(
    by_region: Mapping[str, Any],
    case: Mapping[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    """Build bounded constrained-matrix evidence and assert monotonic eligible features."""
    all_rows = []
    token_total = 0
    latency_values = []
    monotonic = True
    for admin_name, rows in by_region.items():
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            all_rows.append(row)
            metrics = sanitize_provider_metrics(row.get("planner_metrics") or {})
            token_total += int(metrics["token_usage"].get("total_tokens") or 0)
            latency = metrics["latency"].get("latency_ms")
            if latency is not None:
                latency_values.append(float(latency))
        eligible = [
            float(row.get("eligible_features"))
            for row in rows
            if isinstance(row, Mapping)
            and row.get("status") == "COMPLETED"
            and row.get("eligible_features") is not None
        ]
        if len(eligible) >= 2 and any(
            later < earlier for earlier, later in zip(eligible, eligible[1:])
        ):
            monotonic = False
    statuses = [str(row.get("status") or "") for row in all_rows if isinstance(row, Mapping)]
    passed = bool(all_rows) and all(status == "COMPLETED" for status in statuses) and monotonic
    metrics = sanitize_provider_metrics({})
    metrics["token_usage"]["total_tokens"] = token_total
    metrics["latency"] = {
        "status": "valid" if latency_values else "missing",
        "latency_ms": round(sum(latency_values) / len(latency_values), 3) if latency_values else None,
    }
    return {
        "case_id": str(case.get("id") or "unnamed"),
        "kind": "constrained_matrix",
        "request": {
            "admin_names": list(by_region),
            "road_distances": sorted({
                float(row.get("road_distance_m"))
                for rows in by_region.values()
                for row in rows
                if isinstance(row, Mapping) and row.get("road_distance_m") is not None
            }),
        },
        "attempt": attempt,
        "status": "COMPLETED" if passed else "FAILED",
        "status_match": passed,
        "error_class": "none" if passed else _constrained_matrix_error_class(by_region),
        "metrics": metrics,
        "actual_tools": sorted({
            str(tool)
            for rows in by_region.values()
            for row in rows
            if isinstance(row, Mapping)
            for tool in (row.get("actual_tools") or [])
        }),
        "failed_steps": [
            {"tool": str(step.get("tool")), "error_class": _step_error_class(step.get("error"))}
            for rows in by_region.values()
            for row in rows
            if isinstance(row, Mapping)
            for step in (row.get("failed_steps") or [])
            if isinstance(step, Mapping)
        ],
        "result_type": "constrained_buildability_comparison",
        "plan_quality": None,
        "answer_chinese": False,
        "monotonic_eligible_features": monotonic,
        "regions": {
            str(name): [
                {
                    "road_distance_m": row.get("road_distance_m"),
                    "status": str(row.get("status")),
                    "candidate_features": row.get("candidate_features"),
                    "eligible_features": row.get("eligible_features"),
                    "water_excluded_features": row.get("water_excluded_features"),
                }
                for row in rows
                if isinstance(row, Mapping)
            ]
            for name, rows in by_region.items()
        },
        "passed": passed,
    }


def _constrained_matrix_error_class(by_region: Mapping[str, Any]) -> str:
    for rows in by_region.values():
        statuses = [str(row.get("status") or "") for row in rows if isinstance(row, Mapping)]
        if any(status == "NEEDS_CLARIFICATION" for status in statuses):
            return "clarification"
        if any(status == "REJECTED" for status in statuses):
            return "policy_rejection"
    return "monotonicity" if by_region else "backend_execution"


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
    explicit_tools = case.get("expected_tools")
    explicit_result_type = case.get("expected_result_type")
    if plan and (isinstance(explicit_tools, (list, tuple)) or explicit_result_type):
        quality = evaluate_plan_quality(
            plan,
            expected_tools=[item for item in (explicit_tools or []) if isinstance(item, str)],
            expected_result_type=explicit_result_type,
            expected_template_id=case.get("expected_template_id"),
            answer=result.answer,
        )
    elif kind == "spatial_overview" and plan:
        expected_tools = _capability_tools(snapshot, "spatial_overview")
        quality = evaluate_plan_quality(
            plan,
            expected_tools=expected_tools,
            expected_result_type="spatial_overview_result",
            answer=result.answer,
        )
    elif kind == "buildability" and plan:
        expected_tools = _capability_tools(snapshot, "buildability_screening")
        quality = evaluate_plan_quality(
            plan,
            expected_tools=expected_tools,
            expected_result_type="buildability_result",
            answer=result.answer,
        )
    elif kind == "constrained_buildability" and plan:
        expected_tools = _capability_tools(snapshot, "constrained_buildability_screening")
        quality = evaluate_plan_quality(
            plan,
            expected_tools=expected_tools,
            expected_result_type="constrained_buildability_result",
            answer=result.answer,
        )
    status_match = status == str(case.get("expected_status") or "COMPLETED")
    error_class = provider_class if provider_class != "none" else _local_error_class(result)
    repair_evidence = project_repair_evidence(result)
    registry_completeness = repair_evidence.get("evidence_registry_completeness")
    if not isinstance(registry_completeness, Mapping):
        registry_completeness = project_evidence_registry_completeness(None)
    capability_repair_quality = evaluate_capability_guided_repair(
        repair_evidence,
        expected=case,
    )
    passed = status_match and (quality is None or quality["passed"])
    passed = passed and capability_repair_quality["passed"]
    passed = passed and bool(registry_completeness.get("passed"))
    if kind == "clarification":
        passed = passed and not actual_tools
    evidence = {
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
        "runtime_plan_quality": project_plan_quality_evidence(
            (result.plan_evidence or {}).get("plan_quality")
            if isinstance(result.plan_evidence, Mapping)
            else None
        ),
        "repair_evidence": repair_evidence,
        "evidence_registry_completeness": registry_completeness,
        "capability_repair_quality": capability_repair_quality,
        "answer_chinese": bool(result.answer and any("\u3400" <= char <= "\u9fff" for char in result.answer)),
        "passed": passed,
    }
    domain_id = _case_domain_id(case)
    if domain_id:
        evidence["domain_id"] = domain_id
    return evidence


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
    if capability_id == "buildability_screening":
        return [
            "get_dataset_health_report",
            "get_zonal_buildability_analysis",
        ]
    if capability_id == "constrained_buildability_screening":
        return [
            "get_dataset_health_report",
            "get_zonal_constrained_buildability_analysis",
        ]
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
