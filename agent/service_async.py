"""Async job lifecycle helpers shared by the service facade and entry points.

Pure helpers: they never touch the executor or the job dict directly owned by
AgentService. The facade keeps ownership of worker submission and recovery;
this module provides the observability contract, failure classification,
timing utilities, and process-liveness checks.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from agent.models import AgentRunResult
from agent.action_lifecycle import (
    ACTION_LIFECYCLE_SCHEMA_VERSION,
    LIFECYCLE_ACTIONS,
    LIFECYCLE_STATES,
    project_action_lifecycle,
)
from agent.runtime_context import runtime_context_fingerprint
from agent.request_identity import normalize_request_identity
from agent.plan_identity import normalize_plan_identity
from agent.evidence_revalidation import normalize_evidence_binding
from agent.sqlite_store import SQLiteStateStore
from agent.nested_schema import NestedSchemaError, validate_async_nested_sections
from agent.plan_quality import project_plan_quality_evidence
from agent.action_precondition import (
    normalize_action_preconditions,
    project_action_preconditions,
)
from agent.action_effect import normalize_action_effect, project_action_effect
from agent.selection_interaction import normalize_selection_interaction
from agent.execution_timeline import normalize_execution_timeline
from agent.evidence_projection import project_evidence_projection
from agent.evidence_recovery import project_evidence_recovery
from agent.recovery_action import normalize_action_receipt
from result_contract import build_lineage_index


ASYNC_RESULT_EVIDENCE_SCHEMA_VERSION = "spatial-agent.async-result-evidence.v1"
_ASYNC_RESULT_EVIDENCE_STATES = {"pending", "success", "degraded", "unavailable"}

_TERMINAL_RUN_STATUSES = {
    "COMPLETED",
    "NEEDS_CLARIFICATION",
    "WAITING_FOR_DECISION",
    "REJECTED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
}


def terminal_run_statuses():
    return set(_TERMINAL_RUN_STATUSES)


def async_fingerprint(payload: Dict[str, Any]) -> str:
    import hashlib
    import json

    serialized = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return "request:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def async_status(state_store: SQLiteStateStore, job: Dict[str, Any]) -> str:
    if job.get("status") == "CANCEL_REQUESTED":
        return "CANCEL_REQUESTED"
    result = state_store.get(job["run_id"])
    if result is not None:
        return result.status.value
    return "QUEUED" if job.get("status") in {"QUEUED", "RUNNING"} else str(job.get("status"))


def build_async_observability(
    job: Dict[str, Any],
    result: AgentRunResult = None,
    lineage: Dict[str, Any] = None,
    result_evidence: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build a request-free lifecycle contract for polling and metrics consumers."""
    status = str(job.get("status") or "UNKNOWN")
    result_status = result.status.value if result is not None else None
    if result_status in _TERMINAL_RUN_STATUSES:
        status = result_status
    now = time.time()
    created_at = _as_float(job.get("created_at"))
    started_at = _as_float(job.get("started_at"))
    finished_at = _as_float(job.get("finished_at"))
    queue_wait_ms = _as_float(job.get("queue_wait_ms"))
    if queue_wait_ms is None and created_at is not None:
        queue_end = started_at or (finished_at if finished_at is not None else now)
        queue_wait_ms = max(0, (queue_end - created_at) * 1000)
    run_duration_ms = _as_float(job.get("run_duration_ms"))
    if run_duration_ms is None and started_at is not None:
        run_end = finished_at if finished_at is not None else now
        run_duration_ms = max(0, (run_end - started_at) * 1000)
    total_duration_ms = None
    if created_at is not None:
        total_end = finished_at if finished_at is not None else now
        total_duration_ms = max(0, (total_end - created_at) * 1000)
    failure_category = job.get("failure_category")
    if not failure_category and status != "COMPLETED":
        failure_category = failure_category_for(
            status, result.error if result is not None else None
        )
    recovery_count = int(job.get("recovery_count") or 0)
    phase = {
        "QUEUED": "queued",
        "RUNNING": "running",
        "CANCEL_REQUESTED": "cancelling",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "TIMED_OUT": "timed_out",
        "REJECTED": "rejected",
        "NEEDS_CLARIFICATION": "clarification",
        "WAITING_FOR_DECISION": "waiting_decision",
    }.get(status, "unknown")
    observation = {
        "schema_version": 1,
        "run_id": job.get("run_id"),
        "status": status,
        "phase": phase,
        "failure_category": failure_category,
        "request_fingerprint": async_fingerprint(job.get("payload") or {}),
        "last_event": job.get("last_event"),
        "queue_wait_ms": _round_ms(queue_wait_ms),
        "run_duration_ms": _round_ms(run_duration_ms),
        "total_duration_ms": _round_ms(total_duration_ms),
        "timestamps": {
            "submitted_at": _epoch_to_iso(created_at),
            "started_at": _epoch_to_iso(started_at),
            "finished_at": _epoch_to_iso(finished_at),
            "cancel_requested_at": _epoch_to_iso(_as_float(job.get("cancel_requested_at"))),
        },
        "recovered": recovery_count > 0,
        "recovery_count": recovery_count,
        "cancel_requested": _as_float(job.get("cancel_requested_at")) is not None,
    }
    if isinstance(lineage, dict):
        observation["lineage"] = lineage
    observation["result_evidence"] = result_evidence or {
        "schema_version": ASYNC_RESULT_EVIDENCE_SCHEMA_VERSION,
        "available": False,
        "state": "pending" if status in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"} else "unavailable",
        "status": status,
    }
    context = result.runtime_context if result is not None else None
    if context is None:
        payload = job.get("payload")
        context = payload.get("runtime_context") if isinstance(payload, dict) else None
    fingerprint = runtime_context_fingerprint(context)
    if fingerprint:
        observation["runtime_context_fingerprint"] = fingerprint
    return observation


