"""Shared HTTP request/response contract for the dev (stdlib) and production
(FastAPI) entry points.

Both entry points previously duplicated payload normalization, workflow
validate/revise handling, and exception-to-status mapping. This module keeps
those decisions in one place so the two servers cannot drift apart.
"""

from typing import Any, Dict, Tuple

from agent.service import AgentService
from agent.workflow_templates import (
    WorkflowTemplateError,
    get_workflow_template,
    normalize_workflow_constraints,
    normalize_workflow_evidence,
    revise_workflow_plan,
    validate_workflow_plan,
)

# ---------------------------------------------------------------------------
# Payload normalization: keyword arguments for each AgentService call.
# ---------------------------------------------------------------------------


def run_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "request": payload.get("request", ""),
        "session_id": payload.get("session_id", "default"),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
        "export_artifact": bool(payload.get("export_artifact", False)),
        "export_geojson": bool(payload.get("export_geojson", False)),
        "geojson_max_features": payload.get("geojson_max_features", 100),
        "timeout_seconds": payload.get("timeout_seconds"),
        "spatial_context": payload.get("spatial_context"),
        "workflow": payload.get("workflow"),
    }


def async_run_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **run_kwargs(payload),
        "idempotency_key": payload.get("idempotency_key"),
    }


def retry_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
        "export_artifact": bool(payload.get("export_artifact", False)),
        "export_geojson": bool(payload.get("export_geojson", False)),
        "geojson_max_features": payload.get("geojson_max_features", 100),
    }


def cancel_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
    }


def comparison_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "admin_name": payload.get("admin_name", ""),
        "thresholds": payload.get("thresholds", []),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "local"),
        "spatial_context": payload.get("spatial_context"),
    }


def region_comparison_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "admin_names": payload.get("admin_names", []),
        "threshold": payload.get("threshold", 20),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "local"),
    }


# ---------------------------------------------------------------------------
# Workflow validate/revise: one implementation for both entry points.
# ---------------------------------------------------------------------------


def workflow_action_result(template_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    template = get_workflow_template(template_id)
    if action == "validate":
        constraints = normalize_workflow_constraints(template, payload.get("constraints", {}))
        evidence = normalize_workflow_evidence(template, payload.get("evidence"))
        plan = payload.get("plan")
        result = {
            "valid": True,
            "template": template,
            "constraints": constraints,
            "evidence": evidence,
        }
        if plan is not None:
            result["plan"] = validate_workflow_plan(template, plan)
        return result
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        raise WorkflowTemplateError("revise requires a plan object")
    return {
        "valid": True,
        "template": template,
        "plan": revise_workflow_plan(
            template,
            plan,
            constraints=payload.get("constraints"),
            evidence=payload.get("evidence"),
        ),
    }


# ---------------------------------------------------------------------------
# Exception mapping: one consistent status code per error class per endpoint.
# ---------------------------------------------------------------------------


def error_status(
    exc: Exception,
    *,
    not_found: bool = False,
    service_unavailable: bool = False,
) -> int:
    """Map an exception to the HTTP status the endpoint should return.

    The dev server and FastAPI entry point previously disagreed on several
    codes (e.g. create_session 503 vs 400). This is the single decision point.
    """
    if isinstance(exc, (ValueError, WorkflowTemplateError)):
        if not_found:
            return 404
        if service_unavailable:
            return 503
        return 400
    return 500


def error_body(exc: Exception) -> Dict[str, str]:
    return {"error": str(exc)}


def dispatch(service: AgentService, action: str, run_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Route a POST body to the matching service call.

    action is one of: run, run_async, retry, cancel, compare, region_compare,
    session_create, session_clear, workflow_validate, workflow_revise.
    """
    if action == "run":
        return service.run(**run_kwargs(payload))
    if action == "run_async":
        return service.run_async(**async_run_kwargs(payload))
    if action == "retry":
        return service.retry(run_id=run_id, **retry_kwargs(payload))
    if action == "cancel":
        return service.cancel(run_id=run_id, **cancel_kwargs(payload))
    if action == "compare":
        return service.compare_buildability(**comparison_kwargs(payload))
    if action == "region_compare":
        return service.compare_buildability_regions(**region_comparison_kwargs(payload))
    if action == "session_create":
        return service.create_session()
    if action == "session_clear":
        return service.clear_session(run_id)
    raise ValueError("unknown action: " + action)
