"""Production FastAPI entry point.

Route handling delegates payload normalization and workflow actions to
``agent.api_contract`` / ``HTTPApplication``; transport encoding, error
projection and artifact access are shared with ``serve_api.py`` through
``agent.application.http_transport``.
"""

import atexit
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from agent.environment_status import environment_status
from agent.domain_http import assert_domain_payload
from agent.domain_registry import resolve_domain_id
from agent.domain_runtime_host import DomainRuntimeHost
from agent.domain_routing_entry import (
    DomainRoutingApplication,
    DomainRoutingApplicationError,
    routing_state_from_environment,
)
from agent.service import AgentService
from agent.application.http import HTTPApplication
from agent.application.http_routes import resolve_route
from agent.application.composite import CompositeApplication
from agent.application.composite_runs import CompositeRunApplication
from agent.application.composite_planning import (
    CompositeCapabilityProjector,
    CompositePlanningApplication,
)
from agent.application.composite_planner import LLMCompositePlanner, RuleCompositePlanner
from agent.answer_generation import LLMCompositeAnswerGenerator
from agent.llm_planner import OpenAIPlannerClient
from agent.integration.openai_config import load_answer_generation_config, load_openai_config
from agent.application.http_transport import (
    error_projection,
    load_artifact_json,
    safe_artifact_path,
)
from agent.run_events import (
    page_contains_terminal_event,
    validate_event_cursor,
    validate_event_limit,
)
from agent.web_assets import console_asset as resolve_console_asset
from agent.web_assets import console_index as resolve_console_index
from agent.web_assets import console_root


def _composite_answer_generator():
    """Build the default structured answer pass when a model is configured.

    The run application still gates invocation on LLM planner evidence, so
    Rule/Replay and direct execution paths remain offline.  An explicit
    disable switch is retained for constrained deployments and CI.
    """

    if os.environ.get("SPATIAL_AGENT_DISABLE_LLM_ANSWER") == "1":
        return None
    try:
        config = load_answer_generation_config()
        if not config.get("api_key"):
            return None
        return LLMCompositeAnswerGenerator(OpenAIPlannerClient(**config))
    except Exception:
        return None

class UTF8JSONResponse(JSONResponse):
    """Keep JSON responses unambiguous for clients without charset sniffing."""

    media_type = "application/json; charset=utf-8"


host = DomainRuntimeHost()
host.start()
LEGACY_DOMAIN_ID = resolve_domain_id("gis")
# Plain product routes are domain-neutral.  Explicit ``/domains/{id}`` routes
# continue to use the isolated services owned by ``DomainRuntimeHost``.
service = AgentService(general=True, legacy_domain_id=LEGACY_DOMAIN_ID)
service.start_reaper()
domain_routing = DomainRoutingApplication(
    host,
    state=routing_state_from_environment(),
)
composite_application = CompositeRunApplication(
    coordinator=CompositeApplication(host=host, require_execution_binding=True),
    answer_generator=_composite_answer_generator(),
)


def _rule_composite_candidate(request, _context):
    """Offline fallback: ask for explicit planner/model selection."""
    return {
        "outcome": "needs_clarification",
        "goal": "",
        "message": "规则规划器不会猜测跨领域组合；请切换真实模型或明确提供组合能力。",
        "components": [],
    }


def _composite_planner_factory(planner_name, _backend):
    if str(planner_name).lower() == "openai":
        return LLMCompositePlanner(OpenAIPlannerClient(**load_openai_config()))
    return RuleCompositePlanner(_rule_composite_candidate)


def _composite_repair_planner_factory(planner_name, _backend):
    if str(planner_name).lower() == "openai":
        config = load_openai_config()
        config["max_retries"] = 0
        return LLMCompositePlanner(OpenAIPlannerClient(**config))
    return None


composite_planning_application = CompositePlanningApplication(
    host=host,
    projector=CompositeCapabilityProjector(host),
    planner=RuleCompositePlanner(_rule_composite_candidate),
    composite_runs=composite_application,
    planner_factory=_composite_planner_factory,
    repair_planner_factory=_composite_repair_planner_factory,
)


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
    status, payload = error_projection(
        exc,
        not_found=not_found,
        service_unavailable=service_unavailable,
    )
    raise HTTPException(status_code=status, detail=payload) from exc


