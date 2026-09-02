"""Production FastAPI entry point.

Route handling delegates payload normalization and workflow actions to
``agent.api_contract`` / ``HTTPApplication``; transport encoding, error
projection and artifact access are shared with ``serve_api.py`` through
``agent.application.http_transport``.
"""

import atexit
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from agent.environment_status import environment_status
from agent.domain_registry import resolve_domain_id
from agent.domain_routing_entry import (
    DomainRoutingApplicationError,
)
from agent.service import AgentService
from agent.application.http import HTTPApplication
from agent.application.http_composition import (
    build_http_composition,
)
from agent.application.fastapi_http import FastAPIHttpAdapter
from agent.application.http_transport import error_projection
from agent.web_assets import console_asset as resolve_console_asset
from agent.web_assets import console_index as resolve_console_index
from agent.web_assets import console_root

class UTF8JSONResponse(JSONResponse):
    """Keep JSON responses unambiguous for clients without charset sniffing."""

    media_type = "application/json; charset=utf-8"


LEGACY_DOMAIN_ID = resolve_domain_id("gis")
# Plain product routes are domain-neutral.  Explicit ``/domains/{id}`` routes
# continue to use the isolated services owned by ``DomainRuntimeHost``.
_http_composition = build_http_composition(legacy_domain_id=LEGACY_DOMAIN_ID)
host = _http_composition.host
service = _http_composition.service
domain_routing = _http_composition.routing
composite_application = _http_composition.composite
composite_planning_application = _http_composition.composite_planning


def _fastapi_dependencies() -> Dict[str, Any]:
    """Resolve patched entry-point dependencies at request time."""

    return {
        "host": host,
        "service": service,
        "domain_routing": domain_routing,
        "composite_application": composite_application,
        "composite_planning_application": composite_planning_application,
    }


_fastapi_http = FastAPIHttpAdapter(_fastapi_dependencies)


def _close_host() -> None:
    """Release every module-level Domain service exactly once.

    ``DomainRuntimeHost.close`` is idempotent, so FastAPI lifespan shutdown
    and the direct-import atexit fallback can safely share this hook.
    """
    composite_application.close()
    service.close()
    host.close()


@asynccontextmanager
async def _lifespan(_app):
    """Own all enabled Domain services for the ASGI application life."""
    try:
        yield
    finally:
        _close_host()


app = FastAPI(
    title="Spatial Agent Production API",
    default_response_class=UTF8JSONResponse,
    lifespan=_lifespan,
)
atexit.register(_close_host)

ARTIFACT_ROOT = Path(os.environ.get("SPATIAL_AGENT_ARTIFACT_ROOT", "outputs/runs"))
GEOJSON_ROOT = Path(os.environ.get("SPATIAL_AGENT_GEOJSON_ROOT", "outputs/geojson"))
WEB_ROOT = console_root()


def runtime_capability_snapshot(max_files: int = 10) -> Dict[str, Any]:
    """Compatibility name backed by the Service/Domain Pack runtime seam."""
    return service.runtime_capabilities(max_files=max_files, backend="local")


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    body = {"error": str(exc.detail)}
    # Preserve the structured contract when the detail is already a payload.
    if isinstance(exc.detail, dict):
        body = exc.detail
    return UTF8JSONResponse(status_code=exc.status_code, content=body)


def _raise_for(exc: Exception, *, not_found: bool = False, service_unavailable: bool = False):
    return _fastapi_http.raise_for(
        exc,
        not_found=not_found,
        service_unavailable=service_unavailable,
    )


