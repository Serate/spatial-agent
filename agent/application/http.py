"""Domain-neutral HTTP application dispatcher.

Transport adapters parse URLs, query strings, JSON bodies, and HTTP status
codes.  This module owns the semantic POST use cases shared by FastAPI and
the standard-library server: payload projection, Service method selection,
workflow actions, routing actions, and session cleanup hooks.

It deliberately does not know a URL, an HTTP exception, or a GIS capability.
The small ``execute`` interface is the seam tested by both transports.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from agent.api_contract import (
    async_run_kwargs,
    cancel_kwargs,
    comparison_kwargs,
    constrained_comparison_kwargs,
    decision_resolve_kwargs,
    interaction_kwargs,
    region_comparison_kwargs,
    retry_kwargs,
    preview_kwargs,
    run_kwargs,
    workflow_action_result,
)
from agent.artifact_manifest import build_artifact_manifest
from agent.composite_contract import inherit_composite_runtime_selection
from agent.evidence_projection import project_evidence_projection, project_evidence_recovery
from agent.evidence_registry import normalize_evidence_registry
from agent.runtime_defaults import with_product_defaults


class HTTPApplication:
    """Dispatch one transport-neutral semantic command to an AgentService."""

    def __init__(
        self,
        service: Any,
        *,
        use_product_defaults: bool = False,
        routing: Any = None,
        composite: Any = None,
        composite_planning: Any = None,
        action_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_session_clear: Optional[Callable[[str], None]] = None,
        on_session_delete: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._service = service
        self._use_product_defaults = bool(use_product_defaults)
        self._routing = routing
        self._composite = composite
        self._composite_planning = composite_planning
        self._action_handler = action_handler
        self._on_session_clear = on_session_clear
        self._on_session_delete = on_session_delete

    def execute(
        self,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        run_id: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a known semantic command without interpreting a URL.

        ``run_id`` carries a path resource identifier for retry/cancel,
        interaction, decision, and session commands. ``template_id`` carries
        the workflow resource identifier. Unknown commands fail before any
        Service call, making the transport/application seam explicit.
        """
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        body = self._request_body(payload)
        action = action.strip()
        service = self._service

        if action == "run":
            return service.run(**run_kwargs(body))
        if action == "run_async":
            return service.run_async(**async_run_kwargs(body))
        if action == "composite_run":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            session_id = str(body.get("session_id") or "default")[:120]
            composite_body = inherit_composite_runtime_selection(
                body,
                planner=body.get("planner"),
                backend=body.get("backend"),
            )
            composite_kwargs = {"session_id": session_id}
            if "export_artifact" in body:
                composite_kwargs["export_artifact"] = bool(body.get("export_artifact"))
            return self._composite.run(composite_body, **composite_kwargs)
        if action == "composite_run_async":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            composite_body = inherit_composite_runtime_selection(
                body,
                planner=body.get("planner"),
                backend=body.get("backend"),
            )
            return self._composite.submit_async(
                composite_body,
                session_id=str(body.get("session_id") or "default")[:120],
                idempotency_key=body.get("idempotency_key"),
                export_artifact=bool(body.get("export_artifact", False)),
            )
        if action == "composite_plan":
            if self._composite_planning is None:
                raise RuntimeError("composite planning application is unavailable")
            execute = bool(body.get("execute", False))
            if execute:
                composite_plan_kwargs = {
                    "session_id": str(body.get("session_id") or "default")[:120],
                    "idempotency_key": body.get("idempotency_key"),
                    "planner_name": str(body.get("planner") or "rule")[:32],
                    "backend": str(body.get("backend") or "memory")[:32],
                    "domain_ids": body.get("domain_ids"),
                    "asynchronous": bool(body.get("async", True)),
                    "export_artifact": bool(body.get("export_artifact", False)),
                }
                if body.get("continuation_token") is not None:
                    composite_plan_kwargs["continuation_token"] = body.get("continuation_token")
                    composite_plan_kwargs["fact_supplement"] = body.get("facts") or body.get("fact_supplement")
                return self._composite_planning.submit(
                    str(body.get("request") or ""),
                    **composite_plan_kwargs,
                )
            composite_prepare_kwargs = {
                "planner_name": str(body.get("planner") or "rule")[:32],
                "backend": str(body.get("backend") or "memory")[:32],
                "domain_ids": body.get("domain_ids"),
            }
            if body.get("continuation_token") is not None:
                composite_prepare_kwargs["continuation_token"] = body.get("continuation_token")
                composite_prepare_kwargs["fact_supplement"] = body.get("facts") or body.get("fact_supplement")
            return self._composite_planning.prepare(
                str(body.get("request") or ""),
                **composite_prepare_kwargs,
            )
        if action == "preview":
            return service.preview(**preview_kwargs(body))
        if action == "retry":
            return service.retry(run_id=run_id, **retry_kwargs(body))
        if action == "cancel":
            return service.cancel(run_id=run_id, **cancel_kwargs(body))
        if action == "resolve_decision":
            return service.resolve_decision(
                run_id, **decision_resolve_kwargs(body)
            )
        if action == "interaction":
            return service.apply_run_interaction(
                run_id, **interaction_kwargs(body)
            )
        if action == "session_create":
            return service.create_session()
        if action == "session_clear":
            result = service.clear_session(run_id)
            if self._on_session_clear is not None:
                self._on_session_clear(run_id)
            return result
        if action == "session_delete":
            result = service.delete_session(run_id)
            if self._on_session_delete is not None:
                self._on_session_delete(run_id)
            return result
        if action == "compare":
            return service.compare_buildability(**comparison_kwargs(body))
        if action == "region_compare":
            return service.compare_buildability_regions(
                **region_comparison_kwargs(body)
            )
        if action == "constrained_compare":
            return service.compare_constrained_buildability(
                **constrained_comparison_kwargs(body)
            )
        if action == "domain_action":
            action_id = str(run_id or "").strip()
            if not action_id:
                raise ValueError("action_id must be a non-empty string")
            handler = self._action_handler
            if handler is None:
                handler = getattr(service, "estimate_area_handler", None)
            return service.execute_action(
                action_id,
                body,
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "local"),
                idempotency_key=body.get("idempotency_key"),
            )
        if action in {"workflow_validate", "workflow_revise"}:
            if not isinstance(template_id, str) or not template_id.strip():
                raise ValueError("template_id must be a non-empty string")
            contract = service.workflow_contract(
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
            return workflow_action_result(
                template_id,
                "validate" if action == "workflow_validate" else "revise",
                body,
                catalog=contract.get("catalog"),
                known_tools=contract.get("known_tools"),
                known_result_types=contract.get("known_result_types"),
            )
        if action == "tool_register":
            return service.register_tool(
                name=body.get("name", ""),
                definition=body.get("definition", {}),
                handler=self._action_handler,
            )
        if action == "run_auto":
            return self._routing_required().run(body)
        if action == "domain_select":
            return self._routing_required().select(body)
        if action == "domain_routing_override":
            return self._routing_required().override(run_id, body)
        if action == "domain_routing_clear":
            return self._routing_required().clear_unbound_session(run_id)
        raise ValueError("unknown action: " + action)

    def read(
        self,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        resource_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read one transport-neutral resource through the application seam.

        ``payload`` is the already parsed query projection.  URL parsing,
        path safety, HTTP status mapping, and file streaming remain in the
        transport adapters; this method owns semantic Service selection and
        the bounded projections shared by both HTTP entry points.
        """
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        body = self._request_body(payload)
        action = action.strip()
        service = self._service

        if action == "capabilities":
            return service.capabilities(
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
        if action == "actions":
            return service.actions(
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
        if action == "action_execution":
            return service.get_action_execution(_required_resource(resource_id, "execution_id"))
        if action == "action_executions":
            return service.list_action_executions(limit=body.get("limit", 20))
        if action == "workflow":
            contract = service.workflow_contract(
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
            return {
                "domain_id": contract.get("domain_id", "unknown"),
                "templates": contract.get("catalog", {}),
            }
        if action == "runtime_capabilities":
            max_files = body.get("max_files", 10)
            if max_files < 1 or max_files > 10:
                raise ValueError("max_files must be between 1 and 10")
            return service.runtime_capabilities(
                max_files=max_files,
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "local"),
            )
        if action == "composite_run_detail":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            return self._composite.get_run(_required_resource(resource_id, "run_id"))
        if action == "composite_observability":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            return self._composite.get_observability(
                _required_resource(resource_id, "run_id")
            )
        if action == "composite_evidence":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            return self._composite.get_evidence(
                _required_resource(resource_id, "run_id")
            )
        if action == "composite_view":
            if self._composite is None:
                raise RuntimeError("composite application is unavailable")
            return self._composite.get_view(_required_resource(resource_id, "run_id"))
        if action == "release_evidence":
            max_files = body.get("max_files", 10)
            if max_files < 1 or max_files > 10:
                raise ValueError("max_files must be between 1 and 10")
            return service.release_evidence(
                max_files=max_files,
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "local"),
            )
        if action == "decision":
            return service.get_decision(_required_resource(resource_id, "decision_id"))
        if action == "runs":
            return service.list_runs(limit=body.get("limit", 20))
        if action == "run":
            return service.get_run(
                _required_resource(resource_id, "run_id"),
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
        if action == "run_evidence":
            return service.get_run_evidence(
                run_id=_required_resource(resource_id, "run_id")
            )
        if action == "run_interaction":
            return service.get_run_interaction(
                _required_resource(resource_id, "run_id"),
                planner=body.get("planner", "rule"),
                backend=body.get("backend", "memory"),
            )
        if action == "async_observability":
            return service.get_async_observability(
                run_id=_required_resource(resource_id, "run_id")
            )
        if action == "sessions":
            return service.list_sessions(limit=body.get("limit", 50))
        if action == "session_runs":
            return service.list_session_runs(
                session_id=_required_resource(resource_id, "session_id"),
                limit=body.get("limit", 20),
            )
        if action == "metrics":
            return service.metrics()
        if action == "memory":
            return service.list_memory(
                session_id=body.get("session_id"),
                query=body.get("query"),
                limit=body.get("limit", 20),
                global_scope=body.get("global_scope", False),
            )
        if action == "dynamic_tools":
            return service.list_dynamic_tools()
        if action == "observability_health":
            state = service._state.observability
            return {
                "schema_version": "spatial-agent.observability.v1",
                "enabled": state.enabled,
                "event_count": state.event_count,
            }
        if action == "artifact_manifest":
            return build_artifact_manifest(
                body.get("artifact_payload"),
                artifact_ref=body.get("artifact_ref"),
            )
        if action == "artifact_evidence":
            artifact_payload = body.get("artifact_payload")
            if not isinstance(artifact_payload, dict):
                raise ValueError("artifact_payload must be an object")
            registry = normalize_evidence_registry(
                artifact_payload.get("evidence_registry")
            )
            return {
                "schema_version": "spatial-agent.evidence-reference.v1",
                "run_id": artifact_payload.get("run_id"),
                "domain_id": artifact_payload.get(
                    "domain_id", body.get("domain_id", "gis")
                ),
                "artifact": {
                    "available": True,
                    "ref": body.get("artifact_ref"),
                },
                "evidence_registry": registry,
                "evidence_projection": project_evidence_projection(artifact_payload),
                "evidence_recovery": project_evidence_recovery(artifact_payload),
            }
        if action == "routing_catalog":
            return self._routing_required().catalog()
        if action == "routing_metrics":
            return self._routing_required().metrics()
        raise ValueError("unknown read action: " + action)

    def _routing_required(self) -> Any:
        if self._routing is None:
            raise RuntimeError("domain routing application is unavailable")
        return self._routing

    def _request_body(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Project a request with product defaults only at a product boundary.

        Direct application callers (including offline contract tests) retain
        the historical deterministic ``rule + memory`` fallbacks.  HTTP
        production adapters opt in so omitted selections become the product's
        configured Agent mode.
        """

        if self._use_product_defaults:
            return with_product_defaults(payload)
        return dict(payload) if isinstance(payload, dict) else {}


def _required_resource(value: Optional[str], name: str) -> str:
    resource = str(value or "").strip()
    if not resource:
        raise ValueError(name + " must be a non-empty string")
    return resource


__all__ = ["HTTPApplication"]
