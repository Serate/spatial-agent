"""Canonical synchronous run application use case.

Transport adapters and the legacy ``AgentService`` facade provide input and
resource ports.  This module owns the domain-neutral finalization sequence:
runtime result projection, provenance, artifact/GeoJSON publication, result
contract construction, persistence, async quiescence, and bounded memory
evidence.  It does not choose a Domain, planner, or tool.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from agent.persistence.artifact_store import ArtifactStore
from agent.domain_routing_evidence import (
    bind_domain_routing_evidence,
    unavailable_domain_routing_evidence,
)
from agent.execution_contract import build_execution_record
from agent.failure_contract import failure_from_payload
from agent.geojson_exporter import export_run_summary
from agent.models import RunStatus
from agent.provenance import build_provenance
from result_contract import build_result_contract
from agent.application.service_format import (
    _attach_error_category,
    contextualize_request,
    exported_geometry_evidence as _exported_geometry_evidence,
    result_type as _result_type,
    tag_geometry_features as _tag_geometry_features,
)
from agent.trace_formatter import format_trace


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


class RunApplication:
    """Run finalization use case shared by sync and async application paths."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        resolved_domain_id: Callable[[], Optional[str]],
        configured_domain_id: Callable[[], Optional[str]],
        legacy_domain_id: str,
        attach_async_observability: Callable[[Dict[str, Any], Optional[str]], None],
        finalize_async_job: Callable[[Dict[str, Any]], None],
    ) -> None:
        self._artifact_store = artifact_store
        self._state = state
        self._runtime_provider = runtime_provider
        self._resolved_domain_id = resolved_domain_id
        self._configured_domain_id = configured_domain_id
        self._legacy_domain_id = legacy_domain_id
        self._attach_async_observability = attach_async_observability
        self._finalize_async_job = finalize_async_job

    def execute(
        self,
        request: str,
        session_id: str,
        planner: str,
        backend: str,
        normalized_context: Dict[str, Any],
        *,
        runtime_kwargs: Dict[str, Any],
        workflow_context: Optional[Dict[str, Any]],
        export_artifact: bool,
        export_geojson: bool,
        geojson_max_features: int,
        async_requested: bool = False,
        resolved_request_override: Optional[str] = None,
        domain_routing_evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        runtime = self._runtime_provider(planner, backend)
        runtime_kwargs = dict(runtime_kwargs)
        if workflow_context is not None:
            runtime_kwargs["workflow"] = workflow_context
        contextualized_request = contextualize_request(request, normalized_context)
        if resolved_request_override is None:
            result = runtime.run(contextualized_request, **runtime_kwargs)
        else:
            result = runtime.run(
                contextualized_request,
                resolved_request_override=resolved_request_override,
                **runtime_kwargs,
            )
        result.domain_routing_evidence = self._routing_evidence(
            domain_routing_evidence,
            result,
        )
        result.spatial_context = dict(normalized_context)
        payload = result.to_dict()
        if async_requested:
            payload["_async_requested"] = True
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        plan_evidence = payload.get("plan_evidence")
        if isinstance(plan_evidence, dict) and isinstance(
            plan_evidence.get("evidence_binding"), dict
        ):
            payload["evidence_binding"] = dict(plan_evidence["evidence_binding"])
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(
            payload,
            registry=_runtime_result_registry(runtime),
        )
        self._attach_decision_record(payload)
        self._attach_failure(payload, result)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
            result.artifact_ref = payload["artifact_ref"]
        if export_geojson:
            self._publish_geojson(
                payload,
                result,
                runtime,
                max_features=geojson_max_features,
            )
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
        self._attach_async_observability(payload, payload.get("run_id"))
        if export_artifact and async_requested:
            self._artifact_store.write_run(payload)
        payload["memory_evidence"] = self._state.memory.evidence(
            str(payload.get("session_id") or "default")
        )
        self._finalize_async_job(payload)
        if async_requested:
            self._attach_async_observability(payload, payload.get("run_id"))
            if export_artifact:
                self._artifact_store.write_run(payload)
        payload.pop("_async_requested", None)
        payload.pop("_decision_record", None)
        return payload

    def _routing_evidence(self, evidence: Any, result: Any) -> Dict[str, Any]:
        domain_id = (
            getattr(result, "domain_id", None)
            or self._resolved_domain_id()
            or self._configured_domain_id()
            or "gis"
        )
        if isinstance(evidence, Mapping) and evidence.get("available") is True:
            return bind_domain_routing_evidence(
                evidence,
                run_id=result.run_id,
                domain_id=domain_id,
            )
        reason = (evidence or {}).get("reason_code", "domain_routing_evidence_missing")
        return unavailable_domain_routing_evidence(reason)

    def _attach_decision_record(self, payload: Dict[str, Any]) -> None:
        if payload.get("status") != RunStatus.WAITING_FOR_DECISION.value:
            return
        evidence = payload.get("decision_evidence")
        decision_id = evidence.get("decision_id") if isinstance(evidence, dict) else None
        if not decision_id:
            return
        record = self._state.decision_store.get(
            decision_id,
            domain_id=(
                payload.get("domain_id")
                or self._resolved_domain_id()
                or self._configured_domain_id()
                or "gis"
            ),
        )
        if record is not None:
            payload["_decision_record"] = record.as_dict()

    def _attach_failure(self, payload: Dict[str, Any], result: Any) -> None:
        if payload.get("failure") is not None:
            return
        failure = failure_from_payload(payload)
        if failure is None:
            return
        payload["failure"] = failure
        payload.setdefault("error_category", failure["category"])
        payload.setdefault("error_code", failure["code"])
        result.failure = dict(failure)
        result.error_category = payload["error_category"]
        result.error_code = payload["error_code"]

    def _publish_geojson(
        self,
        payload: Dict[str, Any],
        result: Any,
        runtime: Any,
        *,
        max_features: int,
    ) -> None:
        geometry_features = []
        for step in payload.get("steps", []):
            result_ref = (step.get("result") or {}).get("result_ref")
            if not result_ref:
                continue
            exported = runtime.export_result(result_ref, max_features=max_features)
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
        payload["_geometry_evidence"] = geometry_evidence
        result.geometry_evidence = geometry_evidence
        result.geojson_ref = payload["geojson_ref"]