def _domain_service(
    domain_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> AgentService:
    return _fastapi_http.domain_service(domain_id, payload)


def _http_application(target_service: AgentService = None) -> HTTPApplication:
    return _fastapi_http.http_application(target_service)


def _shared_read(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    target_service: AgentService = None,
) -> Dict[str, Any]:
    return _fastapi_http.read(path, payload, target_service=target_service)


def _shared_execute(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    target_service: AgentService = None,
) -> Dict[str, Any]:
    return _fastapi_http.execute(path, payload, target_service=target_service)


def _sse_line(event: Dict[str, Any]) -> str:
    return _fastapi_http.sse_line(event)


async def _run_event_stream(
    reader: HTTPApplication,
    run_id: str,
    *,
    after: int,
    limit: int,
    request: Request,
):
    async for chunk in _fastapi_http.event_stream(
        reader,
        run_id,
        after=after,
        limit=limit,
        request=request,
        sleep=asyncio.sleep,
    ):
        yield chunk


@app.get("/health/live")
def liveness() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(response: Response) -> Dict[str, Any]:
    status = environment_status()
    required_gis = os.environ.get("SPATIAL_AGENT_REQUIRE_GIS", "0").lower() in ("1", "true", "yes")
    required_manifest = os.environ.get("SPATIAL_AGENT_REQUIRE_DATASET_MANIFEST", "0").lower() in ("1", "true", "yes")
    ready = True
    if required_gis and (
        not status["capabilities"]["local_gis_backend"]
        or not status["data"]["gdal_data_available"]
        or not status["data"]["proj_data_available"]
    ):
        ready = False
    if required_manifest:
        snapshot = runtime_capability_snapshot(max_files=1)
        manifest = snapshot.get("manifest") or {}
        status["dataset_manifest"] = manifest
        if snapshot.get("data_readiness") != "ready":
            ready = False
    else:
        status["dataset_manifest"] = {"required": False, "status": "not_required"}
    if not ready:
        response.status_code = 503
    status["status"] = "ready" if ready else "not_ready"
    return status


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", **environment_status()}


@app.get("/capabilities")
def capabilities(
    planner: Optional[str] = None,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    return _shared_read(
        "/capabilities", {"planner": planner, "backend": backend}
    )


@app.get("/domains")
def domains() -> Dict[str, Any]:
    return host.catalog()


@app.get("/domain-routing/catalog")
def domain_routing_catalog() -> Dict[str, Any]:
    return _shared_read("/domain-routing/catalog")


@app.get("/domain-routing/metrics")
def domain_routing_metrics() -> Dict[str, Any]:
    return _http_application().read("routing_metrics")


@app.post("/domain-routing/select")
def select_domain(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _shared_execute("/domain-routing/select", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/domain-routing/decisions/{decision_id}/select")
def override_domain_routing_decision(
    decision_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return _shared_execute(
            "/domain-routing/decisions/" + decision_id + "/select", payload
        )
    except Exception as exc:
        _raise_for(
            exc,
            not_found=isinstance(exc, DomainRoutingApplicationError)
            and exc.code == "domain_routing_decision_not_found",
        )


@app.post("/domain-routing/sessions/{session_id}/clear")
def clear_unbound_domain_routing_session(session_id: str) -> Dict[str, Any]:
    try:
        return _shared_execute(
            "/domain-routing/sessions/" + session_id + "/clear", {}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/actions")
def actions(planner: Optional[str] = None, backend: Optional[str] = None) -> Dict[str, Any]:
    return _shared_read(
        "/actions", {"planner": planner, "backend": backend}
    )


@app.get("/action-executions/{execution_id}")
def action_execution(execution_id: str) -> Dict[str, Any]:
    try:
        return _shared_read(
            "/action-executions/" + execution_id,
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/action-executions")
def action_executions(limit: int = 20) -> Dict[str, Any]:
    try:
        return _shared_read("/action-executions", {"limit": limit})
    except Exception as exc:
        _raise_for(exc)


@app.get("/capabilities/runtime")
def runtime_capabilities(max_files: int = 10) -> Dict[str, Any]:
    try:
        return _shared_read(
            "/capabilities/runtime",
            {"max_files": max_files, "backend": "local"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/release-evidence")
def release_evidence(max_files: int = 10) -> Dict[str, Any]:
    try:
        return _shared_read(
            "/release-evidence",
            {"max_files": max_files, "backend": "local"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def console():
    return FileResponse(resolve_console_index(), media_type="text/html")


@app.get("/index.html")
def console_index():
    return FileResponse(resolve_console_index(), media_type="text/html")


@app.get("/console_{asset_name}.js")
def console_asset(asset_name: str):
    filename = "console_" + asset_name + ".js"
    path = resolve_console_asset(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="web asset not found")
    return FileResponse(path, media_type="application/javascript")


@app.get("/styles.css")
def console_styles():
    path = resolve_console_asset("styles.css")
    if path is None:
        raise HTTPException(status_code=404, detail="web asset not found")
    return FileResponse(path, media_type="text/css")


@app.post("/runs")
def run(payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/composite-runs")
def composite_run(payload: Dict[str, Any]):
    try:
        return _shared_execute("/composite-runs", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/composite-plans")
def composite_plan(payload: Dict[str, Any]):
    try:
        return _shared_execute("/composite-plans", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/composite-runs/async")
def composite_run_async(payload: Dict[str, Any]):
    try:
        return _shared_execute("/composite-runs/async", payload)
    except Exception as exc:
        _raise_for(exc)


@app.get("/composite-runs/{run_id}/observability")
def composite_observability(run_id: str):
    try:
        return _http_application().read(
            "composite_observability", resource_id=run_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/composite-runs/{run_id}/evidence")
def composite_evidence(run_id: str):
    try:
        return _http_application().read("composite_evidence", resource_id=run_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/composite-runs/{run_id}/view")
def composite_view(run_id: str):
    try:
        return _http_application().read("composite_view", resource_id=run_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/composite-runs/{run_id}")
def composite_detail(run_id: str):
    try:
        return _http_application().read("composite_run_detail", resource_id=run_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/runs/auto")
def run_auto(payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs/auto", payload)
    except Exception as exc:
        _raise_for(
            exc,
            not_found=isinstance(exc, DomainRoutingApplicationError)
            and exc.code == "domain_routing_decision_not_found",
        )


@app.post("/runs/preview")
def preview(payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs/preview", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/async")
def run_async(payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs/async", payload)
    except Exception as exc:
        _raise_for(exc)


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: str):
    try:
        return _shared_read("/decisions/" + decision_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/decisions/{decision_id}/resolve")
def resolve_decision(decision_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute(
            "/decisions/" + decision_id + "/resolve", payload
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/runs")
def list_runs(limit: int = 20):
    try:
        return _shared_read("/runs", {"limit": limit})
    except Exception as exc:
        _raise_for(exc)


@app.get("/sessions")
def list_sessions(limit: int = 50):
    try:
        return _shared_read("/sessions", {"limit": limit})
    except Exception as exc:
        _raise_for(exc)


@app.get("/sessions/{session_id}/runs")
def list_session_runs(session_id: str, limit: int = 20):
    try:
        return _shared_read(
            "/sessions/" + session_id + "/runs", {"limit": limit}
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/sessions")
def create_session():
    try:
        return _shared_execute("/sessions", {})
    except Exception as exc:
        _raise_for(exc, service_unavailable=True)


@app.post("/sessions/{session_id}/clear")
def clear_session(session_id: str):
    try:
        return _shared_execute("/sessions/" + session_id + "/clear", {})
    except Exception as exc:
        _raise_for(exc)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        return _http_application().execute("session_delete", {}, run_id=session_id)
    except Exception as exc:
        _raise_for(exc)


@app.get("/metrics")
def metrics():
    return _shared_read("/metrics")


@app.get("/memory")
def memory(
    session_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    global_scope: bool = False,
):
    try:
        return _shared_read(
            "/memory",
            {
                "session_id": session_id,
                "query": query,
                "limit": limit,
                "global_scope": global_scope,
            },
        )
    except ValueError as exc:
        _raise_for(exc)


@app.get("/observability/health")
def observability_health():
    return _shared_read("/observability/health")


@app.get("/tools/dynamic")
def list_dynamic_tools():
    return _shared_read("/tools/dynamic")


@app.get("/tools/approvals")
def list_tool_approvals(limit: int = 50, status: Optional[str] = None):
    try:
        return _shared_read(
            "/tools/approvals", {"limit": limit, "status": status}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/tools/approvals/{approval_id}")
def get_tool_approval(approval_id: str):
    try:
        return _shared_read("/tools/approvals/" + approval_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/tools/approvals/{approval_id}/resolve")
def resolve_tool_approval(approval_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute(
            "/tools/approvals/" + approval_id + "/resolve", payload
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/tools/approvals")
def domain_list_tool_approvals(
    domain_id: str, limit: int = 50, status: Optional[str] = None
):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "tool_approvals", {"limit": limit, "status": status}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/tools/approvals/{approval_id}")
def domain_get_tool_approval(domain_id: str, approval_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "tool_approval", resource_id=approval_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/domains/{domain_id}/tools/approvals/{approval_id}/resolve")
def domain_resolve_tool_approval(
    domain_id: str, approval_id: str, payload: Dict[str, Any]
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "tool_approval_resolve", payload, run_id=approval_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/tools")
def register_tool(payload: Dict[str, Any]):
    try:
        return _shared_execute("/tools", payload)
    except Exception as exc:
        _raise_for(exc)


@app.get("/workflows")
def workflows(planner: Optional[str] = None, backend: Optional[str] = None):
    return _shared_read(
        "/workflows", {"planner": planner, "backend": backend}
    )


@app.post("/workflows/{template_id}/validate")
def validate_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute(
            "/workflows/" + template_id + "/validate", payload
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/workflows/{template_id}/revise")
def revise_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute(
            "/workflows/" + template_id + "/revise", payload
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/runs/{run_id}")
def get_run(run_id: str, planner: Optional[str] = None, backend: Optional[str] = None):
    try:
        return _shared_read(
            "/runs/" + run_id,
            {"planner": planner, "backend": backend},
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/runs/{run_id}/evidence")
def run_evidence(run_id: str):
    try:
        return _shared_read("/runs/" + run_id + "/evidence")
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/runs/{run_id}/interaction")
def run_interaction(run_id: str, planner: Optional[str] = None, backend: Optional[str] = None):
    try:
        return _shared_read(
            "/runs/" + run_id + "/interaction",
            {"planner": planner, "backend": backend},
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/runs/{run_id}/interaction")
def apply_run_interaction(run_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute(
            "/runs/" + run_id + "/interaction", payload
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/runs/{run_id}/observability")
@app.get("/runs/{run_id}/async")
def async_observability(run_id: str):
    try:
        return _shared_read("/runs/" + run_id + "/async")
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    after: Optional[int] = None,
    limit: int = 100,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    try:
        return _fastapi_http.event_stream_response(
            run_id,
            request,
            after=last_event_id if last_event_id is not None else after,
            limit=limit,
            sleep=asyncio.sleep,
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/comparisons")
def compare(payload: Dict[str, Any]):
    try:
        return _shared_execute("/comparisons", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/region-comparisons")
def compare_regions(payload: Dict[str, Any]):
    try:
        return _shared_execute("/region-comparisons", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/constrained-comparisons")
def compare_constrained(payload: Dict[str, Any]):
    try:
        return _shared_execute("/constrained-comparisons", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/actions/{action_id}")
def execute_action(action_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute("/actions/" + action_id, payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/{run_id}/retry")
def retry(run_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs/" + run_id + "/retry", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/{run_id}/cancel")
def cancel(run_id: str, payload: Dict[str, Any]):
    try:
        return _shared_execute("/runs/" + run_id + "/cancel", payload)
    except Exception as exc:
        _raise_for(exc)


def _safe_artifact(
    root: Path,
    name: str,
    suffix: str,
    prefix: str = "",
    *,
    domain_id: Optional[str] = None,
    metadata_root: Optional[Path] = None,
) -> Path:
    return _fastapi_http.artifact_path(
        root,
        name,
        suffix,
        prefix,
        domain_id=domain_id,
        metadata_root=metadata_root,
    )


@app.get("/artifacts/runs/{name}")
def run_artifact(name: str):
    return _fastapi_http.artifact_response(
        ARTIFACT_ROOT,
        name,
        ".json",
        "application/json",
        domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
        metadata_root=ARTIFACT_ROOT,
    )


@app.get("/artifacts/runs/{name}/manifest")
def run_artifact_manifest(name: str):
    path = _safe_artifact(
        ARTIFACT_ROOT,
        name,
        ".json",
        domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
        metadata_root=ARTIFACT_ROOT,
    )
    try:
        payload = _artifact_json(path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return _http_application().read(
        "artifact_manifest",
        {"artifact_payload": payload, "artifact_ref": path.name},
    )


@app.get("/artifacts/runs/{name}/evidence")
def run_artifact_evidence(name: str):
    path = _safe_artifact(
        ARTIFACT_ROOT,
        name,
        ".json",
        domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
        metadata_root=ARTIFACT_ROOT,
    )
    try:
        payload = _artifact_json(path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    return _http_application().read(
        "artifact_evidence",
        {
            "artifact_payload": payload,
            "artifact_ref": path.name,
        },
    )


@app.get("/artifacts/actions/{name}")
def action_artifact(name: str):
    return _fastapi_http.artifact_response(
        ARTIFACT_ROOT,
        name,
        ".json",
        "application/json",
        prefix="action-",
        domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
        metadata_root=ARTIFACT_ROOT,
    )


@app.get("/artifacts/geojson/{name}")
def geojson_artifact(name: str):
    return _fastapi_http.artifact_response(
        GEOJSON_ROOT,
        name,
        ".geojson",
        "application/geo+json",
        domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
        metadata_root=ARTIFACT_ROOT,
    )


# Explicit multi-Domain routes.  The URL selection is authoritative; legacy
# routes above intentionally retain their original module-level Service.


@app.get("/domains/{domain_id}/capabilities")
def domain_capabilities(
    domain_id: str,
    planner: Optional[str] = None,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "capabilities", {"planner": planner, "backend": backend}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/capabilities/runtime")
def domain_runtime_capabilities(domain_id: str, max_files: int = 10) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "runtime_capabilities", {"max_files": max_files, "backend": "local"}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/release-evidence")
def domain_release_evidence(domain_id: str, max_files: int = 10) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "release_evidence", {"max_files": max_files, "backend": "local"}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/actions")
def domain_actions(
    domain_id: str,
    planner: Optional[str] = None,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "actions", {"planner": planner, "backend": backend}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/action-executions/{execution_id}")
def domain_action_execution(domain_id: str, execution_id: str) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "action_execution", resource_id=execution_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/domains/{domain_id}/action-executions")
def domain_action_executions(domain_id: str, limit: int = 20) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "action_executions", {"limit": limit}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/workflows")
def domain_workflows(
    domain_id: str,
    planner: Optional[str] = None,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "workflow", {"planner": planner, "backend": backend}
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/workflows/{template_id}/validate")
def domain_validate_workflow(
    domain_id: str,
    template_id: str,
    payload: Dict[str, Any],
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "workflow_validate", payload, template_id=template_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/workflows/{template_id}/revise")
def domain_revise_workflow(
    domain_id: str,
    template_id: str,
    payload: Dict[str, Any],
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "workflow_revise", payload, template_id=template_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/runs")
def domain_run(domain_id: str, payload: Dict[str, Any]):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute("run", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/runs/preview")
def domain_preview(domain_id: str, payload: Dict[str, Any]):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute("preview", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/runs/async")
def domain_run_async(domain_id: str, payload: Dict[str, Any]):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute("run_async", payload)
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/runs")
def domain_list_runs(domain_id: str, limit: int = 20):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "runs", {"limit": limit}
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/runs/{run_id}")
def domain_get_run(
    domain_id: str,
    run_id: str,
    planner: Optional[str] = None,
    backend: Optional[str] = None,
):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "run",
            {"planner": planner, "backend": backend},
            resource_id=run_id,
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/domains/{domain_id}/runs/{run_id}/evidence")
def domain_run_evidence(domain_id: str, run_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "run_evidence", resource_id=run_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/domains/{domain_id}/runs/{run_id}/interaction")
def domain_run_interaction(
    domain_id: str,
    run_id: str,
    planner: Optional[str] = None,
    backend: Optional[str] = None,
):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "run_interaction",
            {"planner": planner, "backend": backend},
            resource_id=run_id,
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/domains/{domain_id}/runs/{run_id}/interaction")
def domain_apply_run_interaction(
    domain_id: str,
    run_id: str,
    payload: Dict[str, Any],
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "interaction", payload, run_id=run_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/runs/{run_id}/observability")
@app.get("/domains/{domain_id}/runs/{run_id}/async")
def domain_async_observability(domain_id: str, run_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "async_observability", resource_id=run_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/domains/{domain_id}/runs/{run_id}/events")
async def domain_run_events(
    domain_id: str,
    run_id: str,
    request: Request,
    after: Optional[int] = None,
    limit: int = 100,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
):
    try:
        selected_service = _domain_service(domain_id)
        return _fastapi_http.event_stream_response(
            run_id,
            request,
            after=last_event_id if last_event_id is not None else after,
            limit=limit,
            target_service=selected_service,
            sleep=asyncio.sleep,
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/domains/{domain_id}/runs/{run_id}/retry")
def domain_retry(domain_id: str, run_id: str, payload: Dict[str, Any]):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "retry", payload, run_id=run_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/runs/{run_id}/cancel")
def domain_cancel(domain_id: str, run_id: str, payload: Dict[str, Any]):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "cancel", payload, run_id=run_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/decisions/{decision_id}")
def domain_get_decision(domain_id: str, decision_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "decision", resource_id=decision_id
        )
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/domains/{domain_id}/decisions/{decision_id}/resolve")
def domain_resolve_decision(
    domain_id: str,
    decision_id: str,
    payload: Dict[str, Any],
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "resolve_decision", payload, run_id=decision_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/sessions")
def domain_list_sessions(domain_id: str, limit: int = 50):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "sessions", {"limit": limit}
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/sessions")
def domain_create_session(
    domain_id: str, payload: Optional[Dict[str, Any]] = None
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute("session_create", {})
    except Exception as exc:
        _raise_for(exc, service_unavailable=True)


@app.get("/domains/{domain_id}/sessions/{session_id}/runs")
def domain_list_session_runs(domain_id: str, session_id: str, limit: int = 20):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "session_runs", {"limit": limit}, resource_id=session_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/sessions/{session_id}/clear")
def domain_clear_session(
    domain_id: str,
    session_id: str,
    payload: Optional[Dict[str, Any]] = None,
):
    try:
        selected_service = _domain_service(domain_id, payload)
        return _http_application(selected_service).execute(
            "session_clear", payload or {}, run_id=session_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.delete("/domains/{domain_id}/sessions/{session_id}")
def domain_delete_session(domain_id: str, session_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).execute(
            "session_delete", {}, run_id=session_id
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/metrics")
def domain_metrics(domain_id: str):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read("metrics")
    except Exception as exc:
        _raise_for(exc)


@app.get("/domains/{domain_id}/memory")
def domain_memory(
    domain_id: str,
    session_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    global_scope: bool = False,
):
    try:
        selected_service = _domain_service(domain_id)
        return _http_application(selected_service).read(
            "memory",
            {
                "session_id": session_id,
                "query": query,
                "limit": limit,
                "global_scope": global_scope,
            },
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/domains/{domain_id}/actions/{action_id}")
def domain_execute_action(
    domain_id: str,
    action_id: str,
    payload: Dict[str, Any],
):
    try:
        selected_service = _domain_service(domain_id, payload)
        action_payload = dict(payload)
        action_payload.pop("domain_id", None)
        action_payload.pop("domain_selection", None)
        return _http_application(selected_service).execute(
            "domain_action", action_payload, run_id=action_id
        )
    except Exception as exc:
        _raise_for(exc)


def _domain_artifact_path(
    domain_id: str,
    root: Path,
    name: str,
    suffix: str,
    prefix: str = "",
) -> Path:
    return _fastapi_http.domain_artifact_path(
        domain_id,
        root,
        name,
        suffix,
        prefix,
        metadata_root=ARTIFACT_ROOT,
    )


def _artifact_json(path: Path) -> Dict[str, Any]:
    return _fastapi_http.artifact_json(path)


@app.get("/domains/{domain_id}/artifacts/runs/{name}")
def domain_run_artifact(domain_id: str, name: str):
    return _fastapi_http.domain_artifact_response(
        domain_id,
        ARTIFACT_ROOT,
        name,
        ".json",
        "application/json",
        metadata_root=ARTIFACT_ROOT,
    )


@app.get("/domains/{domain_id}/artifacts/runs/{name}/manifest")
def domain_run_artifact_manifest(domain_id: str, name: str):
    path = _domain_artifact_path(domain_id, ARTIFACT_ROOT, name, ".json")
    selected_service = _domain_service(domain_id)
    return _http_application(selected_service).read(
        "artifact_manifest",
        {"artifact_payload": _artifact_json(path), "artifact_ref": path.name},
    )


@app.get("/domains/{domain_id}/artifacts/runs/{name}/evidence")
def domain_run_artifact_evidence(domain_id: str, name: str):
    path = _domain_artifact_path(domain_id, ARTIFACT_ROOT, name, ".json")
    selected_service = _domain_service(domain_id)
    return _http_application(selected_service).read(
        "artifact_evidence",
        {
            "artifact_payload": _artifact_json(path),
            "artifact_ref": path.name,
            "domain_id": domain_id,
        },
    )


@app.get("/domains/{domain_id}/artifacts/actions/{name}")
def domain_action_artifact(domain_id: str, name: str):
    return _fastapi_http.domain_artifact_response(
        domain_id,
        ARTIFACT_ROOT,
        name,
        ".json",
        "application/json",
        prefix="action-",
        metadata_root=ARTIFACT_ROOT,
    )


@app.get("/domains/{domain_id}/artifacts/geojson/{name}")
def domain_geojson_artifact(domain_id: str, name: str):
    return _fastapi_http.domain_artifact_response(
        domain_id,
        GEOJSON_ROOT,
        name,
        ".geojson",
        "application/geo+json",
        metadata_root=ARTIFACT_ROOT,
    )