def _domain_service(
    domain_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> AgentService:
    """Select the URL Domain before validating any redundant body claim."""

    selection = host.select(domain_id, source="explicit")
    assert_domain_payload(selection, payload)
    return host.service(selection)


def _http_application(target_service: AgentService = None) -> HTTPApplication:
    """Build the shared semantic dispatcher for the selected Service."""
    return HTTPApplication(
        target_service or service,
        use_product_defaults=True,
        routing=domain_routing,
        composite=composite_application,
        composite_planning=composite_planning_application,
        action_handler=AgentService.estimate_area_handler,
        on_session_clear=lambda session_id: domain_routing.forget_session(
            session_id, keep_binding=True
        ),
        on_session_delete=domain_routing.forget_session,
    )


def _shared_read(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    target_service: AgentService = None,
) -> Dict[str, Any]:
    """Use the shared route table before entering FastAPI response glue."""
    match = resolve_route("GET", path)
    if match is None:
        raise ValueError("unknown GET route: " + path)
    return _http_application(target_service).read(
        match.action,
        payload or {},
        resource_id=match.resource_id,
    )


def _shared_execute(
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    target_service: AgentService = None,
) -> Dict[str, Any]:
    """Use the shared route table before entering FastAPI response glue."""
    match = resolve_route("POST", path)
    if match is None:
        raise ValueError("unknown POST route: " + path)
    return _http_application(target_service).execute(
        match.action,
        payload or {},
        run_id=match.resource_id,
        template_id=match.template_id,
    )


def _sse_line(event: Dict[str, Any]) -> str:
    """Encode one already-normalized RunEvent as an SSE message."""
    return "id: {}\nevent: run_event\ndata: {}\n\n".format(
        event["sequence"],
        json.dumps(event, ensure_ascii=False, separators=(",", ":")),
    )


async def _run_event_stream(
    reader: HTTPApplication,
    run_id: str,
    *,
    after: int,
    limit: int,
    request: Request,
):
    """Replay persisted events and keep the connection alive with heartbeats."""
    cursor = after
    while True:
        if await request.is_disconnected():
            return
        payload = reader.read(
            "run_events",
            {"after": cursor, "limit": limit},
            resource_id=run_id,
        )
        events = payload.get("events") or []
        if events:
            for event in events:
                yield _sse_line(event)
            cursor = int(payload.get("next_cursor") or cursor)
            if page_contains_terminal_event(events):
                return
            # ``terminal`` is Run-level state. If this is the last available
            # page, there is no terminal event left to replay. Otherwise keep
            # following next_cursor until the terminal event is delivered.
            if payload.get("terminal") and not payload.get("has_more"):
                return
            continue
        if payload.get("terminal"):
            return
        yield ": heartbeat\n\n"
        await asyncio.sleep(0.75)


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
    return domain_routing.catalog()


@app.get("/domain-routing/metrics")
def domain_routing_metrics() -> Dict[str, Any]:
    return _http_application().read("routing_metrics")


@app.post("/domain-routing/select")
def select_domain(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return domain_routing.select(payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/domain-routing/decisions/{decision_id}/select")
def override_domain_routing_decision(
    decision_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return domain_routing.override(decision_id, payload)
    except Exception as exc:
        _raise_for(
            exc,
            not_found=isinstance(exc, DomainRoutingApplicationError)
            and exc.code == "domain_routing_decision_not_found",
        )


@app.post("/domain-routing/sessions/{session_id}/clear")
def clear_unbound_domain_routing_session(session_id: str) -> Dict[str, Any]:
    try:
        return domain_routing.clear_unbound_session(session_id)
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
        cursor = validate_event_cursor(
            last_event_id if last_event_id is not None else after
        )
        event_limit = validate_event_limit(limit)
        # Validate the resource before opening a streaming response so a
        # missing/foreign run produces a normal JSON error status.
        _http_application().read(
            "run_events",
            {"after": cursor, "limit": event_limit},
            resource_id=run_id,
        )
        return StreamingResponse(
            _run_event_stream(
                _http_application(),
                run_id,
                after=cursor,
                limit=event_limit,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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
    normalized_domain = str(domain_id or "").strip()[:80]
    if not normalized_domain:
        raise HTTPException(status_code=500, detail="artifact Domain is not bound")
    candidate = safe_artifact_path(
        root,
        name,
        suffix,
        prefix,
        domain_id=normalized_domain,
        metadata_root=metadata_root,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return candidate


@app.get("/artifacts/runs/{name}")
def run_artifact(name: str):
    return FileResponse(
        _safe_artifact(
            ARTIFACT_ROOT,
            name,
            ".json",
            domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
            metadata_root=ARTIFACT_ROOT,
        ),
        media_type="application/json",
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
        payload = load_artifact_json(path)
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
        payload = load_artifact_json(path)
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
    return FileResponse(
        _safe_artifact(
            ARTIFACT_ROOT,
            name,
            ".json",
            prefix="action-",
            domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
            metadata_root=ARTIFACT_ROOT,
        ),
        media_type="application/json",
    )


@app.get("/artifacts/geojson/{name}")
def geojson_artifact(name: str):
    return FileResponse(
        _safe_artifact(
            GEOJSON_ROOT,
            name,
            ".geojson",
            domain_id=getattr(service, "_resolved_domain_id", LEGACY_DOMAIN_ID),
            metadata_root=ARTIFACT_ROOT,
        ),
        media_type="application/geo+json",
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
        reader = _http_application(selected_service)
        cursor = validate_event_cursor(
            last_event_id if last_event_id is not None else after
        )
        event_limit = validate_event_limit(limit)
        reader.read(
            "run_events",
            {"after": cursor, "limit": event_limit},
            resource_id=run_id,
        )
        return StreamingResponse(
            _run_event_stream(
                reader,
                run_id,
                after=cursor,
                limit=event_limit,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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
    """Resolve an artifact against the explicit URL Domain only."""

    try:
        selection = host.select(domain_id, source="explicit")
        return _safe_artifact(
            root,
            name,
            suffix,
            prefix,
            domain_id=selection.domain_id,
            metadata_root=ARTIFACT_ROOT,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_for(exc)


def _artifact_json(path: Path) -> Dict[str, Any]:
    try:
        return load_artifact_json(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc


@app.get("/domains/{domain_id}/artifacts/runs/{name}")
def domain_run_artifact(domain_id: str, name: str):
    return FileResponse(
        _domain_artifact_path(domain_id, ARTIFACT_ROOT, name, ".json"),
        media_type="application/json",
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
    return FileResponse(
        _domain_artifact_path(
            domain_id,
            ARTIFACT_ROOT,
            name,
            ".json",
            prefix="action-",
        ),
        media_type="application/json",
    )


@app.get("/domains/{domain_id}/artifacts/geojson/{name}")
def domain_geojson_artifact(domain_id: str, name: str):
    return FileResponse(
        _domain_artifact_path(domain_id, GEOJSON_ROOT, name, ".geojson"),
        media_type="application/geo+json",
    )
