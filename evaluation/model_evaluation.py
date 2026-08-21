"""Offline model-plan evaluation with safe provider observability.

The evaluator replays a redacted structured model response through the normal
planner/runtime boundary. It deliberately exposes only bounded quality and
provider categories; raw provider payloads, errors, URLs, and credentials are
never copied into the report.
"""

from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from agent.llm_planner import LLMPlanner
from agent.domain_contract import planner_guidance
from agent.runtime import AgentRuntime
from agent.tools import DemoSpatialAdapter, ToolRegistry
from agent.workflow_templates import workflow_template_context_summary
from evaluation.answer_judge import heuristic_answer_judge
from result_contract import build_result_contract


ROOT = Path(__file__).parents[1]
DEFAULT_MODEL_FIXTURE = ROOT / "tests" / "fixtures" / "m67_spatial_overview_model.json"
DEFAULT_MODEL_REPLAY_FIXTURE = ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
TOOL_SCHEMA = ROOT / "tools" / "schema" / "tool-definitions.json"
_CHINESE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_SECRET_KEY_TERMS = ("api_key", "apikey", "secret", "access_token", "refresh_token")
_TOKEN_KEYS = ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens")
REPAIR_EVIDENCE_SCHEMA_VERSION = "spatial-agent.repair-evaluation.v1"
_MAX_REPAIR_EVENTS = 8
_MAX_REPAIR_STEP_IDS = 24
_MAX_REPAIR_TURNS = 32
_REPAIR_TYPES = {"plan_repair", "planning_repair", "execution_replan", "repair"}
_REPAIR_STATUSES = {
    "CREATED",
    "PLANNING",
    "EXECUTING",
    "COMPLETED",
    "NEEDS_CLARIFICATION",
    "REJECTED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
}


def load_model_fixture(path: Union[str, Path] = DEFAULT_MODEL_FIXTURE) -> Dict[str, Any]:
    """Load one JSON fixture and reject credentials before evaluation."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model fixture must be a JSON object")
    if _contains_private_field(payload):
        raise ValueError("model fixture must not contain credentials or private fields")
    return deepcopy(payload)


def evaluate_model_fixture_file(path: Union[str, Path] = DEFAULT_MODEL_FIXTURE) -> Dict[str, Any]:
    """Evaluate a fixture from disk without creating a network client."""
    return evaluate_model_fixture(load_model_fixture(path))


def evaluate_model_replay_suite_file(path: Union[str, Path] = DEFAULT_MODEL_REPLAY_FIXTURE) -> Dict[str, Any]:
    """Evaluate a redacted multi-turn replay suite without network access."""
    return evaluate_model_replay_suite(load_model_fixture(path))


def evaluate_model_replay_suite(suite: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay clarification and plan-repair turns through the normal runtime."""
    if not isinstance(suite, Mapping) or _contains_private_field(suite):
        raise ValueError("model replay suite is invalid or contains private fields")
    fixtures = suite.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("model replay suite must contain a fixtures array")
    results = [_evaluate_replay_fixture(fixture) for fixture in fixtures]
    passed = sum(1 for item in results if item["passed"])
    return {
        "suite_id": str(suite.get("suite_id") or "unnamed"),
        "execution_mode": "offline_fixture",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "repair_evidence": summarize_repair_evidence(results),
        "results": results,
    }


