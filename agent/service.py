import os
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Tuple

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import export_run_summary
from agent.provenance import build_provenance
from agent.scenario import BuildabilityComparisonScenario
from agent.trace_formatter import format_trace
from run_demo import build_runtime
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from agent.models import AgentRunResult, RunStatus
from result_contract import (
    build_comparison_lineage,
    build_history_lineage,
    build_lineage_index,
    build_result_contract,
)
from agent.workflow_templates import normalize_workflow_selection


_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.NEEDS_CLARIFICATION,
    RunStatus.REJECTED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
}


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(self, artifact_store: ArtifactStore = None, state_db_path: str = None):
        self._runtimes = {}
        self._artifact_store = artifact_store or ArtifactStore()
        self._state_db_path = state_db_path or os.environ.get("SPATIAL_AGENT_STATE_DB")
        self._state_store = SQLiteStateStore(self._state_db_path) if self._state_db_path else None
        self._conversation_store = (
            SQLiteConversationStore(self._state_db_path) if self._state_db_path else None
        )
        self._memory_session_lock = Lock()
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._async_worker_count = _async_worker_count()
        self._async_executor = ThreadPoolExecutor(
            max_workers=self._async_worker_count, thread_name_prefix="spatial-agent"
        )
        self._async_lock = Lock()
        self._async_jobs: Dict[str, Dict[str, Any]] = {}
        self._recover_async_jobs()

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
        run_id: str = None,
        _force_run_id: bool = False,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        workflow_context = _normalize_workflow_payload(workflow)
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        if run_id is not None and not _force_run_id:
            existing = (
                self._state_store.get(run_id)
                if self._state_store is not None
                else self._runtime(planner, backend).get_run(run_id)
            )
            if existing is not None:
                payload = _format_result(existing, _normalize_spatial_context(spatial_context))
                self._attach_async_observability(payload, run_id)
                return payload
        if self._conversation_store is not None:
            self._conversation_store.ensure_session(session_id)
        else:
            self._ensure_memory_session(session_id)
        normalized_context = _normalize_spatial_context(spatial_context)
        runtime = self._runtime(planner, backend)
        runtime_kwargs = {
            "session_id": session_id,
            "timeout_seconds": timeout_seconds,
            "run_id": run_id,
        }
        if workflow_context is not None:
            runtime_kwargs["workflow"] = workflow_context
        result = runtime.run(
            _contextualize_request(request, normalized_context), **runtime_kwargs
        )
        payload = result.to_dict()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
            result.artifact_ref = payload["artifact_ref"]
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                            dataset=(step.get("result") or {}).get("dataset"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"], payload["_geometry_evidence"] = _exported_geometry_evidence(payload["geojson_ref"])
            result.geometry_evidence = payload["_geometry_evidence"]
            result.geojson_ref = payload["geojson_ref"]
        payload["result"] = build_result_contract(payload)
        payload.pop("_geometry_feature_count", None)
        payload.pop("_geometry_evidence", None)
        if self._state_store is not None:
            self._state_store.save(result)
        self._attach_async_observability(payload, payload.get("run_id"))
        # Mark the durable job terminal only after every final snapshot read
        # is complete. Pollers use this marker as the worker quiescence boundary.
        self._finalize_async_job(payload)
        return payload

    def run_async(self, **kwargs) -> Dict:
        request = kwargs.get("request", "")
        session_id = kwargs.get("session_id", "default")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        planner = kwargs.get("planner", "rule")
        backend = kwargs.get("backend", "memory")
        kwargs = dict(kwargs)
        kwargs["workflow"] = _normalize_workflow_payload(kwargs.get("workflow"))
        run_id = kwargs.get("run_id")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        idempotency_key = kwargs.get("idempotency_key")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string")

        job_payload = _async_job_payload(kwargs)
        if run_id:
            idempotency_key = idempotency_key or "run_id:" + run_id.strip()
        else:
            idempotency_key = idempotency_key or _async_fingerprint(job_payload)
            run_id = str(uuid.uuid4())
        job_payload["run_id"] = run_id

        with self._async_lock:
            if self._state_store is not None:
                existing_result = self._state_store.get(run_id)
                if existing_result is not None and not self._state_store.get_async_job(run_id):
                    return self._async_submission_response(run_id, existing_result.status.value, True)
                job = self._state_store.create_async_job(
                    idempotency_key, run_id, job_payload
                )
                created = bool(job.pop("created", False))
                if not created:
                    self._ensure_async_run_snapshot(job)
                    return self._async_submission_response(
                        job["run_id"], _async_status(self._state_store, job), True
                    )
                self._state_store.save(
                    AgentRunResult(
                        run_id=run_id,
                        status=RunStatus.PLANNING,
                        request=request,
                        session_id=session_id,
                        workflow=job_payload.get("workflow"),
                    )
                )
                if not self._state_store.claim_async_job(run_id, os.getpid()):
                    # Another worker may claim the just-created job between the
                    # INSERT and this claim. The caller is still the first
                    # accepted submission, so preserve idempotent=false.
                    return self._async_submission_response(run_id, "QUEUED", False)
            else:
                job = self._async_jobs.get(idempotency_key)
                if job is not None:
                    return self._async_submission_response(
                        run_id=job["run_id"], status=job["status"], reused=True
                    )
                submitted_at = time.time()
                job = {
                    "run_id": run_id,
                    "payload": job_payload,
                    "status": "QUEUED",
                    "created_at": submitted_at,
                    "started_at": None,
                    "finished_at": None,
                    "queue_wait_ms": None,
                    "run_duration_ms": None,
                    "failure_category": None,
                    "recovery_count": 0,
                    "cancel_requested_at": None,
                    "last_event": "submitted",
                }
                self._async_jobs[idempotency_key] = job

            self._async_executor.submit(self._run_async_job, job_payload)
        return self._async_submission_response(run_id, "QUEUED", False)

    def _run_async_job(self, job_payload: Dict[str, Any]) -> None:
        run_id = job_payload["run_id"]
        kwargs = dict(job_payload)
        kwargs.pop("run_id", None)
        completed = False
        failure_category = None
        self._mark_async_started(run_id)
        try:
            payload = self.run(run_id=run_id, _force_run_id=True, **kwargs)
            status = str(payload.get("status") or "FAILED")
            completed = True
        except Exception as exc:
            status = "FAILED"
            failure_category = _failure_category(status, str(exc), source="worker")
            if self._state_store is not None:
                result = self._state_store.get(run_id)
                if result is None:
                    result = AgentRunResult(
                        run_id=run_id,
                        status=RunStatus.FAILED,
                        request=str(kwargs.get("request") or ""),
                        session_id=kwargs.get("session_id"),
                        error=str(exc),
                    )
                elif result.status in {RunStatus.CREATED, RunStatus.PLANNING, RunStatus.EXECUTING}:
                    result.status = RunStatus.FAILED
                    result.error = str(exc)
                self._state_store.save(result)
        if self._state_store is not None and not completed:
            self._state_store.finish_async_job(run_id, status, os.getpid(), failure_category)
        elif self._state_store is None:
            self._finish_memory_async_job(run_id, status, failure_category)

    def _finalize_async_job(self, payload: Dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        status = str(payload.get("status") or "FAILED")
        failure_category = _failure_category(status, payload.get("error"))
        if self._state_store is None:
            self._finish_memory_async_job(run_id, status, failure_category)
            return
        job = self._state_store.get_async_job(run_id)
        if job and job.get("owner_pid") == os.getpid():
            self._state_store.finish_async_job(
                run_id, status, os.getpid(), failure_category
            )

    def _recover_async_jobs(self) -> None:
        if self._state_store is None:
            return
        for job in self._state_store.list_recoverable_async_jobs(os.getpid()):
            run_id = job["run_id"]
            owner_pid = job.get("owner_pid")
            if owner_pid and owner_pid != os.getpid() and _process_is_alive(owner_pid):
                continue
            if not self._state_store.claim_async_job(
                run_id,
                os.getpid(),
                recover=True,
                previous_owner_pid=owner_pid,
            ):
                continue
            self._async_executor.submit(self._run_async_job, job["payload"])

    def _ensure_async_run_snapshot(self, job: Dict[str, Any]) -> None:
        """Close the idempotent-submit window before a caller starts polling."""
        if self._state_store is None or not isinstance(job, dict):
            return
        if str(job.get("status") or "") not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
            return
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        self._state_store.ensure_run_snapshot(
            AgentRunResult(
                run_id=str(job.get("run_id") or ""),
                status=RunStatus.PLANNING,
                request=str(payload.get("request") or ""),
                session_id=payload.get("session_id"),
                workflow=payload.get("workflow"),
            )
        )

    def _mark_async_started(self, run_id: str) -> None:
        """SQLite claims record the start atomically; memory mode needs the same data."""
        if self._state_store is not None:
            return
        now = time.time()
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = "RUNNING"
                job["started_at"] = job.get("started_at") or now
                if job.get("queue_wait_ms") is None:
                    job["queue_wait_ms"] = max(0, (now - job["created_at"]) * 1000)
                job["last_event"] = "started"
                return

    def _finish_memory_async_job(
        self, run_id: str, status: str, failure_category: str = None
    ) -> None:
        finished_at = time.time()
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") != run_id:
                    continue
                job["status"] = status
                job["finished_at"] = finished_at
                started_at = job.get("started_at")
                if started_at is not None:
                    job["run_duration_ms"] = max(0, (finished_at - started_at) * 1000)
                job["failure_category"] = failure_category
                job["last_event"] = _async_event(status)
                return

    def get_async_observability(self, run_id: str) -> Dict[str, Any]:
        """Return a bounded lifecycle summary with no request or error text."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        job = self._state_store.get_async_job(run_id) if self._state_store else None
        if job is None:
            with self._async_lock:
                job = next(
                    (item for item in self._async_jobs.values() if item.get("run_id") == run_id),
                    None,
                )
        if job is None:
            raise ValueError("async run not found: " + run_id)
        result = self._state_store.get(run_id) if self._state_store else self._memory_run(run_id)
        lineage = None
        if result is not None:
            result_payload = result.to_dict()
            explicit_geometry = result_payload.pop("geometry_evidence", None)
            if explicit_geometry is not None:
                result_payload["_geometry_evidence"] = explicit_geometry
            result_payload["trace_summary"] = format_trace(result)
            lineage = build_lineage_index(result_payload)
        return _build_async_observability(job, result, lineage=lineage)

    def _async_submission_response(self, run_id: str, status: str, reused: bool) -> Dict[str, Any]:
        response = _async_response(run_id, status, reused)
        try:
            response["async_observability"] = self.get_async_observability(run_id)
        except ValueError:
            pass
        return response

    def _attach_async_observability(self, payload: Dict[str, Any], run_id: str) -> None:
        if not run_id:
            return
        try:
            payload["async_observability"] = self.get_async_observability(run_id)
        except ValueError:
            return

    def _mark_memory_cancel_requested(self, run_id: str) -> None:
        with self._async_lock:
            for job in self._async_jobs.values():
                if job.get("run_id") == run_id and job.get("status") in {"QUEUED", "RUNNING"}:
                    job["status"] = "CANCEL_REQUESTED"
                    job["cancel_requested_at"] = time.time()
                    job["last_event"] = "cancel_requested"
                    return

    def _memory_run(self, run_id: str):
        for runtime in self._runtimes.values():
            result = runtime.get_run(run_id)
            if result is not None:
                return result
        return None

    def retry(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
    ) -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        runtime = self._runtime(planner, backend)
        result = runtime.retry_failed(run_id)
        payload = result.to_dict()
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        payload["result_type"] = _result_type(payload)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
            result.artifact_ref = payload["artifact_ref"]
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                            dataset=(step.get("result") or {}).get("dataset"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"], payload["_geometry_evidence"] = _exported_geometry_evidence(payload["geojson_ref"])
            result.geometry_evidence = payload["_geometry_evidence"]
            result.geojson_ref = payload["geojson_ref"]
        payload["result"] = build_result_contract(payload)
        payload.pop("_geometry_feature_count", None)
        payload.pop("_geometry_evidence", None)
        if self._state_store is not None:
            self._state_store.save(result)
        return payload

    def cancel(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = self._runtime(planner, backend).cancel(run_id)
        if self._state_store is None:
            self._mark_memory_cancel_requested(run_id)
        return {
            "run_id": run_id,
            "status": "CANCEL_REQUESTED",
            "current_status": result.status.value,
        }

    def get_run(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = None
        # A terminal run snapshot can be written just before the durable async
        # job marker is finalized. Wait long enough for readers to observe one
        # consistent terminal state instead of returning while the worker
        # still owns the SQLite file.
        for _ in range(1000):
            result = (
                self._state_store.get(run_id)
                if self._state_store is not None
                else self._runtime(planner, backend).get_run(run_id)
            )
            if result is None or self._state_store is None:
                break
            job = self._state_store.get_async_job(run_id)
            if (
                result.status in _TERMINAL_RUN_STATUSES
                and job is not None
                and job.get("status") in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
            ):
                time.sleep(0.005)
                continue
            break
        if result is None:
            raise ValueError("run not found: " + run_id)
        payload = result.to_dict()
        explicit_geometry = payload.pop("geometry_evidence", None)
        if explicit_geometry is not None:
            payload["_geometry_evidence"] = explicit_geometry
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(payload)
        payload.pop("_geometry_evidence", None)
        self._attach_async_observability(payload, run_id)
        return payload

    def list_runs(self, limit: int = 20) -> Dict:
        if self._state_store is not None:
            records = self._state_store.list_runs(limit=limit)
        else:
            records = self._artifact_store.list_runs(limit=limit)
        return {"runs": _attach_history_lineage(records)}

    def list_session_runs(self, session_id: str, limit: int = 20) -> Dict:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if self._state_store is None:
            records = []
            for runtime in self._runtimes.values():
                records.extend(runtime._state_store.list_runs(limit=limit, session_id=session_id))
            records = _dedupe_run_records(records)
            return {"runs": _attach_history_lineage(records[:limit])}
        return {"runs": _attach_history_lineage(
            self._state_store.list_runs(limit=limit, session_id=session_id)
        )}

    def list_sessions(self, limit: int = 50) -> Dict:
        if self._conversation_store is None:
            if limit < 1:
                raise ValueError("limit must be positive")
            with self._memory_session_lock:
                sessions = list(self._memory_sessions.values())
            return {"sessions": sessions[-limit:][::-1]}
        return {"sessions": self._conversation_store.list_sessions(limit=limit)}

    def create_session(self) -> Dict:
        if self._conversation_store is None:
            with self._memory_session_lock:
                number = 1
                while "conversation-{}".format(number) in self._memory_sessions:
                    number += 1
                session_id = "conversation-{}".format(number)
                session = {"session_id": session_id, "display_name": "对话{}".format(number)}
                self._memory_sessions[session_id] = session
                return dict(session)
        return self._conversation_store.create_session()

    def clear_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state_store.clear_session_runs(session_id) if self._state_store else 0
        if self._conversation_store:
            self._conversation_store.clear_session(session_id)
        else:
            for runtime in self._runtimes.values():
                cleared_runs += runtime._state_store.clear_session_runs(session_id)
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "cleared_runs": cleared_runs}

    def delete_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state_store.clear_session_runs(session_id) if self._state_store else 0
        deleted = self._conversation_store.delete_session(session_id) if self._conversation_store else False
        if self._conversation_store is None:
            for runtime in self._runtimes.values():
                cleared_runs += runtime._state_store.clear_session_runs(session_id)
            with self._memory_session_lock:
                deleted = self._memory_sessions.pop(session_id, None) is not None
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "deleted": deleted, "cleared_runs": cleared_runs}

    def _ensure_memory_session(self, session_id: str) -> None:
        with self._memory_session_lock:
            if session_id in self._memory_sessions:
                return
            self._memory_sessions[session_id] = {
                "session_id": session_id,
                "display_name": _memory_session_display_name(session_id),
            }

    def metrics(self) -> Dict:
        if self._state_store is not None:
            metrics = self._state_store.metrics()
            metrics.setdefault("async_jobs", {})["worker_count"] = self._async_worker_count
            return metrics
        metrics = self._artifact_store.metrics()
        metrics["async_jobs"] = self._memory_async_metrics()
        return metrics

    def _memory_async_metrics(self) -> Dict[str, Any]:
        with self._async_lock:
            jobs = list(self._async_jobs.values())
        status_counts: Dict[str, int] = {}
        failure_categories: Dict[str, int] = {}
        queue_waits = []
        run_durations = []
        recovered_jobs = 0
        for job in jobs:
            observation = _build_async_observability(job)
            status = observation["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            category = observation.get("failure_category")
            if category:
                failure_categories[category] = failure_categories.get(category, 0) + 1
            if observation.get("queue_wait_ms") is not None:
                queue_waits.append(observation["queue_wait_ms"])
            if observation.get("run_duration_ms") is not None:
                run_durations.append(observation["run_duration_ms"])
            if observation.get("recovered"):
                recovered_jobs += 1
        return {
            "count": len(jobs),
            "worker_count": self._async_worker_count,
            "status_counts": status_counts,
            "failure_categories": failure_categories,
            "recovered_jobs": recovered_jobs,
            "queue_wait_ms": _duration_summary(queue_waits),
            "run_duration_ms": _duration_summary(run_durations),
        }

    def compare_buildability(
        self,
        admin_name: str,
        thresholds,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict:
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        scenario = BuildabilityComparisonScenario.for_thresholds(admin_name, thresholds)
        admin_name = scenario.admin_names[0]
        rows = []
        for value in scenario.thresholds:
            result = self.run(
                f"分析{admin_name}建设适宜性，坡度不超过{value:g}度",
                session_id=f"comparison-{admin_name}-{value:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
            )
            step = next((item for item in result.get("steps", []) if item.get("tool") == "get_zonal_buildability_analysis"), {})
            tool_result = step.get("result") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append({
                "run_id": result.get("run_id"),
                "slope_limit_degrees": value,
                "status": result.get("status"),
                "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                "valid_pixel_count": statistics.get("valid_pixel_count"),
                "candidate_ratio": statistics.get("candidate_ratio"),
                "error": statistics.get("error") or result.get("error"),
                "analysis_ready": _analysis_ready_summary(result),
                "lineage": (result.get("result") or {}).get("lineage"),
            })
        evidence = next(
            (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
            None,
        )
        return {
            "admin_name": admin_name,
            "thresholds": list(scenario.thresholds),
            "scenario": scenario.to_dict(),
            "spatial_context": normalized_context,
            "results": rows,
            "lineage": build_comparison_lineage(rows, "buildability_threshold_comparison"),
            **({"analysis_ready": evidence} if evidence else {}),
        }

    def compare_buildability_regions(
        self,
        admin_names,
        threshold: float = 20,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict:
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold must be a number") from exc
        scenario = BuildabilityComparisonScenario.for_regions(admin_names, threshold_value)
        names = list(scenario.admin_names)
        rows = []
        for admin_name in names:
            result = self.compare_buildability(
                admin_name=admin_name,
                thresholds=[threshold_value],
                planner=planner,
                backend=backend,
            )
            row = (result.get("results") or [{}])[0]
            rows.append({"admin_name": admin_name, **row})
        return {
            "admin_names": names,
            "slope_limit_degrees": threshold_value,
            "scenario": scenario.to_dict(),
            "results": rows,
            "lineage": build_comparison_lineage(rows, "buildability_region_comparison"),
            **({
                "analysis_ready": next(
                    (row.get("analysis_ready") for row in rows if row.get("analysis_ready")),
                    None,
                )
            } if any(row.get("analysis_ready") for row in rows) else {}),
        }

    def _runtime(self, planner: str, backend: str):
        key = _runtime_key(planner, backend)
        if key not in self._runtimes:
            self._runtimes[key] = build_runtime(
                planner,
                backend,
                state_store=self._state_store,
                conversation_store=self._conversation_store,
            )
        return self._runtimes[key]


def _async_job_payload(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the persisted submission limited to arguments accepted by run()."""
    return {
        "request": kwargs.get("request", ""),
        "session_id": kwargs.get("session_id", "default"),
        "planner": kwargs.get("planner", "rule"),
        "backend": kwargs.get("backend", "memory"),
        "export_artifact": bool(kwargs.get("export_artifact", False)),
        "export_geojson": bool(kwargs.get("export_geojson", False)),
        "geojson_max_features": kwargs.get("geojson_max_features", 100),
        "timeout_seconds": kwargs.get("timeout_seconds"),
        "spatial_context": kwargs.get("spatial_context"),
        "workflow": kwargs.get("workflow"),
    }


def _async_fingerprint(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return "request:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _async_status(state_store: SQLiteStateStore, job: Dict[str, Any]) -> str:
    if job.get("status") == "CANCEL_REQUESTED":
        return "CANCEL_REQUESTED"
    result = state_store.get(job["run_id"])
    if result is not None:
        return result.status.value
    return "QUEUED" if job.get("status") in {"QUEUED", "RUNNING"} else str(job.get("status"))


def _build_async_observability(
    job: Dict[str, Any],
    result: AgentRunResult = None,
    lineage: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build a request-free lifecycle contract for polling and metrics consumers."""
    status = str(job.get("status") or "UNKNOWN")
    result_status = result.status.value if result is not None else None
    if result_status in {item.value for item in _TERMINAL_RUN_STATUSES}:
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
        failure_category = _failure_category(
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
        "request_fingerprint": _async_fingerprint(job.get("payload") or {}),
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


def _failure_category(status: str, error: str = None, source: str = None) -> str:
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


def _async_event(status: str) -> str:
    return {
        "QUEUED": "submitted",
        "RUNNING": "started",
        "CANCEL_REQUESTED": "cancel_requested",
        "COMPLETED": "completed",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "TIMED_OUT": "timed_out",
    }.get(str(status), "finished")


def _as_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _round_ms(value):
    return None if value is None else round(max(0, float(value)), 3)


def _epoch_to_iso(value):
    value = _as_float(value)
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _duration_summary(values):
    if not values:
        return {"count": 0, "total_ms": 0.0, "average_ms": None, "max_ms": None}
    total = sum(values)
    return {
        "count": len(values),
        "total_ms": round(total, 3),
        "average_ms": round(total / len(values), 3),
        "max_ms": round(max(values), 3),
    }


def _empty_async_metrics():
    return {
        "count": 0,
        "worker_count": 4,
        "status_counts": {},
        "failure_categories": {},
        "recovered_jobs": 0,
        "queue_wait_ms": _duration_summary([]),
        "run_duration_ms": _duration_summary([]),
    }


def _async_worker_count() -> int:
    raw = os.environ.get("SPATIAL_AGENT_ASYNC_WORKERS", "4")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SPATIAL_AGENT_ASYNC_WORKERS must be an integer from 1 to 16") from exc
    if value < 1 or value > 16:
        raise ValueError("SPATIAL_AGENT_ASYNC_WORKERS must be an integer from 1 to 16")
    return value


def _memory_session_display_name(session_id: str) -> str:
    if session_id.startswith("conversation-"):
        suffix = session_id[len("conversation-"):]
        if suffix.isdigit():
            return "对话" + suffix
    return session_id


def _dedupe_run_records(records):
    seen = set()
    result = []
    for record in records:
        run_id = record.get("run_id")
        if run_id in seen:
            continue
        seen.add(run_id)
        result.append(record)
    return result


def _attach_history_lineage(records):
    """Attach only navigational evidence indexes to compact history records."""
    enriched = []
    for record in records or []:
        item = dict(record or {})
        item["lineage"] = build_history_lineage(item)
        enriched.append(item)
    return enriched


def _async_response(run_id: str, status: str, reused: bool) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "idempotent": bool(reused),
        "reused": bool(reused),
    }


def _process_is_alive(pid: int) -> bool:
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


def _runtime_key(planner: str, backend: str) -> Tuple[str, str]:
    if planner not in ("rule", "openai"):
        raise ValueError("planner must be one of: rule, openai")
    if backend not in ("memory", "local"):
        raise ValueError("backend must be one of: memory, local")
    return planner, backend


def _validate_session_id(session_id: str) -> None:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")


def _normalize_workflow_payload(workflow: Dict[str, Any]) -> Dict[str, Any] | None:
    if workflow is None:
        return None
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be an object")
    template_id = workflow.get("template_id")
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError("workflow.template_id must be a non-empty string")
    return normalize_workflow_selection(
        template_id.strip(),
        workflow.get("constraints", {}),
        workflow.get("evidence"),
    )


def _normalize_spatial_context(context: Dict[str, Any]) -> Dict[str, Any]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise ValueError("spatial_context must be an object")
    normalized = {}
    for key in ("admin_name", "source", "crs", "geometry_type"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()[:160]
    if context.get("geometry_available") is True:
        normalized["geometry_available"] = True
    return normalized


def _contextualize_request(request: str, context: Dict[str, Any]) -> str:
    admin_name = context.get("admin_name")
    if not admin_name:
        return request
    return f"{request}（当前地图选中区域：{admin_name}）"


def _tag_geometry_features(features, source=None, crs=None, source_crs=None, dataset=None):
    """Keep CRS/source beside each feature when result collections are merged."""
    tagged = []
    crs_name = _crs_name(crs)
    for feature in features or []:
        if not isinstance(feature, dict):
            continue
        properties = dict(feature.get("properties") or {})
        if source:
            properties["geometry_source"] = source
        if crs_name:
            properties["geometry_crs"] = crs_name
        if source_crs:
            properties["geometry_source_crs"] = source_crs
        if dataset:
            properties["dataset"] = dataset
        tagged.append({**feature, "properties": properties})
    return tagged


def _result_type(payload: Dict) -> str:
    return str(((payload.get("plan") or {}).get("output") or {}).get("type") or "unknown")


def _crs_name(crs):
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        return (crs.get("properties") or {}).get("name")
    if isinstance(crs, list) and len(crs) == 1:
        return _crs_name(crs[0])
    return None


def _geometry_evidence_for_features(features):
    features = [
        item for item in features or []
        if isinstance(item, dict) and item.get("geometry")
    ]
    if not features:
        return {
            "status": "no_geometry",
            "reason": "导出摘要没有可绘制空间要素",
            "feature_count": 0,
            "truncated": False,
        }
    sources = {
        str((item.get("properties") or {}).get("geometry_source"))
        for item in features
        if (item.get("properties") or {}).get("geometry_source")
    }
    status = "boundary_geometry" if sources == {"geojson"} else "real_geometry"
    return {
        "status": status,
        "reason": "导出摘要包含可绘制空间要素",
        "feature_count": len(features),
        "truncated": any(
            bool((item.get("properties") or {}).get("geometry_truncated"))
            for item in features
        ),
        "sources": sorted(sources),
    }


def _exported_geometry_evidence(geojson_ref):
    """Measure the bounded artifact, not the pre-truncation feature list."""
    path = Path(str(geojson_ref))
    if not path.exists():
        return 0, {
            "status": "unknown",
            "reason": "GeoJSON 导出文件不存在",
            "feature_count": 0,
            "truncated": False,
            "sources": [],
        }
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, {
            "status": "unknown",
            "reason": "GeoJSON 导出文件无法读取",
            "feature_count": 0,
            "truncated": False,
            "sources": [],
        }
    features = [item for item in document.get("features", []) if isinstance(item, dict)]
    evidence = _geometry_evidence_for_features(features)
    truncated = bool((document.get("properties") or {}).get("geometry_truncated"))
    if truncated:
        evidence["status"] = "truncated_geometry"
        evidence["reason"] = "GeoJSON 摘要达到大小上限，空间要素已截断"
        evidence["truncated"] = True
    return len([item for item in features if item.get("geometry")]), evidence


def _analysis_ready_summary(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    """Keep comparison responses tied to the same bounded health evidence."""
    health = next(
        (
            step.get("result") or {}
            for step in payload.get("steps", [])
            if step.get("tool") == "get_dataset_health_report"
        ),
        {},
    )
    evidence = health.get("analysis_ready")
    if not isinstance(evidence, dict):
        return None
    return {
        "status": evidence.get("status", "unknown"),
        "required": bool(evidence.get("required", False)),
        "derived_version": str(evidence.get("derived_version", "unknown"))[:128],
        "target_grid": dict(evidence.get("target_grid") or {}),
        "grid_alignment": dict(evidence.get("grid_alignment") or {}),
        "verification_mode": evidence.get("verification_mode", "metadata"),
        "data_readiness": health.get("data_readiness", "unknown"),
        **({"source_binding": {
            "binding_version": evidence["source_binding"].get("binding_version"),
            "fingerprint": str(evidence["source_binding"].get("fingerprint", ""))[:80],
            "verification_mode": evidence["source_binding"].get("verification_mode", "sha256"),
            "datasets": list(evidence["source_binding"].get("datasets") or [])[:10],
            "status": evidence["source_binding"].get("status", "recorded"),
        }} if isinstance(evidence.get("source_binding"), dict) else {}),
        **({"output_manifest": {
            "status": evidence["output_manifest"].get("status", "unknown"),
            "verification_mode": evidence["output_manifest"].get("verification_mode", "metadata"),
            "hashes_verified": bool(evidence["output_manifest"].get("hashes_verified", False)),
            "verified_files": int(evidence["output_manifest"].get("verified_files") or 0),
            "mismatch_count": int(evidence["output_manifest"].get("mismatch_count") or 0),
            "outputs": {
                str(name)[:32]: {
                    "reported": str(item.get("reported", ""))[:160],
                    "manifest": [str(value)[:160] for value in (item.get("manifest") or [])[:3]],
                    "matched": bool(item.get("matched", False)),
                }
                for name, item in (evidence["output_manifest"].get("outputs") or {}).items()
                if isinstance(item, dict)
            },
        }} if isinstance(evidence.get("output_manifest"), dict) else {}),
    }


def _format_result(result: AgentRunResult, spatial_context: Dict[str, Any]) -> Dict[str, Any]:
    payload = result.to_dict()
    explicit_geometry = payload.pop("geometry_evidence", None)
    if explicit_geometry is not None:
        payload["_geometry_evidence"] = explicit_geometry
    payload["spatial_context"] = spatial_context
    payload["trace_summary"] = format_trace(result)
    payload["provenance"] = build_provenance(payload)
    payload["result_type"] = _result_type(payload)
    payload["result"] = build_result_contract(payload)
    payload.pop("_geometry_evidence", None)
    return payload
