"""Shared HTTP request/response contract for the dev (stdlib) and production
(FastAPI) entry points.

Both entry points previously duplicated payload normalization, workflow
validate/revise handling, and exception-to-status mapping. This module keeps
those decisions in one place so the two servers cannot drift apart.
"""

from typing import Any, Dict

from agent.cost_governance import BudgetExceeded, ConcurrencyLimited
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
        "preview_fingerprint": payload.get("preview_fingerprint"),
        "preview_evidence_fingerprint": payload.get("preview_evidence_fingerprint"),
        "require_confirmation": bool(payload.get("require_confirmation", False)),
        "decision_id": payload.get("decision_id"),
        "decision_version": payload.get("decision_version"),
        "decision_ttl_seconds": payload.get("decision_ttl_seconds", 1800.0),
    }


def preview_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "request": payload.get("request", ""),
        "session_id": payload.get("session_id", "default"),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
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
        "idempotency_key": payload.get("idempotency_key"),
    }


def cancel_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
        "idempotency_key": payload.get("idempotency_key"),
    }


def decision_resolve_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "choice": payload.get("choice", ""),
        "expected_version": payload.get("expected_version"),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "memory"),
        "idempotency_key": payload.get("idempotency_key"),
    }


def interaction_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one generic run interaction without interpreting its action."""
    return {
        "action": payload.get("action", ""),
        "payload": payload,
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


def constrained_comparison_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "admin_name": payload.get("admin_name", ""),
        "road_distances": payload.get("road_distances", []),
        "slope_limit_degrees": payload.get("slope_limit_degrees", 15.0),
        "planner": payload.get("planner", "rule"),
        "backend": payload.get("backend", "local"),
        "spatial_context": payload.get("spatial_context"),
    }


# ---------------------------------------------------------------------------
# Workflow validate/revise: one implementation for both entry points.
# ---------------------------------------------------------------------------


def workflow_action_result(
    template_id: str,
    action: str,
    payload: Dict[str, Any],
    *,
    catalog: Dict[str, Any] | None = None,
    known_tools: Any = None,
    known_result_types: Any = None,
) -> Dict[str, Any]:
    template = get_workflow_template(template_id, catalog=catalog)
    if action == "validate":
        constraints = normalize_workflow_constraints(
            template,
            payload.get("constraints", {}),
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        )
        evidence = normalize_workflow_evidence(
            template,
            payload.get("evidence"),
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
        )
        plan = payload.get("plan")
        result = {
            "valid": True,
            "template": template,
            "constraints": constraints,
            "evidence": evidence,
        }
        if plan is not None:
            result["plan"] = validate_workflow_plan(
                template,
                plan,
                catalog=catalog,
                known_tools=known_tools,
                known_result_types=known_result_types,
            )
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
            catalog=catalog,
            known_tools=known_tools,
            known_result_types=known_result_types,
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
    if isinstance(exc, (BudgetExceeded, ConcurrencyLimited)):
        return 429
    if isinstance(exc, (ValueError, WorkflowTemplateError)):
        if not_found:
            return 404
        if service_unavailable:
            return 503
        return 400
    return 500


_ERROR_CODE_BY_STATUS = {
    400: "invalid_request",
    404: "not_found",
    429: "rate_limited",
    503: "unavailable",
    500: "internal_error",
}


def error_response(
    exc: Exception,
    *,
    not_found: bool = False,
    service_unavailable: bool = False,
) -> Dict[str, Any]:
    """Build the structured error contract for an endpoint failure.

    ``error`` keeps the human-readable message (backward compatible);
    ``error_code`` is a stable machine-readable category derived from the
    mapped HTTP status; ``error_category`` classifies the failure using the
    same bounded labels as the async observability layer.
    """
    status = error_status(exc, not_found=not_found, service_unavailable=service_unavailable)
    declared_code = getattr(exc, "code", None)
    stable_code = (
        str(declared_code)[:96]
        if isinstance(declared_code, str) and declared_code.strip()
        else _ERROR_CODE_BY_STATUS.get(status, "internal_error")
    )
    response = {
        "error": str(exc),
        "error_code": stable_code,
        "error_category": failure_category_for_error(exc),
    }
    action_id = getattr(exc, "action_id", None)
    if action_id:
        response["action_id"] = str(action_id)[:96]
        response["action_error_code"] = str(
            getattr(exc, "code", "action_error")
        )[:96]
        if getattr(exc, "action_execution_id", None):
            response["action_execution_id"] = str(exc.action_execution_id)[:128]
        if getattr(exc, "artifact_ref", None):
            response["artifact_ref"] = str(exc.artifact_ref)[:240]
        if isinstance(getattr(exc, "action_execution", None), dict):
            response["action_execution"] = dict(exc.action_execution)
        if isinstance(getattr(exc, "execution_record", None), dict):
            response["execution_record"] = dict(exc.execution_record)
    return response


def error_body(exc: Exception) -> Dict[str, str]:
    """Backward-compatible alias returning only the message body."""
    return {"error": str(exc)}


def failure_category_for_error(exc: Exception) -> str | None:
    """Reuse the async failure taxonomy for HTTP-level failures."""
    if isinstance(exc, BudgetExceeded):
        return "budget"
    if isinstance(exc, ConcurrencyLimited):
        return "concurrency_limited"
    text = str(exc or "").lower()
    if any(token in text for token in ("openai", "provider", "http", "url", "socket", "network", "api")):
        return "provider"
    if any(token in text for token in ("planner", "plan", "schema", "规划")):
        return "planning"
    if any(token in text for token in ("tool", "action", "backend", "dataset", "raster", "栅格", "数据")):
        return "tool"
    if any(token in text for token in ("timeout", "timed out", "超时")):
        return "timeout"
    if isinstance(exc, ValueError):
        return "invalid_input"
    return "execution"


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