def project_repair_evidence(payload: Any) -> Dict[str, Any]:
    """Project one Runtime result into bounded, credential-free repair evidence.

    The input may be an ``AgentRunResult`` or a result/artifact mapping.  The
    normal result contract remains the source of truth for event normalization;
    this evaluator-specific projection deliberately drops run ids, timestamps,
    raw errors, requests, arguments, and provider payloads.
    """
    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        try:
            payload = payload.to_dict()
        except Exception:
            payload = {}
    source = dict(payload) if isinstance(payload, Mapping) else {}
    try:
        contract = build_result_contract(source)
    except Exception:
        contract = {"replanning": {"events": []}}
    replanning = contract.get("replanning") if isinstance(contract, Mapping) else {}
    events = replanning.get("events") if isinstance(replanning, Mapping) else []
    events = events if isinstance(events, list) else []

    projected_events = []
    for ordinal, event in enumerate(events[:_MAX_REPAIR_EVENTS], start=1):
        if not isinstance(event, Mapping):
            continue
        replacement_ids = [
            token
            for token in (
                _safe_repair_token(item)
                for item in (event.get("replanned_step_ids") or [])
            )
            if token
        ][:_MAX_REPAIR_STEP_IDS]
        item = {
            "ordinal": ordinal,
            "phase": event.get("phase") if event.get("phase") in {"planning", "execution"} else "execution",
            "failed_step_id": _safe_repair_token(event.get("failed_step_id")),
            "failed_tool": _safe_repair_token(event.get("failed_tool")),
            "failure_category": _safe_repair_token(event.get("failure_category")) or "unknown",
            "replanned_step_ids": replacement_ids,
            "replanned_step_count": len(replacement_ids),
        }
        latency = event.get("latency_ms")
        if _nonnegative_number(latency):
            item["latency_ms"] = round(min(float(latency), 86_400_000), 3)
        if item["failed_step_id"] and item["failed_tool"]:
            projected_events.append(item)

    plan = source.get("plan") if isinstance(source.get("plan"), Mapping) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    step_runs = source.get("steps") if isinstance(source.get("steps"), list) else []
    output = plan.get("output") if isinstance(plan.get("output"), Mapping) else {}
    result = source.get("result") if isinstance(source.get("result"), Mapping) else {}
    status = _safe_repair_status(source.get("status") or result.get("status"))
    result_type = output.get("type") or source.get("result_type") or result.get("result_type")
    result_type = _safe_repair_token(result_type) or "unknown"
    failed_step_count = sum(
        1 for item in step_runs[:64]
        if isinstance(item, Mapping) and str(item.get("status") or "") == "FAILED"
    )
    return {
        "schema_version": REPAIR_EVIDENCE_SCHEMA_VERSION,
        "available": bool(projected_events),
        "repair_count": len(projected_events),
        "lineage": {
            "available": bool(projected_events),
            "count": len(projected_events),
            "events": projected_events,
        },
        "result": {
            "status": status,
            "result_type": result_type,
            "plan_step_count": min(len(steps), 64),
            "failed_step_count": min(failed_step_count, 64),
        },
    }


