"""Canonical run and preview submission application.

This module owns the front half of a request lifecycle: input validation,
workflow/context preparation, idempotent run lookup, cost governance and the
handoff into ``RunApplication``.  Finalization remains in ``RunApplication``;
query/recovery remains in ``RunRecoveryApplication``.  The facade therefore
does not carry a second lifecycle implementation.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from agent.cost_governance import RunTokenCapExceeded, extract_tokens
from agent.domain_registry import DomainSelectionError
from agent.domain_routing_evidence import (
    DomainRoutingEvidenceError,
    normalize_domain_routing_evidence,
    routing_evidence_identity,
    unavailable_domain_routing_evidence,
)
from agent.failure_contract import build_failure_evidence
from agent.geojson_exporter import DEFAULT_GEOJSON_MAX_FEATURES
from agent.service_format import (
    _attach_error_category,
    contextualize_request,
    format_result,
    normalize_spatial_context,
    result_type,
)
from agent.action_lifecycle import project_action_lifecycle


def _runtime_result_registry(runtime: Any) -> Any:
    resolver = getattr(runtime, "result_registry", None)
    return resolver() if callable(resolver) else None


class SubmissionApplication:
    """Prepare requests and hand them to canonical runtime application seams."""

    def __init__(
        self,
        *,
        state: Any,
        runtime_provider: Callable[[str, str], Any],
        workflow_normalizer: Callable[[Dict[str, Any] | None, str, str], Optional[Dict[str, Any]]],
        domain_id_provider: Callable[[str, str], str],
        execute_run: Callable[..., Dict[str, Any]],
        attach_async_observability: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> None:
        self._state = state
        self._runtime_provider = runtime_provider
        self._workflow_normalizer = workflow_normalizer
        self._domain_id_provider = domain_id_provider
        self._execute_run = execute_run
        self._attach_async_observability = attach_async_observability

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = DEFAULT_GEOJSON_MAX_FEATURES,
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
        run_id: str = None,
        preview_fingerprint: str = None,
        preview_evidence_fingerprint: str = None,
        require_confirmation: bool = False,
        decision_id: str = None,
        decision_version: int = None,
        decision_ttl_seconds: float = 1800.0,
        _force_run_id: bool = False,
        _async_requested: bool = False,
        _resolved_request: str = None,
        _domain_routing_evidence: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        self._validate_request(request, session_id, run_id, _resolved_request)
        workflow_context = self._workflow_normalizer(workflow, planner, backend)
        domain_id = self._domain_id_provider(planner, backend)
        if _domain_routing_evidence is None and run_id is not None and _force_run_id:
            existing = self._existing_run(run_id, planner, backend, domain_id)
            if existing is not None:
                restored = getattr(existing, "domain_routing_evidence", None)
                if isinstance(restored, Mapping) and restored.get("available") is True:
                    _domain_routing_evidence = restored
        routing_evidence = (
            normalize_domain_routing_evidence(
                _domain_routing_evidence,
                expected_domain_id=domain_id,
                strict=True,
            )
            if _domain_routing_evidence is not None
            else unavailable_domain_routing_evidence()
        )
        self._validate_preview_fingerprints(
            preview_fingerprint, preview_evidence_fingerprint
        )
        if run_id is not None and not _force_run_id:
            existing_any = self._state.get_run(run_id) if self._state.persistent else None
            if existing_any is not None and str(getattr(existing_any, "domain_id", "")) != domain_id:
                raise DomainSelectionError(
                    "run_id belongs to another domain: " + run_id,
                    code="run_domain_mismatch",
                )
            existing = self._existing_run(run_id, planner, backend, domain_id)
            if existing is not None:
                if routing_evidence_identity(
                    getattr(existing, "domain_routing_evidence", None)
                ) != routing_evidence_identity(routing_evidence):
                    raise DomainRoutingEvidenceError(
                        "run_id conflicts with domain routing identity",
                        code="domain_routing_evidence_run_conflict",
                    )
                payload = format_result(
                    existing,
                    normalize_spatial_context(spatial_context),
                    result_registry=_runtime_result_registry(
                        self._runtime_provider(planner, backend)
                    ),
                )
                self._attach_async_observability(payload, run_id)
                return payload
        self._ensure_session(session_id)
        normalized_context = normalize_spatial_context(spatial_context)
        cost = self._state.cost
        cost.acquire_concurrency()
        try:
            cost.check_budget(session_id)
            payload = self._execute_run(
                request,
                session_id,
                planner,
                backend,
                normalized_context,
                runtime_kwargs={
                    "session_id": session_id,
                    "timeout_seconds": timeout_seconds,
                    "run_id": run_id,
                    "expected_plan_fingerprint": preview_fingerprint,
                    "expected_evidence_fingerprint": preview_evidence_fingerprint,
                    "require_confirmation": bool(require_confirmation),
                    "decision_id": decision_id,
                    "decision_version": decision_version,
                    "decision_ttl_seconds": decision_ttl_seconds,
                    "decision_input": {
                        "export_artifact": bool(export_artifact),
                        "export_geojson": bool(export_geojson),
                        "geojson_max_features": int(geojson_max_features),
                    },
                },
                workflow_context=workflow_context,
                export_artifact=export_artifact,
                export_geojson=export_geojson,
                geojson_max_features=geojson_max_features,
                async_requested=_async_requested,
                resolved_request_override=_resolved_request,
                domain_routing_evidence=routing_evidence,
            )
        finally:
            cost.release_concurrency()
        if isinstance(payload.get("plan_evidence"), dict) and payload["plan_evidence"].get("plan_identity"):
            payload["plan_identity"] = dict(payload["plan_evidence"]["plan_identity"])
        cost.charge(session_id, extract_tokens(payload.get("planner_metrics")))
        try:
            cost.check_run_cap(extract_tokens(payload.get("planner_metrics")))
        except RunTokenCapExceeded as exc:
            payload["status"] = "FAILED"
            payload["error"] = str(exc)
            payload["error_category"] = "budget"
            payload["error_code"] = "budget_exceeded"
            payload["failure"] = build_failure_evidence(
                status="FAILED",
                category="budget",
                code="budget_exceeded",
                phase="control",
            )
            if isinstance(payload.get("result"), dict):
                payload["result"]["failure"] = dict(payload["failure"])
            _attach_error_category(payload)
        payload["execution_record"] = self._execution_record(payload)
        return payload

    def preview(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
        workflow: Dict[str, Any] = None,
        _resolved_request: str = None,
    ) -> Dict[str, Any]:
        self._validate_request(request, session_id, None, _resolved_request)
        workflow_context = self._workflow_normalizer(workflow, planner, backend)
        normalized_context = normalize_spatial_context(spatial_context)
        cost = self._state.cost
        cost.acquire_concurrency()
        try:
            cost.check_budget(session_id)
            runtime = self._runtime_provider(planner, backend)
            preview_kwargs = {
                "session_id": session_id,
                "timeout_seconds": timeout_seconds,
                "workflow": workflow_context,
            }
            if _resolved_request is not None:
                preview_kwargs["resolved_request_override"] = _resolved_request
            payload = runtime.preview(
                contextualize_request(request, normalized_context),
                **preview_kwargs,
            )
        finally:
            cost.release_concurrency()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = result_type(payload)
        plan_evidence = payload.get("plan_evidence")
        if isinstance(plan_evidence, dict) and isinstance(plan_evidence.get("evidence_binding"), dict):
            payload["evidence_binding"] = dict(plan_evidence["evidence_binding"])
        cost.charge(session_id, extract_tokens(payload.get("planner_metrics")))
        try:
            cost.check_run_cap(extract_tokens(payload.get("planner_metrics")))
        except RunTokenCapExceeded as exc:
            payload["status"] = "FAILED"
            payload["error"] = str(exc)
            payload["error_category"] = "budget"
        payload["lifecycle"] = project_action_lifecycle(payload)
        return payload

    def _existing_run(self, run_id: str, planner: str, backend: str, domain_id: str) -> Any:
        return (
            self._state.get_run(run_id, domain_id=domain_id)
            if self._state.persistent
            else self._runtime_provider(planner, backend).get_run(run_id)
        )

    def _ensure_session(self, session_id: str) -> None:
        if self._state.conversation_store is not None:
            self._state.conversation_store.ensure_session(session_id)
        else:
            self._state.ensure_session(session_id)

    @staticmethod
    def _validate_request(
        request: str,
        session_id: str,
        run_id: Optional[str],
        resolved_request: Optional[str],
    ) -> None:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a non-empty string")
        if resolved_request is not None and (
            not isinstance(resolved_request, str) or not resolved_request.strip()
        ):
            raise ValueError("_resolved_request must be a non-empty string")

    @staticmethod
    def _validate_preview_fingerprints(
        preview_fingerprint: Optional[str],
        preview_evidence_fingerprint: Optional[str],
    ) -> None:
        if preview_fingerprint is not None and (
            not isinstance(preview_fingerprint, str) or not preview_fingerprint.strip()
        ):
            raise ValueError("preview_fingerprint must be a non-empty string")
        if preview_evidence_fingerprint is not None and (
            not isinstance(preview_evidence_fingerprint, str)
            or not preview_evidence_fingerprint.strip()
        ):
            raise ValueError("preview_evidence_fingerprint must be a non-empty string")

    @staticmethod
    def _execution_record(payload: Dict[str, Any]) -> Dict[str, Any]:
        from agent.execution_contract import build_execution_record

        return build_execution_record(payload, kind="run")


__all__ = ["SubmissionApplication"]
