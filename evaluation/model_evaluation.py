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
from agent.plan_quality import project_plan_quality_evidence
from agent.planner_selection import normalize_planner_selection_evidence
from agent.workflow_selection import normalize_workflow_selection_evidence
from agent.evidence_registry import (
    EVIDENCE_COMPLETENESS_SCHEMA_VERSION,
    project_evidence_registry_completeness,
)
from agent.evidence_projection import (
    EVIDENCE_PROJECTION_SCHEMA_VERSION,
    project_evidence_projection,
)
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
CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION = "spatial-agent.capability-repair-evaluation.v1"
PLANNER_SELECTION_EVIDENCE_SCHEMA_VERSION = "spatial-agent.planner-selection.v1"
SELECTION_EVIDENCE_SUMMARY_SCHEMA_VERSION = "spatial-agent.selection-evaluation.v1"
_MAX_REPAIR_EVENTS = 8
_MAX_REPAIR_STEP_IDS = 24
_MAX_REPAIR_TURNS = 32
_MAX_CAPABILITY_IDS = 8
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
_REPAIR_CLASSES = {
    "repaired",
    "rejected",
    "clarification",
    "failed",
    "no_repair",
    "unknown",
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
        "capability_repair_evaluation": summarize_capability_repair_quality(results),
        "selection_evidence": summarize_selection_evidence(results),
        "evidence_registry_completeness": summarize_evidence_registry_completeness(results),
        "evidence_projection": summarize_evidence_projection(results),
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
    evidence_projection = _evaluation_evidence_projection(source, contract)
    registry_completeness = evidence_projection["evidence_registry_completeness"]
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
        repair_status = _safe_repair_token(event.get("repair_status"))
        if repair_status in {"repaired", "failed"}:
            item["repair_status"] = repair_status
        repair_reason = _safe_repair_token(event.get("repair_reason_code"))
        if repair_reason:
            item["repair_reason_code"] = repair_reason
        latency = event.get("latency_ms")
        if _nonnegative_number(latency):
            item["latency_ms"] = round(min(float(latency), 86_400_000), 3)
        for key in ("plan_quality_before", "plan_quality_after"):
            if isinstance(event.get(key), Mapping):
                item[key] = project_plan_quality_evidence(event[key])
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
    planning = source.get("plan_evidence") if isinstance(source.get("plan_evidence"), Mapping) else {}
    failed_step_count = sum(
        1 for item in step_runs[:64]
        if isinstance(item, Mapping) and str(item.get("status") or "") == "FAILED"
    )
    return {
        "schema_version": REPAIR_EVIDENCE_SCHEMA_VERSION,
        "available": bool(projected_events),
        "repair_count": len(projected_events),
        "repair_class": _repair_class(status, len(projected_events)),
        "capability_guidance": _project_capability_guidance(source),
        "workflow_selection": project_workflow_selection_evidence(source),
        "planner_selection": project_planner_selection_evidence(source),
        "plan_quality": project_plan_quality_evidence(planning.get("plan_quality")),
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
        "evidence_registry_completeness": registry_completeness,
        "evidence_projection": evidence_projection,
        "evidence_migration": evidence_projection["migration"],
    }


def _evaluation_evidence_projection(
    source: Mapping[str, Any], contract: Mapping[str, Any]
) -> Dict[str, Any]:
    """Read evaluation evidence through the public result projection seam.

    Runtime objects are rebuilt into a result contract before evaluation.  A
    persisted artifact may already carry a nested result or a legacy top-level
    registry; preserve that source for migration classification instead of
    silently rebuilding it into the current Registry shape.
    """

    if isinstance(source.get("result"), Mapping):
        return project_evidence_projection(source)
    projection_contract = dict(contract)
    raw_registry = source.get("evidence_registry")
    if isinstance(raw_registry, Mapping):
        projection_contract["evidence_registry"] = raw_registry
    return project_evidence_projection({"result": projection_contract})


def project_planner_selection_evidence(payload: Any) -> Dict[str, Any]:
    """Project the Runtime planner/domain alignment for replay and live.

    Only the versioned planner-selection fields are returned.  Requests,
    tool arguments, provider payloads and arbitrary error text never enter
    the model-evaluation report.
    """

    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        try:
            payload = payload.to_dict()
        except Exception:
            payload = {}
    source = dict(payload) if isinstance(payload, Mapping) else {}
    candidates = []
    nested_result = source.get("result")
    if isinstance(nested_result, Mapping):
        candidates.extend(
            nested_result.get(key)
            for key in ("planning", "plan_evidence")
        )
    candidates.extend(source.get(key) for key in ("plan_evidence", "planning"))
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        value = candidate.get("planner_selection")
        if isinstance(value, Mapping):
            return normalize_planner_selection_evidence(value)
    return normalize_planner_selection_evidence(None)


def project_workflow_selection_evidence(payload: Any) -> Dict[str, Any]:
    """Project only safe workflow selection state for evaluation reports."""

    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        try:
            payload = payload.to_dict()
        except Exception:
            payload = {}
    source = dict(payload) if isinstance(payload, Mapping) else {}
    candidates = []
    nested_result = source.get("result")
    if isinstance(nested_result, Mapping):
        candidates.extend(
            nested_result.get(key)
            for key in ("planning", "plan_evidence")
        )
    candidates.extend(source.get(key) for key in ("plan_evidence", "planning"))
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        value = candidate.get("workflow_selection")
        if not isinstance(value, Mapping):
            continue
        normalized = normalize_workflow_selection_evidence(value)
        return {
            "schema_version": normalized.get("schema_version"),
            "state": normalized.get("state"),
            "reason_code": normalized.get("reason_code"),
            "source": normalized.get("source"),
            "selected_capability_id": normalized.get("selected_capability_id"),
            "candidate_ids": list(normalized.get("candidate_ids") or [])[:16],
            "candidate_count": normalized.get("candidate_count"),
            "missing_fields": [
                {
                    "id": str(item.get("id"))[:80],
                    "label": str(item.get("label"))[:120],
                    "kind": str(item.get("kind") or "fact")[:32],
                }
                for item in (normalized.get("missing_fields") or [])[:8]
                if isinstance(item, Mapping) and item.get("id") and item.get("label")
            ],
            "suggested_capability_ids": [
                str(item)[:96]
                for item in (normalized.get("suggested_capability_ids") or [])[:8]
                if str(item).strip()
            ],
        }
    normalized = normalize_workflow_selection_evidence(None)
    return {
        "schema_version": normalized.get("schema_version"),
        "state": normalized.get("state"),
        "reason_code": normalized.get("reason_code"),
        "source": normalized.get("source"),
        "selected_capability_id": normalized.get("selected_capability_id"),
        "candidate_ids": [],
        "candidate_count": 0,
    }


def summarize_selection_evidence(report_or_results: Any) -> Dict[str, Any]:
    """Count bounded workflow/planner selection states in replay or live data."""

    if isinstance(report_or_results, Mapping):
        candidates = report_or_results.get("results")
        if not isinstance(candidates, list):
            candidates = report_or_results.get("cases")
    elif isinstance(report_or_results, list):
        candidates = report_or_results
    else:
        candidates = []
    candidates = candidates if isinstance(candidates, list) else []
    workflow_states = Counter()
    planner_states = Counter()
    workflow_count = 0
    planner_count = 0
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        turns = item.get("turns")
        entries = turns if isinstance(turns, list) else [item]
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            repair = entry.get("repair_evidence")
            repair = repair if isinstance(repair, Mapping) else entry
            workflow = repair.get("workflow_selection")
            planner = repair.get("planner_selection")
            if isinstance(workflow, Mapping):
                state = str(workflow.get("state") or "unavailable")[:32]
                workflow_states[state] += 1
                workflow_count += 1
            if isinstance(planner, Mapping):
                state = str(planner.get("state") or "unavailable")[:32]
                planner_states[state] += 1
                planner_count += 1
    return {
        "schema_version": SELECTION_EVIDENCE_SUMMARY_SCHEMA_VERSION,
        "workflow_selection_count": workflow_count,
        "planner_selection_count": planner_count,
        "workflow_states": dict(sorted(workflow_states.items())),
        "planner_states": dict(sorted(planner_states.items())),
        "passed": planner_count >= 0 and workflow_count >= 0,
    }


def evaluate_capability_guided_repair(
    payload: Any,
    *,
    expected: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate capability selection and repair outcome on safe evidence.

    ``payload`` may be a Runtime result, an artifact/result mapping, or an
    already projected replay evidence object.  All three paths are reduced to
    the same bounded projection before comparison, so replay and live reports
    cannot accidentally expose different fields or provider content.
    """
    actual = _coerce_repair_projection(payload)
    expected_value = _normalize_capability_expectation(expected)
    actual_guidance = actual.get("capability_guidance")
    if not isinstance(actual_guidance, Mapping):
        actual_guidance = _empty_capability_guidance()
    actual_class = _safe_repair_class(actual.get("repair_class"))
    expected_selected = expected_value.get("selected_capability_id")
    expected_candidates = expected_value.get("candidate_ids")
    expected_class = expected_value.get("repair_class")
    matches = {
        "selected_capability": (
            True
            if expected_selected is None
            else actual_guidance.get("selected_capability_id") == expected_selected
        ),
        "candidate_ids": (
            True
            if expected_candidates is None
            else actual_guidance.get("candidate_ids", []) == expected_candidates
        ),
        "repair_class": (
            True
            if expected_class is None
            else actual_class == expected_class
        ),
    }
    evaluated = any(
        value is not None
        for value in (expected_selected, expected_candidates, expected_class)
    )
    return {
        "schema_version": CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION,
        "evaluated": evaluated,
        "expected": {
            "selected_capability_id": expected_selected,
            "candidate_ids": expected_candidates,
            "repair_class": expected_class,
        },
        "actual": {
            "selected_capability_id": _safe_capability_id(
                actual_guidance.get("selected_capability_id")
            ),
            "candidate_ids": _safe_capability_ids(
                actual_guidance.get("candidate_ids")
            ),
            "repair_class": actual_class,
            "guidance_available": bool(actual_guidance.get("available")),
        },
        "matches": matches,
        "passed": all(matches.values()) if evaluated else True,
    }


def summarize_capability_repair_quality(report_or_results: Any) -> Dict[str, Any]:
    """Aggregate capability-guided repair quality without raw request data."""
    if isinstance(report_or_results, Mapping):
        candidates = report_or_results.get("results")
        if not isinstance(candidates, list):
            candidates = report_or_results.get("cases")
    elif isinstance(report_or_results, list):
        candidates = report_or_results
    else:
        candidates = []
    candidates = candidates if isinstance(candidates, list) else []
    quality = [
        item.get("capability_repair_quality")
        for item in candidates
        if isinstance(item, Mapping)
        and isinstance(item.get("capability_repair_quality"), Mapping)
    ]
    classes = Counter(
        str(item.get("actual", {}).get("repair_class") or "unknown")
        for item in quality
        if isinstance(item.get("actual"), Mapping)
    )
    evaluated = [item for item in quality if item.get("evaluated")]
    return {
        "schema_version": CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION,
        "fixture_count": len(quality),
        "evaluated_count": len(evaluated),
        "passed_count": sum(1 for item in evaluated if item.get("passed")),
        "failed_count": sum(1 for item in evaluated if not item.get("passed")),
        "repair_classes": dict(sorted(classes.items())),
        "passed": all(bool(item.get("passed", True)) for item in evaluated),
    }


def summarize_evidence_registry_completeness(report_or_results: Any) -> Dict[str, Any]:
    """Aggregate the strict registry check for replay/live-safe reports."""
    candidates = report_or_results.get("results") if isinstance(report_or_results, Mapping) else report_or_results
    candidates = candidates if isinstance(candidates, list) else []
    projections = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        direct = item.get("evidence_registry_completeness")
        if isinstance(direct, Mapping):
            projections.append(direct)
            continue
        for turn in item.get("turns") or []:
            if not isinstance(turn, Mapping):
                continue
            repair = turn.get("repair_evidence")
            projection = repair.get("evidence_registry_completeness") if isinstance(repair, Mapping) else None
            if isinstance(projection, Mapping):
                projections.append(projection)
    return _summarize_registry_projections(projections)


def summarize_evidence_projection(report_or_results: Any) -> Dict[str, Any]:
    """Aggregate shared projection and migration states for safe reports."""

    projections = _collect_evidence_projections(report_or_results)
    migration_states = Counter()
    completeness_states = Counter()
    for projection in projections:
        migration = projection.get("migration")
        migration_state = (
            str(migration.get("state") or "unavailable")[:32]
            if isinstance(migration, Mapping)
            else "unavailable"
        )
        migration_states[migration_state] += 1
        completeness = projection.get("evidence_registry_completeness")
        completeness_state = (
            "passed"
            if isinstance(completeness, Mapping) and completeness.get("passed") is True
            else "failed"
        )
        completeness_states[completeness_state] += 1
    evaluated = [
        projection
        for projection in projections
        if isinstance(projection.get("migration"), Mapping)
        and projection["migration"].get("state") != "unavailable"
    ]
    passed = bool(evaluated) and all(
        isinstance(projection.get("migration"), Mapping)
        and projection["migration"].get("state") == "current"
        and isinstance(projection.get("evidence_registry_completeness"), Mapping)
        and projection["evidence_registry_completeness"].get("passed") is True
        for projection in evaluated
    )
    return {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA_VERSION,
        "projection_count": len(projections),
        "migration_states": dict(sorted(migration_states.items())),
        "completeness_states": dict(sorted(completeness_states.items())),
        "passed": passed,
    }


def _collect_evidence_projections(value: Any) -> List[Mapping[str, Any]]:
    """Collect bounded projections from replay, live, or turn-shaped reports."""

    collected: List[Mapping[str, Any]] = []
    if isinstance(value, list):
        for item in value[:_MAX_REPAIR_TURNS]:
            collected.extend(_collect_evidence_projections(item))
        return collected[:_MAX_REPAIR_TURNS]
    if not isinstance(value, Mapping):
        return collected
    direct = value.get("evidence_projection")
    if (
        isinstance(direct, Mapping)
        and isinstance(direct.get("migration"), Mapping)
        and isinstance(direct.get("evidence_registry_completeness"), Mapping)
    ):
        collected.append(direct)
    repair = value.get("repair_evidence")
    if isinstance(repair, Mapping):
        collected.extend(_collect_evidence_projections(repair))
    for key in ("results", "cases", "turns"):
        nested = value.get(key)
        if isinstance(nested, list):
            collected.extend(_collect_evidence_projections(nested))
    return collected[:_MAX_REPAIR_TURNS]


def _fixture_registry_completeness(turns: Any) -> Dict[str, Any]:
    projections = []
    for turn in turns if isinstance(turns, list) else []:
        if not isinstance(turn, Mapping):
            continue
        repair = turn.get("repair_evidence")
        projection = repair.get("evidence_registry_completeness") if isinstance(repair, Mapping) else None
        if isinstance(projection, Mapping):
            projections.append(projection)
    return _summarize_registry_projections(projections)


def _summarize_registry_projections(projections: List[Mapping[str, Any]]) -> Dict[str, Any]:
    evaluated = [item for item in projections if item.get("schema_version") == EVIDENCE_COMPLETENESS_SCHEMA_VERSION]
    passed_count = sum(1 for item in evaluated if item.get("passed") is True)
    return {
        "schema_version": EVIDENCE_COMPLETENESS_SCHEMA_VERSION,
        "evaluated_count": len(evaluated),
        "passed_count": passed_count,
        "failed_count": max(0, len(evaluated) - passed_count),
        "passed": bool(evaluated) and passed_count == len(evaluated),
    }


def compare_repair_evidence_entries(left: Any, right: Any) -> Dict[str, Any]:
    """Check that replay/live entries share the same bounded evidence shape."""
    left_projection = _coerce_repair_projection(left)
    right_projection = _coerce_repair_projection(right)
    left_keys = _safe_projection_shape(left_projection)
    right_keys = _safe_projection_shape(right_projection)
    left_text = json.dumps(left_projection, ensure_ascii=False, sort_keys=True)
    right_text = json.dumps(right_projection, ensure_ascii=False, sort_keys=True)
    return {
        "schema_version": CAPABILITY_REPAIR_EVIDENCE_SCHEMA_VERSION,
        "same_schema": (
            left_projection.get("schema_version") == REPAIR_EVIDENCE_SCHEMA_VERSION
            and right_projection.get("schema_version") == REPAIR_EVIDENCE_SCHEMA_VERSION
        ),
        "same_shape": left_keys == right_keys,
        "left_shape": left_keys,
        "right_shape": right_keys,
        "redacted": not _contains_private_field(left_projection)
        and not _contains_private_field(right_projection),
        "contains_raw_private_terms": any(
            term in (left_text + right_text).lower()
            for term in ("authorization", "api_key", "access_token", "secret")
        ),
        "passed": (
            left_keys == right_keys
            and left_projection.get("schema_version") == REPAIR_EVIDENCE_SCHEMA_VERSION
            and right_projection.get("schema_version") == REPAIR_EVIDENCE_SCHEMA_VERSION
            and not _contains_private_field(left_projection)
            and not _contains_private_field(right_projection)
        ),
    }


def _coerce_repair_projection(payload: Any) -> Dict[str, Any]:
    """Re-project raw or previously projected evidence through one seam."""
    if isinstance(payload, Mapping):
        nested = payload.get("repair_evidence")
        if isinstance(nested, Mapping):
            payload = nested
        if payload.get("schema_version") == REPAIR_EVIDENCE_SCHEMA_VERSION:
            result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
            guidance = payload.get("capability_guidance")
            events = payload.get("lineage", {}).get("events", []) if isinstance(payload.get("lineage"), Mapping) else []
            if "terminal_status" in payload:
                count = payload.get("repair_count")
                count = count if type(count) is int and count >= 0 else 0
                events = [
                    {
                        "failed_step_id": "replay-transition",
                        "failed_tool": "replay",
                        "failure_category": "replay_transition",
                        "phase": "planning",
                        "replanned_step_ids": ["replay-transition"],
                    }
                    for _ in range(min(count, _MAX_REPAIR_EVENTS))
                ]
                result = {
                    "status": payload.get("terminal_status"),
                    "result_type": "unknown",
                }
            return project_repair_evidence({
                "status": result.get("status"),
                "result_type": result.get("result_type"),
                "plan": {"output": {"type": result.get("result_type")}},
                "replan_events": events if isinstance(events, list) else [],
                "plan_evidence": guidance if isinstance(guidance, Mapping) else {},
            })
    return project_repair_evidence(payload)


def _project_capability_guidance(source: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract only capability ids from runtime or envelope planning evidence."""
    candidates = []
    nested_result = source.get("result")
    if isinstance(nested_result, Mapping):
        candidates.extend(
            nested_result.get(key)
            for key in ("plan_evidence", "planning", "capability_guidance")
        )
    candidates.extend(
        source.get(key)
        for key in ("plan_evidence", "planning", "capability_guidance")
    )
    selected = None
    candidate_ids = []
    source_kind = "unavailable"
    for value in candidates:
        if not isinstance(value, Mapping):
            continue
        selected_value = value.get("selected_capability_id")
        if selected is None and selected_value is not None:
            selected = _safe_capability_id(selected_value)
        raw_ids = value.get("capability_candidate_ids")
        if raw_ids is None:
            raw_ids = value.get("candidate_ids")
        if not candidate_ids and isinstance(raw_ids, (list, tuple)):
            candidate_ids = _safe_capability_ids(raw_ids)
        if selected or candidate_ids:
            source_kind = "plan_evidence"
            break
    if selected and selected not in candidate_ids:
        candidate_ids.insert(0, selected)
        candidate_ids = candidate_ids[:_MAX_CAPABILITY_IDS]
    return {
        "available": bool(selected or candidate_ids),
        "selected_capability_id": selected or None,
        "candidate_ids": candidate_ids,
        "source": source_kind,
    }


def _empty_capability_guidance() -> Dict[str, Any]:
    return {
        "available": False,
        "selected_capability_id": None,
        "candidate_ids": [],
        "source": "unavailable",
    }


def _normalize_capability_expectation(value: Any) -> Dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    nested = value.get("capability_guidance")
    nested = nested if isinstance(nested, Mapping) else value.get("expected_capability")
    nested = nested if isinstance(nested, Mapping) else {}
    selected = (
        nested.get("selected_capability_id")
        or nested.get("selected")
        or value.get("expected_capability_id")
    )
    raw_candidates = (
        nested.get("candidate_ids")
        if "candidate_ids" in nested
        else nested.get("candidates")
    )
    if raw_candidates is None:
        raw_candidates = value.get("expected_capability_candidates")
    candidates = None
    if raw_candidates is not None:
        candidates = _safe_capability_ids(raw_candidates)
    repair_class = (
        value.get("expected_repair_class")
        or value.get("repair_class")
        or (value.get("expected_repair") or {}).get("class")
        if isinstance(value.get("expected_repair"), Mapping)
        else value.get("expected_repair_class") or value.get("repair_class")
    )
    repair_class = _safe_repair_class(repair_class) if repair_class else None
    return {
        "selected_capability_id": _safe_capability_id(selected) or None,
        "candidate_ids": candidates,
        "repair_class": repair_class,
    }


def _safe_capability_id(value: Any) -> str:
    return _safe_repair_token(value)


def _safe_capability_ids(values: Any) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    result = []
    for value in values[:_MAX_CAPABILITY_IDS]:
        safe = _safe_capability_id(value)
        if safe and safe not in result:
            result.append(safe)
    return result


def _safe_repair_class(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in _REPAIR_CLASSES else "unknown"


def _repair_class(status: Any, repair_count: int) -> str:
    safe_status = _safe_repair_status(status)
    if safe_status == "REJECTED":
        return "rejected"
    if safe_status == "NEEDS_CLARIFICATION":
        return "clarification"
    if safe_status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
        return "failed"
    if safe_status == "COMPLETED":
        return "repaired" if repair_count > 0 else "no_repair"
    return "unknown"


def _safe_projection_shape(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Describe the stable recursive shape, excluding values and secrets."""
    if not isinstance(value, Mapping):
        return {}
    result = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        key_text = str(key)
        if isinstance(item, Mapping):
            result[key_text] = _safe_projection_shape(item)
        elif isinstance(item, list):
            result[key_text] = [
                _safe_projection_shape(entry) if isinstance(entry, Mapping) else type(entry).__name__
                for entry in item[:_MAX_REPAIR_EVENTS]
            ]
        else:
            result[key_text] = type(item).__name__
    return result


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
    capability_guidance = _empty_capability_guidance()
    for turn in turn_evidence[:_MAX_REPAIR_TURNS]:
        if not isinstance(turn, Mapping):
            continue
        evidence = turn.get("repair_evidence")
        if not isinstance(evidence, Mapping):
            continue
        guidance = evidence.get("capability_guidance")
        if isinstance(guidance, Mapping) and (
            guidance.get("selected_capability_id") or guidance.get("candidate_ids")
        ):
            capability_guidance = {
                "available": bool(guidance.get("available")),
                "selected_capability_id": _safe_capability_id(
                    guidance.get("selected_capability_id")
                ) or None,
                "candidate_ids": _safe_capability_ids(guidance.get("candidate_ids")),
                "source": "plan_evidence",
            }
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
        "repair_class": _repair_class(final_status, inferred_count),
        "capability_guidance": capability_guidance,
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
        "evidence_projection_summary": summarize_evidence_projection(turn_evidence),
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
    capability_repair_quality = evaluate_capability_guided_repair(
        repair_evidence,
        expected=fixture,
    )
    passed = all(
        item["status_match"]
        and item["quality"]["passed"]
        and item["repair_evidence"].get("evidence_registry_completeness", {}).get("passed", False)
        for item in turn_results
    )
    passed = passed and final_status == final_expected
    if expected_repair_count is not None:
        passed = passed and repair_count == expected_repair_count
    if fixture.get("expected_plan_repair_count") is not None:
        passed = passed and repair_evidence["passed"]
    passed = passed and capability_repair_quality["passed"]
    return {
        "fixture_id": fixture_id,
        "domain": domain,
        "replay_type": str(fixture.get("replay_type") or "unknown"),
        "turn_count": len(turn_results),
        "repair_count": repair_count,
        "final_status": final_status,
        "turns": turn_results,
        "repair_evidence": repair_evidence,
        "capability_repair_quality": capability_repair_quality,
        "evidence_registry_completeness": _fixture_registry_completeness(turn_results),
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
        "evidence_registry_completeness": project_evidence_registry_completeness(None),
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
        report["evidence_registry_completeness"] = report["repair_evidence"][
            "evidence_registry_completeness"
        ]
        report["model_evidence"] = build_result_contract(
            result_payload,
            registry=runtime.result_registry(),
        )["model_evidence"]
        report["passed"] = (
            result.status.value == str(expected.get("expected_status") or "COMPLETED")
            and quality["passed"]
            and report["evidence_registry_completeness"]["passed"]
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