def project_replay_repair_evidence(
    fixture_id: Any,
    replay_type: Any,
    turn_evidence: Iterable[Mapping[str, Any]],
    *,
    expected_repair_count: Any = None,
    expected_final_status: Any = None,
) -> Dict[str, Any]:
    """Project multi-turn replay recovery into the same repair evidence shape."""
    turn_evidence = list(turn_evidence)
    safe_turns = []
    for index, turn in enumerate(turn_evidence[:_MAX_REPAIR_TURNS], start=1):
        if not isinstance(turn, Mapping):
            continue
        evidence = turn.get("repair_evidence")
        evidence = evidence if isinstance(evidence, Mapping) else {}
        result = evidence.get("result") if isinstance(evidence.get("result"), Mapping) else {}
        safe_turns.append({
            "ordinal": index,
            "status": _safe_repair_status(turn.get("status")),
            "status_match": bool(turn.get("status_match")),
            "repair_count": min(int(evidence.get("repair_count") or 0), _MAX_REPAIR_EVENTS),
            "result_type": _safe_repair_token(result.get("result_type")) or "unknown",
        })

    runtime_events = []
    for turn in turn_evidence[:_MAX_REPAIR_TURNS]:
        if not isinstance(turn, Mapping):
            continue
        evidence = turn.get("repair_evidence")
        if not isinstance(evidence, Mapping):
            continue
        lineage = evidence.get("lineage")
        events = lineage.get("events") if isinstance(lineage, Mapping) else []
        for event in events if isinstance(events, list) else []:
            if isinstance(event, Mapping):
                runtime_events.append(dict(event))

    transitions = []
    for index in range(len(safe_turns) - 1):
        current = safe_turns[index]
        following = safe_turns[index + 1]
        if current["status"] == "FAILED" and following["status"] == "COMPLETED":
            transitions.append({
                "ordinal": len(transitions) + 1,
                "source": "replay_transition",
                "from_turn": current["ordinal"],
                "to_turn": following["ordinal"],
                "from_status": "FAILED",
                "to_status": "COMPLETED",
            })

    safe_type = _safe_repair_token(replay_type) or "unknown"
    inferred_count = len(runtime_events)
    if safe_type in _REPAIR_TYPES:
        inferred_count = max(inferred_count, len(transitions))
    expected = _bounded_nonnegative_int(expected_repair_count)
    expected_status = _safe_repair_status(expected_final_status)
    final_status = safe_turns[-1]["status"] if safe_turns else "unknown"
    expected_match = expected is None or inferred_count == expected
    final_match = expected_status in (None, "unknown") or final_status == expected_status
    rounds = []
    for event in runtime_events[:_MAX_REPAIR_EVENTS]:
        item = dict(event)
        item["source"] = "runtime_event"
        item["ordinal"] = len(rounds) + 1
        rounds.append(item)
    if not runtime_events:
        rounds.extend(transitions[:_MAX_REPAIR_EVENTS])
    return {
        "schema_version": REPAIR_EVIDENCE_SCHEMA_VERSION,
        "available": inferred_count > 0,
        "repair_count": min(inferred_count, _MAX_REPAIR_EVENTS),
        "clarification_count": sum(
            1 for turn in safe_turns if turn["status"] == "NEEDS_CLARIFICATION"
        ),
        "failed_turn_count": sum(1 for turn in safe_turns if turn["status"] == "FAILED"),
        "replay_type": safe_type,
        "fixture_id": _safe_repair_token(fixture_id) or "unknown",
        "turn_count": len(safe_turns),
        "terminal_status": final_status,
        "lineage": {
            "available": bool(rounds),
            "count": min(len(rounds), _MAX_REPAIR_EVENTS),
            "events": rounds[:_MAX_REPAIR_EVENTS],
        },
        "turns": safe_turns,
        "expected_repair_count": expected,
        "expected_match": expected_match,
        "expected_final_status": expected_status,
        "final_status_match": final_match,
        "passed": expected_match and final_match,
    }


def summarize_repair_evidence(report_or_results: Any) -> Dict[str, Any]:
    """Aggregate only safe repair projections for replay or live reports."""
    if isinstance(report_or_results, Mapping):
        results = report_or_results.get("results")
        if not isinstance(results, list):
            results = []
    elif isinstance(report_or_results, list):
        results = report_or_results
    else:
        results = []
    evidence = [
        item.get("repair_evidence")
        for item in results
        if isinstance(item, Mapping) and isinstance(item.get("repair_evidence"), Mapping)
    ]
    return {
        "schema_version": REPAIR_EVIDENCE_SCHEMA_VERSION,
        "available": any(bool(item.get("available")) for item in evidence),
        "fixture_count": len(evidence),
        "repair_case_count": sum(1 for item in evidence if int(item.get("repair_count") or 0) > 0),
        "repair_count": min(sum(int(item.get("repair_count") or 0) for item in evidence), _MAX_REPAIR_EVENTS),
        "clarification_count": min(sum(int(item.get("clarification_count") or 0) for item in evidence), _MAX_REPAIR_TURNS),
        "passed": all(bool(item.get("passed", True)) for item in evidence),
    }