def build_async_result_evidence(
    contract: Mapping[str, Any] = None,
    *,
    status: str = "UNKNOWN",
    artifact_ref: Any = None,
) -> Dict[str, Any]:
    """Project only safe view state for an async polling response.

    The full result envelope remains available from ``GET /runs/{id}``.  This
    compact projection lets a poller select a renderer without receiving the
    request, answer, raw tool errors, or filesystem paths.  ``state`` is the
    common lifecycle vocabulary consumed by all Domains: success, degraded,
    unavailable, or pending while no result snapshot exists yet.
    """
    value = contract if isinstance(contract, Mapping) else {}
    lifecycle_input = dict(value)
    lifecycle_input["status"] = status
    lifecycle = project_action_lifecycle(lifecycle_input)
    degradation = value.get("degradation")
    degradation_status = (
        str(degradation.get("status") or "none")
        if isinstance(degradation, Mapping)
        else "none"
    )
    lifecycle_state = str(lifecycle.get("state") or "")
    if degradation_status == "unavailable":
        state = "unavailable"
    elif degradation_status in {"warning", "degraded"}:
        state = "degraded"
    elif lifecycle_state in {
        "planning",
        "executing",
        "awaiting_confirmation",
        "clarification_required",
    }:
        state = "pending"
    elif lifecycle_state in {"repairable", "recoverable", "failed", "rejected", "cancelled"}:
        state = "degraded"
    else:
        state = "success"

    workspace = value.get("workspace")
    workspace = workspace if isinstance(workspace, Mapping) else {}
    requested_panels = [
        str(item)[:64]
        for item in (workspace.get("panels") or [])
        if isinstance(item, (str, int))
    ][:20]
    specs = []
    view_specs = workspace.get("view_specs")
    view_specs = view_specs if isinstance(view_specs, (list, tuple)) else []
    for item in view_specs[:20]:
        if not isinstance(item, Mapping) or not item.get("id"):
            continue
        specs.append({
            "id": str(item.get("id"))[:64],
            "renderer": str(item.get("renderer") or "view")[:64],
        })

    views = value.get("views")
    views = views if isinstance(views, Mapping) else {}
    panels = views.get("panels")
    panels = panels if isinstance(panels, Mapping) else {}
    safe_panels: Dict[str, Dict[str, Any]] = {}
    for panel_id, panel in list(panels.items())[:20]:
        if not isinstance(panel, Mapping):
            continue
        panel_name = str(panel_id)[:64]
        kind = str(panel.get("kind") or "unknown")[:64]
        safe_panels[panel_name] = {
            "kind": kind,
            "state": "unavailable" if kind == "unavailable" else "available",
            "artifact_available": bool(panel.get("artifact_available")),
        }

    ref = None
    if artifact_ref:
        # Artifacts can originate on Windows and be recovered by a Linux
        # worker.  Do not rely on the host platform's Path separator.
        ref = str(artifact_ref).replace("\\", "/").rsplit("/", 1)[-1] or None
    planning = value.get("planning")
    planning = planning if isinstance(planning, Mapping) else {}
    evidence_projection = project_evidence_projection(value)
    evidence_recovery = project_evidence_recovery(value)
    request_identity = normalize_request_identity(value.get("request_identity"))
    plan_identity = normalize_plan_identity(planning.get("plan_identity"))
    evidence_binding = normalize_evidence_binding(planning.get("evidence_binding"))
    timeline = normalize_execution_timeline(value.get("execution_timeline"))
    registry = evidence_projection["evidence_registry"]
    selection = evidence_projection["selection"]
    result = {
        "schema_version": ASYNC_RESULT_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value),
        "state": state,
        "status": str(status or "UNKNOWN")[:32],
        "lifecycle": lifecycle,
        "result_type": str(value.get("type") or "unknown")[:96],
        "request_identity": request_identity,
        "degradation_status": degradation_status,
        "workspace": {
            "schema_version": str(workspace.get("schema_version") or "")[:80],
            "panels": requested_panels,
            "view_specs": specs,
        },
        "views": {
            "schema_version": str(views.get("schema_version") or "spatial-agent.views.v1")[:80],
            "panels": safe_panels,
        },
        "artifact": {"available": bool(ref), "ref": ref},
        "planning": {
            "plan_identity": plan_identity,
            "evidence_binding": evidence_binding,
            "plan_quality": project_plan_quality_evidence(planning.get("plan_quality")),
            "workflow_selection": selection["workflow_selection"],
            "planner_selection": selection["planner_selection"],
        },
        "selection_interaction": normalize_selection_interaction(
            value.get("selection_interaction")
        ),
        "execution_timeline": timeline,
        "action_preconditions": project_action_preconditions(value),
        "action_effect": project_action_effect(value),
        "evidence_registry": registry,
        "evidence_projection": evidence_projection,
        "evidence_recovery": evidence_recovery,
    }
    if isinstance(value.get("action_receipt"), Mapping):
        result["action_receipt"] = normalize_action_receipt(
            value.get("action_receipt")
        )
    return result


