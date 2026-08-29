"""Canonical run query and recovery application.

This module owns the read/replay side of a run lifecycle.  It resolves the
Runtime selection carried by a durable run, reads from SQLite or memory,
falls back to an artifact when necessary, rebuilds the public result contract,
and executes retry/cancel through the existing action-receipt seam.  The
``AgentService`` facade only adapts legacy method names to this interface.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from agent.persistence.artifact_store import ArtifactStore
from agent.execution_contract import build_execution_record
from agent.evidence.projection import project_evidence_projection, project_evidence_recovery
from agent.evidence.registry import normalize_evidence_registry
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES, export_run_summary
from agent.models import RunStatus
from agent.nested_schema import NestedSchemaError, normalize_result_contract
from agent.provenance import build_provenance
from agent.application.service_format import (
    _attach_error_category,
    exported_geometry_evidence as _exported_geometry_evidence,
    result_type as _result_type,
    tag_geometry_features as _tag_geometry_features,
)
from agent.application.service_sessions import attach_history_lineage as _attach_history_lineage
from agent.trace_formatter import format_trace
from result_contract import build_result_contract


_TERMINAL_RUN_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.NEEDS_CLARIFICATION,
    RunStatus.WAITING_FOR_DECISION,
    RunStatus.REJECTED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
}


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


class RunRecoveryApplication:
    """Read, replay and cancel runs through one deep application seam."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        domain_id_provider: Callable[[str, str], str],
        resolved_domain_id: Callable[[], Optional[str]],
        configured_domain_id: Callable[[], Optional[str]],
        reserve_action_receipt: Callable[..., Any],
        complete_action_receipt: Callable[..., Any],
        attach_async_observability: Callable[[Dict[str, Any], Optional[str]], None],
        mark_memory_cancel_requested: Callable[[str], None],
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._runtime_provider = runtime_provider
        self._domain_id_provider = domain_id_provider
        self._resolved_domain_id = resolved_domain_id
        self._configured_domain_id = configured_domain_id
        self._reserve_action_receipt = reserve_action_receipt
        self._complete_action_receipt = complete_action_receipt
        self._attach_async_observability = attach_async_observability
        self._mark_memory_cancel_requested = mark_memory_cancel_requested

    def memory_run(self, run_id: str) -> Any:
        """Find a memory run across all cached planner/backend adapters."""
        for runtime in self._state.runtimes().values():
            result = runtime.get_run(run_id)
            if result is not None:
                return result
        return None

    def infer_runtime_selection(
        self, run_id: str, planner: str, backend: str
    ) -> tuple[str, str]:
        """Recover immutable planner/backend selection from a run snapshot."""
        if (planner, backend) != ("rule", "memory"):
            return planner, backend

        context = None
        if self._state.persistent:
            domain_id = self._resolved_domain_id() or self._configured_domain_id()
            snapshot = self._state.get_run(run_id, domain_id=domain_id)
            context = getattr(snapshot, "runtime_context", None) if snapshot else None
            if not isinstance(context, dict):
                job = self._state.async_job(run_id, domain_id=domain_id)
                payload = job.get("payload") if isinstance(job, dict) else None
                context = payload.get("runtime_context") if isinstance(payload, dict) else None
                if isinstance(payload, dict):
                    planner = str(payload.get("planner") or planner)
                    backend = str(payload.get("backend") or backend)
        else:
            snapshot = self.memory_run(run_id)
            context = getattr(snapshot, "runtime_context", None) if snapshot else None

        if isinstance(context, dict):
            planner = str(context.get("planner") or planner)
            backend = str(context.get("backend") or backend)
        if planner not in {"rule", "openai"}:
            planner = "rule"
        if backend not in {"memory", "local"}:
            backend = "memory"
        return planner, backend

    def retry(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Retry a failed run with an idempotent action receipt."""
        self._validate_run_id(run_id)
        receipt, reused = self._reserve_action_receipt(
            source_run_id=run_id,
            action="retry",
            payload={
                "export_artifact": bool(export_artifact),
                "export_geojson": bool(export_geojson),
                "geojson_max_features": int(geojson_max_features),
                "idempotency_key": idempotency_key,
            },
            planner=planner,
            backend=backend,
            auto_key=idempotency_key is not None,
        )
        if reused:
            return receipt
        try:
            response = self._retry_payload(
                run_id,
                planner=planner,
                backend=backend,
                export_artifact=export_artifact,
                export_geojson=export_geojson,
                geojson_max_features=geojson_max_features,
            )
        except Exception as exc:
            self._complete_action_receipt(
                receipt,
                {"run_id": run_id, "status": "FAILED", "error": str(exc)},
                status="FAILED",
                error_code="retry_failed",
                response_payload={
                    "run_id": run_id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
            raise
        action_status = "COMPLETED" if response.get("status") == "COMPLETED" else "FAILED"
        return self._complete_action_receipt(
            receipt,
            response,
            status=action_status,
            error_code=None if action_status == "COMPLETED" else "retry_failed",
            result_run_id=response.get("run_id") or run_id,
        )

    def _retry_payload(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
    ) -> Dict[str, Any]:
        self._validate_run_id(run_id)
        runtime = self._runtime_provider(planner, backend)
        result = runtime.retry_failed(run_id)
        payload = result.to_dict()
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
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
            _, geometry_evidence = _exported_geometry_evidence(payload["geojson_ref"])
            result.geometry_evidence = geometry_evidence
            result.geojson_ref = payload["geojson_ref"]
            payload["_geometry_evidence"] = geometry_evidence
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        result.evidence_registry = payload["result"].get("evidence_registry")
        payload.pop("_geometry_feature_count", None)
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        payload["execution_record"] = build_execution_record(payload, kind="run")
        if export_artifact:
            self._artifact_store.write_run(payload)
        if self._state.persistent:
            self._state.save_run(result)
        return payload

    def cancel(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        idempotency_key: str = None,
    ) -> Dict[str, Any]:
        """Cancel a run or persist a cancellation request for its worker."""
        self._validate_run_id(run_id)
        receipt, reused = self._reserve_action_receipt(
            source_run_id=run_id,
            action="cancel",
            payload={"idempotency_key": idempotency_key},
            planner=planner,
            backend=backend,
        )
        if reused:
            return receipt
        try:
            result = self._runtime_provider(planner, backend).cancel(run_id)
            if not self._state.persistent:
                self._mark_memory_cancel_requested(run_id)
            response = {
                "run_id": run_id,
                "status": (
                    "CANCELLED"
                    if result.status == RunStatus.CANCELLED
                    else "CANCEL_REQUESTED"
                ),
                "current_status": result.status.value,
            }
        except Exception as exc:
            self._complete_action_receipt(
                receipt,
                {"run_id": run_id, "status": "FAILED", "error": str(exc)},
                status="FAILED",
                error_code="cancel_failed",
                response_payload={
                    "run_id": run_id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
            raise
        return self._complete_action_receipt(
            receipt,
            response,
            status="COMPLETED",
            result_run_id=run_id,
            response_payload=response,
        )

    def get_run(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict[str, Any]:
        """Read a run from memory/SQLite and recover from an artifact if needed."""
        self._validate_run_id(run_id)
        planner, backend = self.infer_runtime_selection(run_id, planner, backend)
        domain_id = self._domain_id_provider(planner, backend)
        result = self._wait_for_consistent_snapshot(run_id, planner, backend, domain_id)
        if result is None and not self._state.persistent:
            result = self.memory_run(run_id)
        if result is None:
            payload = self._artifact_store.read_run(run_id, domain_id=domain_id)
            if payload is not None:
                return self._project_artifact_payload(payload, run_id, planner, backend)
            self._reject_cross_domain_run_id(run_id, domain_id)
        if result is None:
            raise ValueError("run not found: " + run_id)
        payload = result.to_dict()
        explicit_geometry = payload.pop("geometry_evidence", None)
        if explicit_geometry is not None:
            payload["_geometry_evidence"] = explicit_geometry
        payload["trace_summary"] = format_trace(result)
        runtime = self._runtime_provider(planner, backend)
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        payload.pop("_geometry_evidence", None)
        _attach_error_category(payload)
        payload["execution_record"] = build_execution_record(payload, kind="run")
        self._attach_async_observability(payload, run_id)
        return payload

    def list_runs(self, limit: int = 20) -> Dict[str, Any]:
        if self._state.persistent:
            records = self._state.list_runs(
                limit=limit, domain_id=self._resolved_domain_id()
            )
        else:
            records = self._artifact_store.list_runs(
                limit=limit, domain_id=self._resolved_domain_id()
            )
        return {"runs": _attach_history_lineage(records)}

    def get_run_evidence(self, run_id: str) -> Dict[str, Any]:
        """Return a bounded, navigable evidence index for one run."""
        self._validate_run_id(run_id)
        domain_id = self._resolved_domain_id() or self._configured_domain_id() or "gis"
        artifact = self._artifact_store.read_run(run_id, domain_id=domain_id)
        registry = normalize_evidence_registry(
            artifact.get("evidence_registry") if isinstance(artifact, dict) else None
        )
        artifact_ref = artifact.get("artifact_ref") if isinstance(artifact, dict) else None
        payload = None
        if not registry.get("available"):
            try:
                payload = self.get_run(run_id)
            except ValueError:
                payload = None
            envelope = payload.get("result") if isinstance(payload, dict) else None
            if isinstance(envelope, dict):
                registry = normalize_evidence_registry(envelope.get("evidence_registry"))
                artifact_ref = artifact_ref or payload.get("artifact_ref")
        safe_ref = str(artifact_ref or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not registry.get("available") and not safe_ref:
            self._reject_cross_domain_run_id(run_id, domain_id)
            raise ValueError("run evidence not found: " + run_id)
        source = artifact if isinstance(artifact, dict) else (payload or {})
        return {
            "schema_version": "spatial-agent.evidence-reference.v1",
            "run_id": run_id,
            "domain_id": domain_id,
            "artifact": {"available": bool(safe_ref), "ref": safe_ref or None},
            "evidence_registry": registry,
            "evidence_projection": project_evidence_projection(source),
            "evidence_recovery": project_evidence_recovery(source),
        }

    def _wait_for_consistent_snapshot(
        self, run_id: str, planner: str, backend: str, domain_id: str
    ) -> Any:
        result = None
        for _ in range(1000):
            result = (
                self._state.get_run(run_id, domain_id=domain_id)
                if self._state.persistent
                else self._runtime_provider(planner, backend).get_run(run_id)
            )
            if result is None or not self._state.persistent:
                break
            job = self._state.async_job(run_id, domain_id=domain_id)
            job_payload = (
                job.get("payload")
                if isinstance(job, dict) and isinstance(job.get("payload"), dict)
                else {}
            )
            requested_artifact = job_payload.get("export_artifact") is True
            requested_geojson = job_payload.get("export_geojson") is True
            missing_requested_refs = result.status == RunStatus.COMPLETED and (
                (requested_artifact and not result.artifact_ref)
                or (requested_geojson and not result.geojson_ref)
            )
            if (
                result.status in _TERMINAL_RUN_STATUSES
                and job is not None
                and (
                    job.get("status") in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
                    or missing_requested_refs
                )
            ):
                time.sleep(0.005)
                continue
            break
        return result

    def _project_artifact_payload(
        self, payload: Dict[str, Any], run_id: str, planner: str, backend: str
    ) -> Dict[str, Any]:
        artifact_result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        normalized_artifact_result = None
        nested_schema_error = payload.get("nested_schema_warning")
        if artifact_result:
            try:
                normalized_artifact_result = normalize_result_contract(artifact_result)
            except NestedSchemaError as exc:
                nested_schema_error = exc.reason_code
        if nested_schema_error:
            payload["_nested_schema_error"] = nested_schema_error
        payload["trace_summary"] = payload.get("trace_summary") or []
        runtime = self._runtime_provider(planner, backend)
        payload["provenance"] = payload.get("provenance") or build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        artifact_views = (
            normalized_artifact_result.get("views")
            if isinstance(normalized_artifact_result, dict)
            else None
        )
        artifact_panels = artifact_views.get("panels") if isinstance(artifact_views, dict) else None
        if isinstance(artifact_views, dict) and isinstance(artifact_panels, dict) and artifact_panels:
            payload["result"]["views"] = artifact_views
        payload.pop("_nested_schema_error", None)
        payload.pop("nested_schema_warning", None)
        _attach_error_category(payload)
        payload["execution_record"] = payload.get("execution_record") or build_execution_record(
            payload, kind="run"
        )
        self._attach_async_observability(payload, run_id)
        return payload

    def _reject_cross_domain_run_id(self, run_id: str, domain_id: str) -> None:
        """Never let a detail/evidence read cross Domain ownership."""
        configured = self._configured_domain_id() or "gis"
        if self._state.persistent:
            other = self._state.get_run(run_id)
            if other is not None and (getattr(other, "domain_id", None) or configured) != domain_id:
                raise ValueError("run_id belongs to another domain: " + str(run_id))
        else:
            artifact = self._artifact_store.read_run(run_id)
            if artifact is not None and (artifact.get("domain_id") or configured) != domain_id:
                raise ValueError("run_id belongs to another domain: " + str(run_id))

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")


__all__ = ["RunRecoveryApplication"]