def _evaluate_replay_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(fixture, Mapping):
        return {"fixture_id": "invalid", "passed": False, "error_class": "fixture_error"}
    fixture_id = str(fixture.get("fixture_id") or "unnamed")
    turns = fixture.get("turns")
    if not isinstance(turns, list) or not turns:
        return {"fixture_id": fixture_id, "passed": False, "error_class": "fixture_error"}
    responses = [turn.get("response") for turn in turns if isinstance(turn, Mapping)]
    if len(responses) != len(turns) or not all(isinstance(item, Mapping) for item in responses):
        return {"fixture_id": fixture_id, "passed": False, "error_class": "fixture_error"}
    metrics = _fixture_metrics(fixture)
    safe_metrics = sanitize_provider_metrics(metrics)
    domain = str(fixture.get("domain") or "gis")[:32]
    runtime = _build_recorded_runtime(
        responses,
        metrics,
        domain=domain,
    )
    session_id = "m69-replay-" + fixture_id
    turn_results = []
    for turn in turns:
        expected = turn.get("expected") or {}
        try:
            result = runtime.run(str(turn.get("request") or ""), session_id=session_id)
            status = result.status.value
            status_match = status == str(expected.get("expected_status") or status)
            quality = {"passed": True, "status_only": True}
            repair_projection = project_repair_evidence(result)
            if status == "COMPLETED":
                plan = result.to_dict().get("plan") or {}
                quality = evaluate_plan_quality(
                    plan,
                    expected_tools=expected.get("expected_tools") or [],
                    expected_result_type=expected.get("expected_result_type"),
                    expected_template_id=expected.get("expected_template_id"),
                    answer=result.answer,
                )
            turn_results.append({
                "status": status,
                "expected_status": expected.get("expected_status"),
                "status_match": status_match,
                "quality": quality,
                "repair_evidence": repair_projection,
            })
        except Exception:
            turn_results.append({
                "status": "EVALUATOR_ERROR",
                "expected_status": expected.get("expected_status"),
                "status_match": False,
                "quality": {"passed": False},
                "repair_evidence": project_repair_evidence({"status": "FAILED"}),
            })
    repair_count = sum(1 for item in turn_results[:-1] if item["status"] in {"FAILED", "NEEDS_CLARIFICATION"})
    expected_repair_count = fixture.get("expected_repair_count")
    final_expected = fixture.get("expected_final_status", "COMPLETED")
    final_status = turn_results[-1]["status"]
    repair_evidence = project_replay_repair_evidence(
        fixture_id,
        fixture.get("replay_type"),
        turn_results,
        expected_repair_count=fixture.get("expected_plan_repair_count"),
        expected_final_status=final_expected,
    )
    passed = all(item["status_match"] and item["quality"]["passed"] for item in turn_results)
    passed = passed and final_status == final_expected
    if expected_repair_count is not None:
        passed = passed and repair_count == expected_repair_count
    if fixture.get("expected_plan_repair_count") is not None:
        passed = passed and repair_evidence["passed"]
    return {
        "fixture_id": fixture_id,
        "domain": domain,
        "replay_type": str(fixture.get("replay_type") or "unknown"),
        "turn_count": len(turn_results),
        "repair_count": repair_count,
        "final_status": final_status,
        "turns": turn_results,
        "repair_evidence": repair_evidence,
        "metrics": safe_metrics,
        "passed": passed,
        "error_class": "none" if passed else "replay_contract_error",
    }