def _normalize_lifecycle(value: Any, status: str) -> Dict[str, Any]:
    """Keep async lifecycle evidence bounded while tolerating old payloads."""
    fallback = project_action_lifecycle({"status": status})
    if not isinstance(value, Mapping):
        return fallback
    if value.get("schema_version") != ACTION_LIFECYCLE_SCHEMA_VERSION:
        return fallback
    state = str(value.get("state") or "")[:64]
    phase = str(value.get("phase") or "")[:32]
    if state not in LIFECYCLE_STATES or not phase:
        return fallback
    actions = [
        str(item)[:32]
        for item in (value.get("allowed_actions") or [])
        if str(item) in LIFECYCLE_ACTIONS
    ][:8]
    result = dict(fallback)
    result.update(
        {
            "state": state,
            "phase": phase,
            "status": str(value.get("status") or status or "UNKNOWN")[:32],
            "allowed_actions": actions,
            "reason_code": str(value.get("reason_code") or "")[:96],
        }
    )
    lineage = value.get("lineage")
    if isinstance(lineage, Mapping):
        result["lineage"] = {
            "retry_count": _bounded_int(lineage.get("retry_count"), 0, 10000),
            "repair_count": _bounded_int(lineage.get("repair_count"), 0, 1000),
            "recovery_count": _bounded_int(lineage.get("recovery_count"), 0, 10000),
            "decision": str(lineage.get("decision") or "")[:64] or None,
            "recovered": bool(lineage.get("recovered")),
        }
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def unavailable_async_result_evidence(
    *,
    status: str = "UNKNOWN",
    artifact_ref: Any = None,
    reason_code: str = "async_result_evidence_missing",
    source: str = "run_artifact",
) -> Dict[str, Any]:
    """Describe missing async evidence without silently dropping the state.

    Artifact-only recovery may encounter a legacy run artifact that predates
    the async evidence field.  Keep the normal bounded evidence shape, but
    explicitly mark availability as unknown and expose only a stable reason
    code.  This is intentionally not an error payload and never includes a
    request, raw exception, or host path.
    """
    evidence = build_async_result_evidence(
        {}, status=status, artifact_ref=artifact_ref
    )
    evidence.update(
        {
            "available": False,
            "state": "unavailable",
            "degradation_status": "unavailable",
            "availability": "unknown",
            "reason_code": str(reason_code or "async_result_evidence_missing")[:96],
            "source": str(source or "run_artifact")[:32],
        }
    )
    return evidence


