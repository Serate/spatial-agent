"""Durable Composite run application built on the shared async lifecycle.

The M276 coordinator remains a transport-neutral component executor.  This
module owns only the run boundary: persistence scope, artifact publication,
async idempotency/claim/recovery, and bounded read projections.  It injects
the existing :class:`AsyncApplication` instead of creating a second worker
state machine.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from typing import Any, Callable, Optional

from agent.artifact_store import ArtifactStore
from agent.application.async_runs import AsyncApplication
from agent.application.composite import CompositeApplication
from agent.composite_contract import normalize_composite_request
from agent.composite_view import build_composite_view_projection
from agent.contract_versions import COMPOSITE_COORDINATOR_SCHEMA_VERSION
from agent.models import AgentRunResult, RunStatus
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from agent.runtime_context import build_runtime_context
from agent.runtime_core.composite_taskplan import project_task_plan_bridge
from agent.service_async import process_is_alive
from agent.service_state import ServiceState


COMPOSITE_RUN_SCOPE = "composite"


class _CompositeRuntime:
    """Minimal runtime identity used only by shared async evidence helpers."""

    def result_registry(self):
        return None


def _runtime_context(planner: str, backend: str) -> dict[str, Any]:
    return build_runtime_context(
        domain_id=COMPOSITE_RUN_SCOPE,
        planner=planner,
        backend=backend,
        tool_provider={"id": "composite-coordinator", "tool_count": 0},
    )


class CompositeRunApplication:
    """Persist and execute Composite requests through shared lifecycle seams."""

    schema_version = COMPOSITE_COORDINATOR_SCHEMA_VERSION

    def __init__(
        self,
        *,
        coordinator: CompositeApplication,
        state: Any = None,
        artifact_store: ArtifactStore | None = None,
        state_db_path: str | None = None,
        artifact_root: str = "outputs/runs",
        worker_count: int = 1,
    ) -> None:
        if coordinator is None or not callable(getattr(coordinator, "run", None)):
            raise ValueError("coordinator must expose run()")
        self._coordinator = coordinator
        self._state = state or ServiceState(
            state_db_path=state_db_path or os.environ.get("SPATIAL_AGENT_STATE_DB"),
            runtime_factory=lambda _planner, _backend, **_kwargs: _CompositeRuntime(),
            domain_id=COMPOSITE_RUN_SCOPE,
            legacy_domain_id=COMPOSITE_RUN_SCOPE,
        )
        self._artifact_store = artifact_store or ArtifactStore(
            artifact_root,
            legacy_domain_id=COMPOSITE_RUN_SCOPE,
        )
        self._memory_results: dict[str, AgentRunResult] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, int(worker_count))),
            thread_name_prefix="spatial-agent-composite",
        )
        self._closed = False
        self._async = AsyncApplication(
            artifact_store=self._artifact_store,
            state=self._state,
            runtime_provider=lambda _planner, _backend: _CompositeRuntime(),
            memory_result_provider=lambda run_id: self._memory_results.get(run_id),
            run_provider=self._run_async_provider,
            domain_id_provider=lambda _planner, _backend: COMPOSITE_RUN_SCOPE,
            resolved_domain_id=lambda: COMPOSITE_RUN_SCOPE,
            configured_domain_id=lambda: COMPOSITE_RUN_SCOPE,
            normalize_workflow=lambda value, _planner, _backend: (
                dict(value) if isinstance(value, Mapping) else {}
            ),
            submission_runtime_context=_runtime_context,
            runtime_context_provider=_runtime_context,
            process_is_alive=process_is_alive,
            submit_job=lambda function, payload: self._executor.submit(function, payload),
            worker_count=max(1, min(4, int(worker_count))),
        )
        self._state.start_reaper()
        self._async.recover()

    def run(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        export_artifact: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_composite_request(request)
        return self._execute_and_persist(
            normalized,
            session_id=session_id,
            export_artifact=export_artifact,
        )

    def run_with_planning(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        export_artifact: bool = False,
        planner_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a canonical request while preserving bounded planner evidence."""
        normalized = normalize_composite_request(request)
        return self._execute_and_persist(
            normalized,
            session_id=session_id,
            export_artifact=export_artifact,
            planning_evidence=_safe_planning_evidence(planner_evidence),
        )

    def submit_async(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        idempotency_key: str | None = None,
        export_artifact: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_composite_request(request)
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._async.submit(
            request=encoded,
            session_id=session_id,
            planner=COMPOSITE_RUN_SCOPE,
            backend=COMPOSITE_RUN_SCOPE,
            export_artifact=export_artifact,
            idempotency_key=idempotency_key,
        )

    def submit_async_with_planning(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        idempotency_key: str | None = None,
        export_artifact: bool = False,
        planner_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit without changing the request contract or losing evidence."""
        normalized = normalize_composite_request(request)
        evidence = _safe_planning_evidence(planner_evidence)
        payload: Mapping[str, Any] = normalized
        if evidence:
            payload = {"request": normalized, "_planner_evidence": evidence}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self._async.submit(
            request=encoded,
            session_id=session_id,
            planner=COMPOSITE_RUN_SCOPE,
            backend=COMPOSITE_RUN_SCOPE,
            export_artifact=export_artifact,
            idempotency_key=idempotency_key,
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        safe_id = _safe_run_id(run_id)
        result = self._state.get_run(safe_id, domain_id=COMPOSITE_RUN_SCOPE) if safe_id and self._state.persistent else None
        artifact_recovered = False
        if result is None and safe_id:
            result = self._memory_results.get(safe_id)
        if result is None and safe_id:
            artifact = self._artifact_store.read_run(
                safe_id, domain_id=COMPOSITE_RUN_SCOPE
            )
            if isinstance(artifact, dict):
                artifact_result = artifact.get("result")
                if isinstance(artifact_result, Mapping):
                    return _response_from_result(
                        artifact_result,
                        run_id=safe_id,
                        artifact_ref=artifact.get("artifact_ref"),
                        artifact_recovered=True,
                    )
        if result is None:
            raise ValueError("composite run not found: " + str(run_id))
        return _response_from_result(
            result.result or {},
            run_id=result.run_id,
            artifact_ref=result.artifact_ref,
            artifact_recovered=artifact_recovered,
        )

    def get_observability(self, run_id: str) -> dict[str, Any]:
        return self._async.get_observability(_safe_required_run_id(run_id))

    def get_evidence(self, run_id: str) -> dict[str, Any]:
        detail = self.get_run(run_id)
        result = detail.get("result") if isinstance(detail, dict) else {}
        return {
            "schema_version": "spatial-agent.evidence-reference.v1",
            "run_id": detail.get("run_id"),
            "domain_id": COMPOSITE_RUN_SCOPE,
            "planner_evidence": result.get("planner_evidence") or {},
            "artifact": {
                "available": bool(detail.get("artifact_ref")),
                "ref": _safe_name(detail.get("artifact_ref")),
            },
            "evidence_registry": result.get("evidence_registry") or {"available": False},
            "evidence_recovery": result.get("evidence_recovery") or {"available": False},
        }

    def get_view(self, run_id: str) -> dict[str, Any]:
        """Return the same bounded user projection used by every transport."""

        detail = self.get_run(run_id)
        projection = detail.get("view") if isinstance(detail, Mapping) else None
        if not isinstance(projection, Mapping):
            result = detail.get("result") if isinstance(detail, Mapping) else None
            projection = build_composite_view_projection(result or {})
        projection = dict(projection)
        projection["run_id"] = detail.get("run_id") or projection.get("run_id")
        return projection

    def recover(self) -> int:
        return self._async.recover()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._state.stop_reaper()
        self._executor.shutdown(wait=True)
        self._state.observability.close()

    def _run_async_provider(self, **kwargs: Any) -> dict[str, Any]:
        run_id = _safe_required_run_id(kwargs.pop("run_id", None))
        encoded = kwargs.pop("request", "")
        try:
            request = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise ValueError("composite async request is invalid") from exc
        planning_evidence = None
        if isinstance(request, Mapping) and isinstance(request.get("request"), Mapping):
            planning_evidence = _safe_planning_evidence(request.get("_planner_evidence"))
            request = request["request"]
        response = self._execute_and_persist(
            normalize_composite_request(request),
            session_id=str(kwargs.get("session_id") or "default"),
            run_id=run_id,
            export_artifact=bool(kwargs.get("export_artifact", False)),
            async_requested=True,
            planning_evidence=planning_evidence,
        )
        self._async.finalize_job(response)
        if response.get("artifact_ref"):
            self._rewrite_async_artifact(run_id)
        return response

    def _execute_and_persist(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str,
        run_id: str | None = None,
        export_artifact: bool,
        async_requested: bool = False,
        planning_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._coordinator.run(
            request,
            session_id=session_id,
            run_id=run_id,
        )
        canonical = response.get("result")
        if not isinstance(canonical, Mapping):
            raise ValueError("composite coordinator returned no result contract")
        canonical = normalize_result_contract(canonical)
        if planning_evidence:
            canonical = dict(canonical)
            canonical["planner_evidence"] = dict(planning_evidence)
        actual_run_id = _safe_required_run_id(response.get("run_id"))
        snapshot = AgentRunResult(
            run_id=actual_run_id,
            status=_run_status(response.get("status")),
            request=str(request.get("request") or "")[:2000],
            session_id=str(session_id or "default")[:120],
            domain_id=COMPOSITE_RUN_SCOPE,
            runtime_context=_runtime_context(COMPOSITE_RUN_SCOPE, COMPOSITE_RUN_SCOPE),
            result=canonical,
            answer=str(canonical.get("summary") or "")[:1200] or None,
        )
        self._memory_results[actual_run_id] = snapshot
        self._state.save_run(snapshot)
        response = dict(response)
        response["run_id"] = actual_run_id
        response["result"] = canonical
        if export_artifact:
            payload = snapshot.to_dict()
            if async_requested:
                payload["_async_requested"] = True
            artifact_ref = self._artifact_store.write_run(payload)
            snapshot.artifact_ref = artifact_ref
            self._state.save_run(snapshot)
            response["artifact_ref"] = artifact_ref
        return response

    def _rewrite_async_artifact(self, run_id: str) -> None:
        snapshot = self._state.get_run(run_id, domain_id=COMPOSITE_RUN_SCOPE)
        if snapshot is None:
            snapshot = self._memory_results.get(run_id)
        if snapshot is None or not snapshot.artifact_ref:
            return
        payload = snapshot.to_dict()
        payload["_async_requested"] = True
        payload["async_observability"] = self._async.get_observability(run_id)
        self._artifact_store.write_run(payload)


def _run_status(value: Any) -> RunStatus:
    normalized = str(value or "FAILED").upper()
    if normalized in {"COMPLETED", "PARTIAL"}:
        return RunStatus.COMPLETED
    if normalized in {"BLOCKED", "NEEDS_CLARIFICATION"}:
        return RunStatus.NEEDS_CLARIFICATION
    try:
        return RunStatus(normalized)
    except ValueError:
        return RunStatus.FAILED


def _safe_planning_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = {
        "schema_version",
        "planner_source",
        "schema_status",
        "component_count",
        "request_fingerprint",
        "context_fingerprint",
        "context_schema_version",
        "compatibility",
        "task_plan_bridge",
    }
    result = {key: value[key] for key in allowed if key in value}
    result["schema_version"] = str(
        result.get("schema_version") or "spatial-agent.composite-planner-evidence.v1"
    )[:96]
    result["planner_source"] = str(result.get("planner_source") or "unknown")[:32]
    result["schema_status"] = str(result.get("schema_status") or "unknown")[:32]
    try:
        result["component_count"] = max(0, min(8, int(result.get("component_count") or 0)))
    except (TypeError, ValueError):
        result["component_count"] = 0
    for key in (
        "request_fingerprint",
        "context_fingerprint",
        "context_schema_version",
    ):
        if key in result:
            result[key] = str(result[key] or "")[:128] or None
    compatibility = result.get("compatibility")
    if isinstance(compatibility, Mapping):
        result["compatibility"] = {
            "status": str(compatibility.get("status") or "identity")[:32],
            "actions": [str(item)[:96] for item in (compatibility.get("actions") or [])[:16]],
        }
    else:
        result.pop("compatibility", None)
    if "task_plan_bridge" in result:
        result["task_plan_bridge"] = project_task_plan_bridge(
            result.get("task_plan_bridge")
        )
    return result


def _response_from_result(
    result: Mapping[str, Any],
    *,
    run_id: str,
    artifact_ref: Any = None,
    artifact_recovered: bool = False,
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("composite result is invalid")
    composite = result.get("composite") if isinstance(result.get("composite"), Mapping) else {}
    state = str(composite.get("state") or "failed")
    status = {"completed": "COMPLETED", "partial": "PARTIAL", "blocked": "BLOCKED", "failed": "FAILED"}.get(state, "FAILED")
    response = {
        "schema_version": COMPOSITE_COORDINATOR_SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "state": state,
        "request_fingerprint": (composite.get("request") or {}).get("fingerprint"),
        "components": composite.get("components") or [],
        "result": dict(result),
    }
    response["view"] = build_composite_view_projection(result)
    if artifact_ref:
        response["artifact_ref"] = artifact_ref
    if artifact_recovered:
        response["artifact_recovered"] = True
    return response


def _safe_required_run_id(value: Any) -> str:
    safe = _safe_run_id(value)
    if not safe:
        raise ValueError("run_id must be a safe non-empty string")
    return safe


def _safe_run_id(value: Any) -> str | None:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 128 or "/" in candidate or "\\" in candidate:
        return None
    return candidate


def _safe_name(value: Any) -> str | None:
    if not value:
        return None
    return str(value).replace("\\", "/").rsplit("/", 1)[-1][:160]


__all__ = ["COMPOSITE_RUN_SCOPE", "CompositeRunApplication"]