def evaluate_model_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay a redacted planner response and return a safe quality report."""
    if not isinstance(fixture, Mapping):
        raise ValueError("model fixture must be a mapping")
    if _contains_private_field(fixture):
        raise ValueError("model fixture must not contain credentials or private fields")

    request = str(fixture.get("request") or "")
    expected = fixture.get("expected") or {}
    expected_tools = list(expected.get("expected_tools") or [])
    expected_result_type = expected.get("expected_result_type")
    fixture_id = str(fixture.get("fixture_id") or "unnamed")
    provider_metrics = dict(_fixture_metrics(fixture))
    provider_metrics.setdefault("execution_mode", "offline_replay")
    provider_metrics.setdefault("fixture_id", fixture_id)
    safety = sanitize_provider_metrics(provider_metrics)

    report: Dict[str, Any] = {
        "fixture_id": fixture_id,
        "request": request,
        "execution_mode": "offline_fixture",
        "provider": "redacted-fixture",
        "status": "FAILED",
        "quality": {
            "tool_coverage": _empty_quality("no plan"),
            "dependency_dag": _empty_quality("no plan"),
            "result_type_match": _empty_quality("no plan"),
            "workflow_template_match": _empty_quality("no plan"),
            "chinese_answer": _empty_quality("no answer"),
        },
        "plan_quality": {
            "tool_coverage": _empty_quality("no plan"),
            "dependency_dag": _empty_quality("no plan"),
            "result_type_match": _empty_quality("no plan"),
            "workflow_template_match": _empty_quality("no plan"),
            "chinese_answer": _empty_quality("no answer"),
        },
        "repair_evidence": project_repair_evidence({"status": "FAILED"}),
        "safety": safety,
        "error_class": safety["provider_error"]["class"],
        "passed": False,
    }

    if safety["provider_error"]["class"] != "none":
        report["status"] = "PROVIDER_ERROR"
        return report

    response = fixture.get("response")
    if not isinstance(response, Mapping):
        report["status"] = "MODEL_RESPONSE_MISSING"
        return report

    try:
        runtime = _build_recorded_runtime(response, provider_metrics)
        result = runtime.run(request, session_id="m67-offline-fixture")
        plan_payload = result.to_dict().get("plan") or {}
        quality = evaluate_plan_quality(
            plan_payload,
            expected_tools=expected_tools,
            expected_result_type=expected_result_type,
            expected_template_id=expected.get("expected_template_id"),
            answer=result.answer,
        )
        report["status"] = result.status.value
        report["quality"] = quality
        report["plan_quality"] = quality
        report["actual_tools"] = [step.tool for step in result.steps]
        report["result_type"] = _result_type(plan_payload)
        report["answer"] = result.answer or ""
        result_payload = result.to_dict()
        result_payload["result_type"] = report["result_type"]
        report["repair_evidence"] = project_repair_evidence(result)
        report["model_evidence"] = build_result_contract(
            result_payload,
            registry=runtime.result_registry(),
        )["model_evidence"]
        report["passed"] = (
            result.status.value == str(expected.get("expected_status") or "COMPLETED")
            and quality["passed"]
        )
        if result.status.value != "COMPLETED":
            report["error_class"] = "runtime_failure"
    except Exception as exc:
        # Keep diagnostics categorical. The exception text may contain a URL or
        # provider response and is intentionally not copied into the report.
        report["status"] = "EVALUATOR_ERROR"
        report["error_class"] = _runtime_error_class(exc)
    return report


def evaluate_plan_quality(
    plan: Mapping[str, Any],
    expected_tools: Iterable[str],
    expected_result_type: Optional[str],
    answer: Optional[str],
    expected_template_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Measure the quality properties that are stable across model providers."""
    steps = plan.get("steps") if isinstance(plan, Mapping) else None
    steps = steps if isinstance(steps, list) else []
    actual_tools = [step.get("tool") for step in steps if isinstance(step, Mapping)]
    actual_tools = [tool for tool in actual_tools if isinstance(tool, str)]
    expected_tools = [tool for tool in expected_tools if isinstance(tool, str)]
    coverage = _tool_coverage(actual_tools, expected_tools)
    dag = _dependency_dag(steps)
    actual_type = _result_type(plan)
    type_passed = expected_result_type is None or actual_type == expected_result_type
    result_type = {
        "passed": type_passed,
        "actual": actual_type,
        "expected": expected_result_type,
    }
    template_match = _workflow_template_match(
        plan,
        output_type=actual_type,
        tool_names=actual_tools,
        expected_template_id=expected_template_id,
    )
    answer_text = answer if isinstance(answer, str) else ""
    chinese_count = len(_CHINESE_RE.findall(answer_text))
    chinese_answer = {
        "passed": chinese_count > 0,
        "chinese_char_count": chinese_count,
        "answer_length": len(answer_text),
    }
    passed = bool(
        coverage["passed"]
        and dag["passed"]
        and type_passed
        and template_match["passed"]
        and chinese_answer["passed"]
    )
    return {
        "passed": passed,
        "tool_coverage": coverage,
        "dependency_dag": dag,
        "result_type_match": result_type,
        "workflow_template_match": template_match,
        "chinese_answer": chinese_answer,
        "answer_judge": heuristic_answer_judge(
            answer_text, steps, request=plan.get("goal")
        ),
    }