def normalize_async_result_evidence(
    value: Any,
    *,
    status: str = "UNKNOWN",
    artifact_ref: Any = None,
) -> Dict[str, Any]:
    """Return a bounded, path-safe async evidence projection.

    This is used at the artifact boundary as well as during recovery.  It
    prevents a hand-written or older artifact from reintroducing arbitrary
    nested data into the polling contract.  Unknown nested versions/states
    become explicit unavailable evidence rather than being interpreted as a
    current format.
    """
    if not isinstance(value, Mapping):
        return unavailable_async_result_evidence(
            status=status,
            artifact_ref=artifact_ref,
        )
    if value.get("schema_version") != ASYNC_RESULT_EVIDENCE_SCHEMA_VERSION:
        return unavailable_async_result_evidence(
            status=status,
            artifact_ref=artifact_ref,
            reason_code="async_result_evidence_unknown_schema",
        )
    state = str(value.get("state") or "unavailable")[:32]
    if state not in _ASYNC_RESULT_EVIDENCE_STATES:
        return unavailable_async_result_evidence(
            status=status,
            artifact_ref=artifact_ref,
            reason_code="async_result_evidence_unknown_state",
        )

    try:
        nested = validate_async_nested_sections(value)
    except NestedSchemaError as exc:
        return unavailable_async_result_evidence(
            status=status,
            artifact_ref=artifact_ref,
            reason_code=exc.reason_code,
        )

    def _safe_ref(ref: Any) -> str | None:
        if not ref:
            return None
        return str(ref).replace("\\", "/").rsplit("/", 1)[-1] or None

    workspace = nested["workspace"]
    panels = workspace.get("panels")
    panels = panels if isinstance(panels, list) else []
    safe_panels = [str(item)[:64] for item in panels[:20]]
    specs = workspace.get("view_specs")
    specs = specs if isinstance(specs, list) else []
    safe_specs = []
    for item in specs[:20]:
        if not isinstance(item, Mapping):
            continue
        spec = {}
        for key in ("id", "title", "renderer"):
            if item.get(key) is not None:
                spec[key] = str(item[key])[:120]
        if spec:
            safe_specs.append(spec)

    views = nested["views"]
    source_panels = views.get("panels")
    source_panels = source_panels if isinstance(source_panels, Mapping) else {}
    safe_view_panels = {}
    for panel_id, panel in list(source_panels.items())[:20]:
        if not isinstance(panel, Mapping):
            continue
        safe_view_panels[str(panel_id)[:64]] = {
            "kind": str(panel.get("kind") or "unknown")[:64],
            "state": str(panel.get("state") or "unavailable")[:32],
            "artifact_available": bool(panel.get("artifact_available")),
        }

    lifecycle = _normalize_lifecycle(value.get("lifecycle"), status)
    planning = value.get("planning")
    planning = planning if isinstance(planning, Mapping) else {}
    evidence_projection = project_evidence_projection(value)
    evidence_recovery = project_evidence_recovery(value)
    request_identity = normalize_request_identity(value.get("request_identity"))
    plan_identity = normalize_plan_identity(planning.get("plan_identity"))
    evidence_binding = normalize_evidence_binding(planning.get("evidence_binding"))
    timeline = normalize_execution_timeline(value.get("execution_timeline"))
    registry = evidence_projection["evidence_registry"]
    selection = evidence_projection["selection"]
    artifact = value.get("artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    ref = _safe_ref(artifact.get("ref") or artifact_ref)
    result = {
        "schema_version": ASYNC_RESULT_EVIDENCE_SCHEMA_VERSION,
        "available": bool(value.get("available")) and state != "unavailable",
        "state": state,
        "status": str(value.get("status") or status or "UNKNOWN")[:32],
        "lifecycle": lifecycle,
        "result_type": str(value.get("result_type") or "unknown")[:96],
        "request_identity": request_identity,
        "degradation_status": str(value.get("degradation_status") or "none")[:32],
        "workspace": {
            "schema_version": str(workspace.get("schema_version") or "")[:80],
            "panels": safe_panels,
            "view_specs": safe_specs,
        },
        "views": {
            "schema_version": str(
                views.get("schema_version") or "spatial-agent.views.v1"
            )[:80],
            "panels": safe_view_panels,
        },
        "artifact": {"available": bool(ref), "ref": ref},
        "planning": {
            "plan_identity": plan_identity,
            "evidence_binding": evidence_binding,
            "plan_quality": project_plan_quality_evidence(planning.get("plan_quality")),
            "workflow_selection": selection["workflow_selection"],
            "planner_selection": selection["planner_selection"],
        },
        "selection_interaction": normalize_selection_interaction(
            value.get("selection_interaction")
        ),
        "execution_timeline": timeline,
        "action_preconditions": normalize_action_preconditions(
            value.get("action_preconditions")
        ),
        "action_effect": normalize_action_effect(value.get("action_effect")),
        "evidence_registry": registry,
        "evidence_projection": evidence_projection,
        "evidence_recovery": evidence_recovery,
    }
    if isinstance(value.get("action_receipt"), Mapping):
        result["action_receipt"] = normalize_action_receipt(
            value.get("action_receipt")
        )
    for key in ("availability", "reason_code", "source"):
        if value.get(key) is not None:
            result[key] = str(value[key])[:96]
    return result


def failure_category_for(status: str, error: str = None, source: str = None) -> str:
    """Classify failures using bounded labels; never return the source error."""
    status = str(status or "").upper()
    if status == "COMPLETED":
        return None
    if status in {"CANCELLED", "CANCEL_REQUESTED"}:
        return "cancelled"
    if status == "TIMED_OUT":
        return "timeout"
    if status == "NEEDS_CLARIFICATION":
        return "clarification"
    if status == "WAITING_FOR_DECISION":
        return "decision"
    if status == "REJECTED":
        return "rejected"
    if source == "worker":
        return "worker_exception"
    text = str(error or "").lower()
    if any(token in text for token in ("timeout", "timed out", "超时")):
        return "timeout"
    if any(token in text for token in ("openai", "provider", "http", "url", "socket", "network", "api")):
        return "provider"
    if any(token in text for token in ("planner", "plan", "schema", "规划")):
        return "planning"
    if any(token in text for token in ("tool", "backend", "dataset", "raster", "栅格", "数据")):
        return "tool"
    if status == "FAILED":
        return "execution"
    return None


def async_event(status: str) -> str:
    return {
        "QUEUED": "submitted",
        "RUNNING": "started",
        "CANCEL_REQUESTED": "cancel_requested",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "TIMED_OUT": "timed_out",
        "WAITING_FOR_DECISION": "waiting_decision",
    }.get(str(status), "finished")


def as_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def round_ms(value):
    return None if value is None else round(max(0, float(value)), 3)


def epoch_to_iso(value):
    value = as_float(value)
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def duration_summary(values):
    if not values:
        return {"count": 0, "total_ms": 0.0, "average_ms": None, "max_ms": None}
    total = sum(values)
    return {
        "count": len(values),
        "total_ms": round(total, 3),
        "average_ms": round(total / len(values), 3),
        "max_ms": round(max(values), 3),
    }


# Internal aliases keep the refactored module consistent with the helper names
# the original service.py used; service.py imports the public names directly.
_as_float = as_float
_round_ms = round_ms
_epoch_to_iso = epoch_to_iso
_duration_summary = duration_summary
_failure_category = failure_category_for
_async_fingerprint = async_fingerprint
_async_event = async_event


def empty_async_metrics():
    return {
        "count": 0,
        "worker_count": 4,
        "status_counts": {},
        "failure_categories": {},
        "recovered_jobs": 0,
        "queue_wait_ms": duration_summary([]),
        "run_duration_ms": duration_summary([]),
    }


def async_worker_count() -> int:
    raw = os.environ.get("SPATIAL_AGENT_ASYNC_WORKERS", "4")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SPATIAL_AGENT_ASYNC_WORKERS must be an integer from 1 to 16") from exc
    if value < 1 or value > 16:
        raise ValueError("SPATIAL_AGENT_ASYNC_WORKERS must be an integer from 1 to 16")
    return value


def async_response(run_id: str, status: str, reused: bool) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "idempotent": bool(reused),
        "reused": bool(reused),
    }


def process_is_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not process:
                # Access-denied is not evidence that a worker exited. Treat
                # that case as alive so a second service cannot replay a job
                # while the original worker may still be writing its snapshot.
                error_code = ctypes.windll.kernel32.GetLastError()
                return error_code == 5  # ERROR_ACCESS_DENIED
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
                    return True
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(process)
        except (AttributeError, OSError, TypeError, ValueError):
            # A transient API failure must not trigger duplicate execution.
            return True
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OSError, ValueError):
        return False
    return True


def build_lineage_for_result(result: AgentRunResult) -> Dict[str, Any]:
    """Build a lineage index from a run result without mutating it."""
    from agent.trace_formatter import format_trace

    result_payload = result.to_dict()
    explicit_geometry = result_payload.pop("geometry_evidence", None)
    if explicit_geometry is not None:
        result_payload["_geometry_evidence"] = explicit_geometry
    result_payload["trace_summary"] = format_trace(result)
    return build_lineage_index(result_payload)
