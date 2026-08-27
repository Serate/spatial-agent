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
from agent.answer_generation import (
    fallback_composite_answer,
    project_answer_generation_evidence,
)
from agent.analysis_intent import AnalysisIntentError, normalize_analysis_intent
from agent.application.async_runs import AsyncApplication
from agent.application.composite import CompositeApplication
from agent.composite_contract import (
    CompositeContractError,
    build_composite_result_contract,
    normalize_composite_request,
    normalize_composite_section,
)
from agent.composite_view import build_composite_view_projection
from agent.contract_versions import COMPOSITE_COORDINATOR_SCHEMA_VERSION
from agent.failure_contract import build_failure_evidence
from agent.models import AgentRunResult, RunStatus
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from agent.runtime_context import build_runtime_context
from agent.runtime_core.composite_taskplan import project_task_plan_bridge
from agent.runtime_core.execution_binding import (
    ExecutionBindingError,
    project_execution_binding,
    validate_execution_binding,
)
from agent.provider_structured_output import project_structured_output_evidence
from agent.provider_runtime import (
    project_planner_attempt_receipt,
    project_provider_runtime_evidence,
)
from agent.run_events import new_run_event
from agent.runtime_core.selection_evidence import normalize_selection_evidence
from agent.runtime_core.plan_receipt import project_canonical_plan_receipt
from agent.planner_repair import build_repair_lineage
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
        answer_generator: Any = None,
    ) -> None:
        if coordinator is None or not callable(getattr(coordinator, "run", None)):
            raise ValueError("coordinator must expose run()")
        self._coordinator = coordinator
        self._answer_generator = answer_generator
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
        execution_binding: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_composite_request(request)
        return self._execute_and_persist(
            normalized,
            session_id=session_id,
            export_artifact=export_artifact,
            execution_binding=execution_binding,
        )

    def run_with_planning(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        export_artifact: bool = False,
        planner_evidence: Mapping[str, Any] | None = None,
        execution_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
        """Run a canonical request while preserving bounded planner evidence."""
        normalized = normalize_composite_request(request)
        return self._execute_and_persist(
            normalized,
            session_id=session_id,
            export_artifact=export_artifact,
            planning_evidence=_safe_planning_evidence(planner_evidence),
            execution_binding=execution_binding,
        )

    def submit_async(
        self,
        request: Mapping[str, Any],
        *,
        session_id: str = "default",
        idempotency_key: str | None = None,
        export_artifact: bool = False,
        execution_binding: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_composite_request(request)
        payload: Mapping[str, Any] = normalized
        if execution_binding is not None:
            payload = {
                "request": normalized,
                "_execution_binding": _validated_binding(
                    execution_binding,
                    request=normalized,
                ),
            }
        encoded = json.dumps(
            payload,
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
        execution_binding: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit without changing the request contract or losing evidence."""
        normalized = normalize_composite_request(request)
        evidence = _safe_planning_evidence(planner_evidence)
        payload: Mapping[str, Any] = normalized
        if evidence or execution_binding is not None:
            payload = {
                "request": normalized,
                "_planner_evidence": evidence,
            }
            if execution_binding is not None:
                payload["_execution_binding"] = _validated_binding(
                    execution_binding,
                    request=normalized,
                )
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
            job = self._state.async_job(safe_id, domain_id=COMPOSITE_RUN_SCOPE)
            if isinstance(job, Mapping) and str(job.get("status") or "").upper() in {
                "FAILED",
                "CANCELLED",
                "TIMED_OUT",
            }:
                return _response_from_result(
                    {},
                    run_id=safe_id,
                    fallback_request=_composite_request_from_value(job.get("payload")),
                    fallback_status=job.get("status"),
                    fallback_error_category=job.get("failure_category"),
                )
            artifact = self._artifact_store.read_run(
                safe_id, domain_id=COMPOSITE_RUN_SCOPE
            )
            if isinstance(artifact, dict):
                artifact_result = artifact.get("result")
                return _response_from_result(
                    artifact_result if isinstance(artifact_result, Mapping) else {},
                    run_id=safe_id,
                    artifact_ref=artifact.get("artifact_ref"),
                    artifact_recovered=True,
                    fallback_request=_composite_request_from_value(artifact.get("request")),
                    fallback_status=artifact.get("status"),
                    fallback_error_code=artifact.get("error_code"),
                    fallback_error_category=artifact.get("error_category"),
                    fallback_failure=artifact.get("failure"),
                )
        if result is None:
            raise ValueError("composite run not found: " + str(run_id))
        async_job = (
            self._state.async_job(safe_id, domain_id=COMPOSITE_RUN_SCOPE)
            if safe_id and self._state.persistent
            else None
        )
        fallback_request = _composite_request_from_value(getattr(result, "request", None))
        if fallback_request is None and isinstance(async_job, Mapping):
            fallback_request = _composite_request_from_value(async_job.get("payload"))
        return _response_from_result(
            result.result if isinstance(result.result, Mapping) else {},
            run_id=result.run_id,
            artifact_ref=result.artifact_ref,
            artifact_recovered=artifact_recovered,
            fallback_request=fallback_request,
            fallback_status=result.status.value,
            fallback_error_code=result.error_code,
            fallback_error_category=result.error_category,
            fallback_failure=result.failure,
        )

    def get_observability(self, run_id: str) -> dict[str, Any]:
        return self._async.get_observability(_safe_required_run_id(run_id))

    def get_evidence(self, run_id: str) -> dict[str, Any]:
        detail = self.get_run(run_id)
        result = detail.get("result") if isinstance(detail, dict) else {}
        composite = result.get("composite") if isinstance(result, Mapping) else {}
        binding_evidence = (
            composite.get("request", {}).get("execution_binding")
            if isinstance(composite, Mapping)
            and isinstance(composite.get("request"), Mapping)
            else None
        )
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
            "execution_binding": binding_evidence,
            "answer_generation": result.get("answer_generation_evidence") or {"available": False},
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
        execution_binding = None
        if isinstance(request, Mapping) and isinstance(request.get("request"), Mapping):
            planning_evidence = _safe_planning_evidence(request.get("_planner_evidence"))
            if request.get("_execution_binding") is not None:
                execution_binding = _validated_binding(
                    request.get("_execution_binding"),
                    request=request["request"],
                )
            request = request["request"]
        response = self._execute_and_persist(
            normalize_composite_request(request),
            session_id=str(kwargs.get("session_id") or "default"),
            run_id=run_id,
            export_artifact=bool(kwargs.get("export_artifact", False)),
            async_requested=True,
            planning_evidence=planning_evidence,
            execution_binding=execution_binding,
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
        execution_binding: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if execution_binding is not None:
            binding = _validated_binding(execution_binding, request=request)
            response = self._coordinator.run(
                request,
                session_id=session_id,
                run_id=run_id,
                execution_binding=binding,
            )
        else:
            response = self._coordinator.run(
                request,
                session_id=session_id,
                run_id=run_id,
            )
        canonical = response.get("result")
        if not isinstance(canonical, Mapping):
            raise ValueError("composite coordinator returned no result contract")
        canonical = normalize_result_contract(canonical)
        actual_run_id = _safe_required_run_id(response.get("run_id"))
        self._append_run_event(
            actual_run_id,
            phase="answer",
            kind="stage_started",
            status="EXECUTING",
            message="正在汇总组合分析结果",
        )
        streamed_length = 0

        def emit_answer_delta(delta: str) -> None:
            nonlocal streamed_length
            if not isinstance(delta, str) or not delta:
                return
            streamed_length += len(delta)
            self._append_run_event(
                actual_run_id,
                phase="answer",
                kind="answer_delta",
                status="EXECUTING",
                message="答案正在生成",
                data={
                    "answer_delta": delta[:512],
                    "answer_length": min(streamed_length, 1800),
                },
                terminal=False,
            )
        canonical = self._compose_composite_answer(
            canonical,
            planning_evidence=planning_evidence,
            on_delta=emit_answer_delta,
        )
        if planning_evidence:
            canonical = dict(canonical)
            canonical["planner_evidence"] = dict(planning_evidence)
        if execution_binding is not None:
            response["execution_binding"] = project_execution_binding(execution_binding)
        snapshot = AgentRunResult(
            run_id=actual_run_id,
            status=_run_status(response.get("status")),
            request=str(request.get("request") or "")[:2000],
            session_id=str(session_id or "default")[:120],
            domain_id=COMPOSITE_RUN_SCOPE,
            runtime_context=_runtime_context(COMPOSITE_RUN_SCOPE, COMPOSITE_RUN_SCOPE),
            result=canonical,
            answer=str(canonical.get("answer") or canonical.get("summary") or "")[:1200] or None,
        )
        response = dict(response)
        response["run_id"] = actual_run_id
        response["result"] = canonical
        # The synchronous response must expose the same View contract as the
        # later HTTP/artifact recovery path.  Without this projection the
        # Console sees a result envelope immediately but cannot render the
        # Composite answer/selection view until it performs a second read.
        response["view"] = build_composite_view_projection(canonical)
        if export_artifact:
            payload = snapshot.to_dict()
            if async_requested:
                payload["_async_requested"] = True
            artifact_ref = self._artifact_store.write_run(payload)
            snapshot.artifact_ref = artifact_ref
            response["artifact_ref"] = artifact_ref
        # Publish the final snapshot only after optional artifact publication.
        # Pollers must never observe COMPLETED without the artifact reference
        # that the same request explicitly asked us to export.
        self._memory_results[actual_run_id] = snapshot
        self._state.save_run(snapshot)
        self._append_run_event(
            actual_run_id,
            phase="answer",
            kind="stage_completed",
            status=snapshot.status.value,
            message="组合分析答案已生成",
            data={"answer_length": len(snapshot.answer or "")},
        )
        return response

    def _append_run_event(
        self,
        run_id: str,
        *,
        phase: str,
        kind: str,
        status: str,
        message: str,
        data: Mapping[str, Any] | None = None,
        terminal: bool | None = None,
    ) -> None:
        sink = getattr(self._state, "append_run_event", None)
        if not callable(sink):
            return
        try:
            sink(
                new_run_event(
                    run_id=run_id,
                    phase=phase,
                    kind=kind,
                    status=status,
                    message=message,
                    data=data,
                    terminal=terminal,
                )
            )
        except Exception:
            return

    def _compose_composite_answer(
        self,
        result: Mapping[str, Any],
        *,
        planning_evidence: Mapping[str, Any] | None = None,
        on_delta=None,
    ) -> dict[str, Any]:
        """Attach an LLM answer only to an LLM-planned Composite result.

        Direct Composite execution and deterministic Rule/Replay paths must
        remain offline.  The planner evidence is the existing public seam for
        distinguishing an actual LLM plan from a caller merely requesting a
        Composite run, so this method does not infer mode from request text.
        """

        generator = self._answer_generator
        planner_source = str(
            planning_evidence.get("planner_source")
            if isinstance(planning_evidence, Mapping)
            else ""
        ).strip().lower()
        if planner_source not in {"llm", "openai"}:
            return dict(result)
        if generator is None or not callable(getattr(generator, "generate", None)):
            return dict(result)
        try:
            stream_generate = getattr(generator, "generate_stream", None)
            if callable(on_delta) and callable(stream_generate):
                generated = stream_generate(result, on_delta=on_delta)
            else:
                generated = generator.generate(result)
            answer = getattr(generated, "answer", None)
            evidence = getattr(generated, "evidence", None)
            if not isinstance(answer, Mapping) or not isinstance(evidence, Mapping):
                raise ValueError("composite answer generator returned an invalid result")
        except Exception:
            generated = fallback_composite_answer(result, "answer_generation_failed")
            answer = generated.answer
            evidence = generated.evidence
        enriched = dict(result)
        enriched["answer_structured"] = dict(answer)
        enriched["answer_generation_evidence"] = project_answer_generation_evidence(
            evidence
        )
        enriched["answer"] = str(answer.get("summary") or enriched.get("answer") or "")[:1200]
        return enriched

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


def _validated_binding(value: Any, *, request: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return validate_execution_binding(value, request=request)
    except ExecutionBindingError as exc:
        raise ValueError("composite execution binding rejected: " + exc.code) from exc


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
        "execution_binding",
        "repair_lineage",
        "structured_output",
        "provider_runtime",
        "planner_attempt",
        "canonical_plan",
        "plan_completeness",
        "continuation",
        "discovery",
        "selection_evidence",
        "analysis_intents",
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
    if "execution_binding" in result:
        result["execution_binding"] = project_execution_binding(
            result.get("execution_binding")
        )
    if "structured_output" in result:
        projected_structured_output = project_structured_output_evidence(
            result.get("structured_output")
        )
        if projected_structured_output is None:
            result.pop("structured_output", None)
        else:
            result["structured_output"] = projected_structured_output
    if "provider_runtime" in result:
        projected_provider_runtime = project_provider_runtime_evidence(
            result.get("provider_runtime")
        )
        if projected_provider_runtime is None:
            result.pop("provider_runtime", None)
        else:
            result["provider_runtime"] = projected_provider_runtime
    if "planner_attempt" in result:
        planner_attempt = project_planner_attempt_receipt(result.get("planner_attempt"))
        if planner_attempt is None:
            result.pop("planner_attempt", None)
        else:
            result["planner_attempt"] = planner_attempt
    if "canonical_plan" in result:
        canonical_plan = result.get("canonical_plan")
        if isinstance(canonical_plan, Mapping):
            result["canonical_plan"] = project_canonical_plan_receipt(canonical_plan)
        else:
            result.pop("canonical_plan", None)
    if "plan_completeness" in result:
        completeness = result.get("plan_completeness")
        if isinstance(completeness, Mapping):
            result["plan_completeness"] = {
                "schema_version": str(
                    completeness.get("schema_version")
                    or "spatial-agent.plan-completeness.v1"
                )[:96],
                "status": str(completeness.get("status") or "unknown")[:24],
                "reason_code": str(completeness.get("reason_code") or "")[:96]
                or None,
                "component_count": max(
                    0, min(8, int(completeness.get("component_count") or 0))
                ),
                "materialized_count": max(
                    0, min(8, int(completeness.get("materialized_count") or 0))
                ),
            }
        else:
            result.pop("plan_completeness", None)
    if "discovery" in result:
        discovery = result.get("discovery")
        if isinstance(discovery, Mapping):
            result["discovery"] = _safe_discovery_evidence(discovery)
        else:
            result.pop("discovery", None)
    if "selection_evidence" in result:
        selection_evidence = normalize_selection_evidence(result.get("selection_evidence"))
        if selection_evidence:
            result["selection_evidence"] = selection_evidence
        else:
            result.pop("selection_evidence", None)
    if "analysis_intents" in result:
        result["analysis_intents"] = _safe_analysis_intents(result.get("analysis_intents"))
        if not result["analysis_intents"]:
            result.pop("analysis_intents", None)
    if "continuation" in result:
        continuation = result.get("continuation")
        if isinstance(continuation, Mapping):
            result["continuation"] = {
                "schema_version": str(continuation.get("schema_version") or "")[:96],
                "request_fingerprint": str(continuation.get("request_fingerprint") or "")[:128] or None,
                "planner_selection_fingerprint": str(
                    continuation.get("planner_selection_fingerprint") or ""
                )[:128]
                or None,
                "component_id": str(continuation.get("component_id") or "")[:96],
                "domain_id": str(continuation.get("domain_id") or "")[:64],
                "capability_id": str(continuation.get("capability_id") or "")[:96],
                "field_ids": [
                    str(item)[:80]
                    for item in (continuation.get("field_ids") or [])[:16]
                    if str(item).strip()
                ],
                "component_ids": [
                    str(item)[:96]
                    for item in (continuation.get("component_ids") or [])[:8]
                    if str(item).strip()
                ],
                "domain_ids": [
                    str(item)[:64]
                    for item in (continuation.get("domain_ids") or [])[:8]
                    if str(item).strip()
                ],
                "components": [
                    {
                        "component_id": str(item.get("component_id") or "")[:96],
                        "domain_id": str(item.get("domain_id") or "")[:64],
                        "capability_id": str(item.get("capability_id") or "")[:96],
                    }
                    for item in (continuation.get("components") or [])[:8]
                    if isinstance(item, Mapping)
                ],
            }
        else:
            result.pop("continuation", None)
    if "repair_lineage" in result:
        lineage = result.get("repair_lineage")
        if isinstance(lineage, Mapping):
            try:
                result["repair_lineage"] = build_repair_lineage(
                    reason_code=lineage.get("reason_code"),
                    status=lineage.get("status"),
                    attempted=bool(lineage.get("attempted")),
                    count=int(lineage.get("count") or 0),
                    request_fingerprint=lineage.get("request_fingerprint"),
                )
            except (TypeError, ValueError):
                result.pop("repair_lineage", None)
        else:
            result.pop("repair_lineage", None)
    return result


def _safe_analysis_intents(value: Any) -> list[dict[str, Any]]:
    """Preserve only normalized intent receipts across async/artifact reads."""

    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for raw in list(value)[:8]:
        if not isinstance(raw, Mapping):
            continue
        try:
            intent = normalize_analysis_intent(raw.get("intent"))
        except AnalysisIntentError:
            continue
        item = {"intent": intent}
        domain_id = str(raw.get("domain_id") or "").strip()[:64]
        if domain_id:
            item["domain_id"] = domain_id
        result.append(item)
    return result


def _safe_discovery_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep receipt identity/state while dropping candidate payload details."""

    candidates = [
        item for item in (value.get("candidate_states") or {}).items()
        if isinstance(item, tuple) and len(item) == 2
    ]
    states = {
        str(key)[:32]: max(0, min(16, int(count)))
        for key, count in candidates
    }
    return {
        "schema_version": str(value.get("schema_version") or "")[:96],
        "request_fingerprint": str(value.get("request_fingerprint") or "")[:128] or None,
        "discovery_fingerprint": str(value.get("discovery_fingerprint") or "")[:128] or None,
        "state": str(value.get("state") or "unknown")[:32],
        "reason_code": str(value.get("reason_code") or "unknown")[:96],
        "domain_count": max(0, min(8, int(value.get("domain_count") or 0))),
        "candidate_count": max(0, min(16, int(value.get("candidate_count") or 0))),
        "data_requirement_count": max(0, min(64, int(value.get("data_requirement_count") or 0))),
        "candidate_states": states,
        "next_actions": [str(item)[:160] for item in (value.get("next_actions") or [])[:4]],
    }


def _response_from_result(
    result: Mapping[str, Any],
    *,
    run_id: str,
    artifact_ref: Any = None,
    artifact_recovered: bool = False,
    fallback_request: Mapping[str, Any] | None = None,
    fallback_status: Any = None,
    fallback_error_code: Any = None,
    fallback_error_category: Any = None,
    fallback_failure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("composite result is invalid")
    result = _ensure_composite_result(
        result,
        run_id=run_id,
        fallback_request=fallback_request,
        fallback_status=fallback_status,
        fallback_error_code=fallback_error_code,
        fallback_error_category=fallback_error_category,
        fallback_failure=fallback_failure,
    )
    composite = result.get("composite") if isinstance(result.get("composite"), Mapping) else {}
    state = str(composite.get("state") or "failed")
    status = {
        "pending": "PLANNING",
        "completed": "COMPLETED",
        "partial": "PARTIAL",
        "blocked": "BLOCKED",
        "failed": "FAILED",
    }.get(state, "FAILED")
    fallback_lifecycle = str(fallback_status or "").upper()
    if fallback_lifecycle in {
        "QUEUED",
        "PLANNING",
        "EXECUTING",
        "CANCEL_REQUESTED",
    }:
        status = fallback_lifecycle
    response = {
        "schema_version": COMPOSITE_COORDINATOR_SCHEMA_VERSION,
        "run_id": run_id,
        "status": status,
        "state": state,
        "request_fingerprint": (composite.get("request") or {}).get("fingerprint"),
        "components": composite.get("components") or [],
        "result": dict(result),
    }
    if result.get("error_code"):
        response["error_code"] = str(result["error_code"])[:96]
    if result.get("error_category"):
        response["error_category"] = str(result["error_category"])[:64]
    if isinstance(result.get("failure"), Mapping):
        response["failure"] = dict(result["failure"])
    binding = composite.get("request", {}).get("execution_binding")
    if isinstance(binding, Mapping):
        response["execution_binding"] = dict(binding)
    response["view"] = build_composite_view_projection(result)
    if artifact_ref:
        response["artifact_ref"] = artifact_ref
    if artifact_recovered:
        response["artifact_recovered"] = True
    return response


def _ensure_composite_result(
    result: Mapping[str, Any],
    *,
    run_id: str,
    fallback_request: Mapping[str, Any] | None,
    fallback_status: Any,
    fallback_error_code: Any,
    fallback_error_category: Any,
    fallback_failure: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Make failed async snapshots readable without reviving execution.

    ``AsyncApplication`` persists the generic ``AgentRunResult`` before a
    worker starts.  If the worker raises before the Composite coordinator
    returns, that snapshot legitimately has no nested Composite result.  Read
    paths must still expose one stable Result/View contract rather than
    throwing from the frontend boundary.
    """

    candidate = dict(result)
    try:
        normalize_composite_section(candidate.get("composite"))
        return candidate
    except (CompositeContractError, TypeError):
        pass

    request = fallback_request or _unavailable_composite_request()
    failure = _normalize_fallback_failure(
        status=fallback_status,
        code=fallback_error_code,
        category=fallback_error_category,
        existing=fallback_failure,
    )
    active_status = str(fallback_status or "").upper()
    if active_status in {
        "QUEUED",
        "PLANNING",
        "EXECUTING",
        "CANCEL_REQUESTED",
    }:
        child_status = "QUEUED" if active_status == "QUEUED" else "PLANNING"
        children = {
            component["component_id"]: {
                "status": child_status,
                "domain_id": component["domain_id"],
            }
            for component in request["components"]
        }
        recovered = build_composite_result_contract(
            request,
            children,
            run_id=run_id,
            answer="组合分析正在处理中，完成后将返回结构化结果。",
        )
        return normalize_result_contract(recovered)

    children = {
        component["component_id"]: {
            "status": "FAILED",
            "domain_id": component["domain_id"],
            "error": "组合执行未能返回组件结果。",
            "error_code": failure["code"],
            "error_category": failure["category"],
        }
        for component in request["components"]
    }
    recovered = build_composite_result_contract(
        request,
        children,
        run_id=run_id,
        answer="组合分析未能完成，失败原因已记录，可根据失败证据进行恢复。",
    )
    recovered["error_code"] = failure["code"]
    recovered["error_category"] = failure["category"]
    recovered["failure"] = failure
    return normalize_result_contract(recovered)


def _composite_request_from_value(value: Any) -> dict[str, Any] | None:
    """Decode only a bounded canonical request from a snapshot or job."""

    candidate = value
    if isinstance(candidate, str):
        if len(candidate) > 64_000:
            return None
        try:
            candidate = json.loads(candidate)
        except (TypeError, ValueError):
            return None
    if not isinstance(candidate, Mapping):
        return None
    nested = candidate.get("request")
    if isinstance(nested, Mapping):
        candidate = nested
    try:
        return normalize_composite_request(candidate, allow_legacy=True)
    except (CompositeContractError, TypeError):
        return None


def _unavailable_composite_request() -> dict[str, Any]:
    """Return a truthful, domain-neutral request for unrecoverable snapshots."""

    return normalize_composite_request(
        {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合分析请求",
            "components": [
                {
                    "component_id": "request",
                    "domain_id": "unknown",
                    "request": "恢复组合请求",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }
    )


def _normalize_fallback_failure(
    *,
    status: Any,
    code: Any,
    category: Any,
    existing: Mapping[str, Any] | None,
) -> dict[str, Any]:
    existing = existing if isinstance(existing, Mapping) else {}
    normalized_status = str(status or "FAILED").upper()
    default_category = {
        "CANCELLED": "cancelled",
        "TIMED_OUT": "timeout",
    }.get(normalized_status, "execution")
    default_code = {
        "CANCELLED": "run_cancelled",
        "TIMED_OUT": "run_timeout",
    }.get(normalized_status, "execution_failed")
    return build_failure_evidence(
        status="FAILED",
        category=category or existing.get("category") or default_category,
        code=code or existing.get("code") or default_code,
        phase=existing.get("phase") or "execution",
        retryable=existing.get("retryable"),
    )


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