def sanitize_provider_metrics(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an allowlisted, credential-free view of provider telemetry."""
    metrics = metrics if isinstance(metrics, Mapping) else {}
    usage = metrics.get("usage")
    usage = usage if isinstance(usage, Mapping) else {}
    token_values = {key: usage.get(key) for key in _TOKEN_KEYS if key in usage}
    invalid_tokens = [key for key, value in token_values.items() if not _nonnegative_int(value)]
    safe_usage = {
        key: int(value)
        for key, value in token_values.items()
        if _nonnegative_int(value)
    }
    token_status = "invalid" if invalid_tokens else ("reported" if safe_usage else "missing")
    safe_usage["status"] = token_status
    safe_usage["invalid_fields"] = invalid_tokens
    safe_usage.setdefault("total_tokens", 0)

    raw_latency = metrics.get("latency_ms")
    if _nonnegative_number(raw_latency):
        latency = {"status": "valid", "latency_ms": round(float(raw_latency), 3)}
    elif raw_latency is None:
        latency = {"status": "missing", "latency_ms": None}
    else:
        latency = {"status": "invalid", "latency_ms": None}

    status = metrics.get("response_status")
    safe_status = int(status) if _nonnegative_int(status) else None
    error_class = classify_provider_error(metrics.get("error_type"), safe_status, metrics.get("status"))
    provider_error = {"class": error_class, "response_status": safe_status}
    safe_attempts = int(metrics["attempts"]) if _nonnegative_int(metrics.get("attempts")) else 0
    safe_retries = int(metrics["retries"]) if _nonnegative_int(metrics.get("retries")) else 0
    return {
        "token_usage": safe_usage,
        "latency": latency,
        "provider_error": provider_error,
        "attempts": safe_attempts,
        "retries": safe_retries,
    }


def classify_provider_error(
    error_type: Any,
    response_status: Optional[int] = None,
    status: Any = None,
) -> str:
    """Map provider-specific error names to a small safe taxonomy."""
    value = str(error_type or "").strip().lower()
    if not value and status in (None, "", "success") and not response_status:
        return "none"
    if value == "http_error":
        if response_status in (401, 403):
            return "authentication"
        if response_status == 429:
            return "rate_limited"
        if response_status in (408, 425) or (response_status is not None and response_status >= 500):
            return "transient_http"
        return "request_rejected"
    if value in {"timeout", "timed_out"}:
        return "timeout"
    if value == "url_error":
        return "network"
    if value in {"response_json_error", "response_shape_error"}:
        return "invalid_response"
    if value in {"planning_error", "schema_error"}:
        return "planner_error"
    if not value and response_status and response_status >= 500:
        return "transient_http"
    return "other"


def _build_recorded_runtime(
    response: Mapping[str, Any],
    metrics: Mapping[str, Any],
    *,
    domain: str = "gis",
) -> AgentRuntime:
    if domain == "text":
        from domains.text.domain import TEXT_DOMAIN_PACK
        from domains.text.provider import TextToolProvider

        registry = ToolRegistry.from_provider(TextToolProvider())
        client = _RecordedModelClient(response, metrics)
        planner = LLMPlanner(
            client,
            registry.names,
            planner_guidance=planner_guidance(TEXT_DOMAIN_PACK),
        )
        return AgentRuntime(planner, registry, domain_pack=TEXT_DOMAIN_PACK)
    if domain != "gis":
        raise ValueError("unsupported replay domain: " + domain)
    adapter = DemoSpatialAdapter()
    registry = ToolRegistry.from_json(str(TOOL_SCHEMA), adapter)
    client = _RecordedModelClient(response, metrics)
    from domains.gis.domain import GIS_DOMAIN_PACK

    planner = LLMPlanner(
        client,
        registry.names,
        planner_guidance=planner_guidance(GIS_DOMAIN_PACK),
    )
    return AgentRuntime(planner, registry, domain_pack=GIS_DOMAIN_PACK)


class _RecordedModelClient:
    def __init__(self, response: Mapping[str, Any], metrics: Mapping[str, Any]):
        self._responses = (
            [deepcopy(dict(item)) for item in response]
            if isinstance(response, list)
            else [deepcopy(dict(response))]
        )
        self._metrics = dict(metrics)

    def complete_json(self, messages, schema):
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return deepcopy(self._responses[0])

    def metrics(self):
        return dict(self._metrics)


def _fixture_metrics(fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    provider = fixture.get("provider")
    if isinstance(provider, Mapping) and isinstance(provider.get("metrics"), Mapping):
        return provider["metrics"]
    return fixture.get("provider_metrics") or fixture.get("metrics") or {}


def _tool_coverage(actual: List[str], expected: List[str]) -> Dict[str, Any]:
    remaining = Counter(expected)
    covered = 0
    unexpected = []
    for tool in actual:
        if remaining[tool] > 0:
            remaining[tool] -= 1
            covered += 1
        else:
            unexpected.append(tool)
    missing = []
    for tool in expected:
        if remaining[tool] > 0:
            missing.append(tool)
            remaining[tool] -= 1
    return {
        "passed": covered == len(expected),
        "covered_count": covered,
        "expected_count": len(expected),
        "coverage_ratio": round(covered / len(expected), 4) if expected else 1.0,
        "missing": missing,
        "unexpected": unexpected,
        "actual": actual,
        "expected": expected,
    }


def _dependency_dag(steps: List[Any]) -> Dict[str, Any]:
    ids = [step.get("id") if isinstance(step, Mapping) else None for step in steps]
    positions = {step_id: index for index, step_id in enumerate(ids) if isinstance(step_id, str)}
    issues = []
    duplicate_ids = [step_id for step_id, count in Counter(ids).items() if step_id and count > 1]
    if duplicate_ids:
        issues.append("duplicate_id")
    graph = {step_id: [] for step_id in positions}
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            issues.append("invalid_step")
            continue
        step_id = step.get("id")
        dependencies = step.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            issues.append("invalid_dependency_list")
            continue
        for dependency in dependencies:
            if dependency not in positions:
                issues.append("unknown_dependency")
            elif dependency == step_id:
                issues.append("self_dependency")
            else:
                graph.setdefault(dependency, []).append(step_id)
                if positions[dependency] >= index:
                    issues.append("future_dependency")
        for source_id, _ in _find_references(step.get("args", {})):
            if source_id not in dependencies:
                issues.append("reference_not_declared")
    if _has_cycle(graph):
        issues.append("cycle")
    issues = list(dict.fromkeys(issues))
    return {
        "passed": not issues,
        "node_count": len(steps),
        "edge_count": sum(len(value) for value in graph.values()),
        "issues": issues,
        "duplicate_ids": duplicate_ids,
    }


def _find_references(value: Any):
    if isinstance(value, Mapping):
        if set(value) == {"$from", "path"} and isinstance(value.get("$from"), str):
            yield value["$from"], value.get("path")
            return
        for item in value.values():
            yield from _find_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _find_references(item)


def _has_cycle(graph: Mapping[str, List[str]]) -> bool:
    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _result_type(plan: Mapping[str, Any]) -> str:
    output = plan.get("output") if isinstance(plan, Mapping) else None
    return str(output.get("type") or "unknown") if isinstance(output, Mapping) else "unknown"


def _workflow_template_match(
    plan: Mapping[str, Any],
    *,
    output_type: str,
    tool_names: List[str],
    expected_template_id: Optional[str],
) -> Dict[str, Any]:
    summary = workflow_template_context_summary()
    templates = summary.get("templates") if isinstance(summary, Mapping) else []
    steps = plan.get("steps") if isinstance(plan, Mapping) else None
    steps = steps if isinstance(steps, list) else []
    matched: List[str] = []
    exact: List[str] = []
    issues_by_template: Dict[str, List[str]] = {}
    relevant_templates = []
    for template in templates if isinstance(templates, list) else []:
        if not isinstance(template, Mapping):
            continue
        template_id = template.get("id")
        if not isinstance(template_id, str) or not template_id:
            continue
        if expected_template_id and template_id != expected_template_id:
            continue
        relevant_templates.append(template)
        issues = _template_match_issues(template, steps, output_type, tool_names)
        issues_by_template[template_id] = issues
        hard_issues = [issue for issue in issues if not issue.startswith("blueprint_")]
        if not hard_issues:
            matched.append(template_id)
        if not issues:
            exact.append(template_id)
    requires_exact = _template_has_blueprint(relevant_templates, expected_template_id)
    if expected_template_id:
        passed = expected_template_id in (exact if requires_exact else matched)
    else:
        passed = bool(matched) or not _has_relevant_template(templates, output_type)
    return {
        "passed": passed,
        "expected_template_id": expected_template_id,
        "matched_template_ids": matched,
        "exact_template_ids": exact,
        "output_type": output_type,
        "tool_names": tool_names,
        "issues": issues_by_template,
        "template_count": len(relevant_templates),
        "requires_exact_blueprint": requires_exact,
    }


def _template_match_issues(
    template: Mapping[str, Any],
    steps: List[Any],
    output_type: str,
    tool_names: List[str],
) -> List[str]:
    issues: List[str] = []
    if output_type not in (template.get("result_types") or []):
        issues.append("result_type")
    allowed_tools = set(template.get("allowed_tools") or [])
    if any(tool not in allowed_tools for tool in tool_names):
        issues.append("allowed_tools")
    try:
        max_steps = int(template.get("max_steps") or 0)
    except (TypeError, ValueError):
        max_steps = 0
    if max_steps and len(steps) > max_steps:
        issues.append("max_steps")
    blueprint = template.get("step_blueprint") or []
    if blueprint:
        if len(blueprint) != len(steps):
            issues.append("blueprint_step_count")
        for index, blueprint_step in enumerate(blueprint):
            if index >= len(steps) or not isinstance(blueprint_step, Mapping):
                continue
            actual_step = steps[index]
            if not isinstance(actual_step, Mapping):
                issues.append("blueprint_step")
                continue
            if actual_step.get("id") != blueprint_step.get("id"):
                issues.append("blueprint_step_id")
            if actual_step.get("tool") != blueprint_step.get("tool"):
                issues.append("blueprint_tool")
            actual_depends = actual_step.get("depends_on") or []
            blueprint_depends = blueprint_step.get("depends_on") or []
            if list(actual_depends) != list(blueprint_depends):
                issues.append("blueprint_dependency")
            expected_arg_keys = sorted(blueprint_step.get("arg_keys") or [])
            actual_args = actual_step.get("args") if isinstance(actual_step.get("args"), Mapping) else {}
            if expected_arg_keys and sorted(actual_args.keys()) != expected_arg_keys:
                issues.append("blueprint_arg_keys")
            expected_refs = sorted(_result_refs_from_shape(blueprint_step.get("arg_shape")))
            actual_refs = sorted(_find_references(actual_args))
            if expected_refs != actual_refs:
                issues.append("blueprint_result_ref")
    return list(dict.fromkeys(issues))


def _template_has_blueprint(templates: List[Mapping[str, Any]], template_id: Optional[str]) -> bool:
    if not template_id:
        return False
    for template in templates:
        if template.get("id") == template_id:
            return bool(template.get("step_blueprint"))
    return False


def _result_refs_from_shape(value: Any):
    if isinstance(value, Mapping):
        if set(value) == {"binds_result", "path"} and value.get("binds_result"):
            yield str(value["binds_result"]), value.get("path")
            return
        for item in value.values():
            yield from _result_refs_from_shape(item)
    elif isinstance(value, list):
        for item in value:
            yield from _result_refs_from_shape(item)


def _has_relevant_template(templates: Any, output_type: str) -> bool:
    if not isinstance(templates, list):
        return False
    return any(
        isinstance(template, Mapping)
        and output_type in (template.get("result_types") or [])
        for template in templates
    )


def _empty_quality(reason: str) -> Dict[str, Any]:
    return {"passed": False, "reason": reason}


def _runtime_error_class(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "planning" in name:
        return "planner_error"
    return "runtime_error"


def _safe_repair_token(value: Any) -> str:
    """Allow identifiers only; never echo arbitrary error/provider text."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    token = str(value).strip()[:96]
    if not token or not re.fullmatch(r"[A-Za-z0-9_.:-]+", token):
        return ""
    if re.search(r"(?:sk-|bearer|token|secret|password|key)", token, re.IGNORECASE):
        return ""
    return token


def _safe_repair_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    return status if status in _REPAIR_STATUSES else "unknown"


def _bounded_nonnegative_int(value: Any) -> Optional[int]:
    if type(value) is int and value >= 0:
        return min(value, _MAX_REPAIR_EVENTS)
    return None


def _contains_private_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(term in key_text for term in _SECRET_KEY_TERMS):
                return True
            if _contains_private_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_private_field(item) for item in value)
    elif isinstance(value, str):
        return bool(re.search(r"(?:sk-|bearer\s+)[A-Za-z0-9._-]{8,}", value, re.IGNORECASE))
    return False


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0
