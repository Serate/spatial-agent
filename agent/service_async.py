"""Async job lifecycle helpers shared by the service facade and entry points.

Pure helpers: they never touch the executor or the job dict directly owned by
AgentService. The facade keeps ownership of worker submission and recovery;
this module provides the observability contract, failure classification,
timing utilities, and process-liveness checks.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from agent.models import AgentRunResult
from agent.sqlite_store import SQLiteStateStore
from result_contract import build_lineage_index


_TERMINAL_RUN_STATUSES = {
    "COMPLETED",
    "NEEDS_CLARIFICATION",
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
    return observation


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
