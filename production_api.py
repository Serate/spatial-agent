"""Production FastAPI entry point.

Route handling delegates payload normalization, workflow actions, and
exception mapping to agent.api_contract so this server cannot drift from the
dev server in serve_api.py.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from agent.api_contract import (
    async_run_kwargs,
    cancel_kwargs,
    comparison_kwargs,
    constrained_comparison_kwargs,
    error_response,
    error_status,
    region_comparison_kwargs,
    retry_kwargs,
    preview_kwargs,
    run_kwargs,
    workflow_action_result,
)
from agent.environment_status import environment_status
from agent.domain_registry import domain_registry
from agent.service import AgentService
from agent.workflow_templates import workflow_template_catalog

app = FastAPI(title="Spatial Agent Production API")
service = AgentService()
service.start_reaper()

ARTIFACT_ROOT = Path(os.environ.get("SPATIAL_AGENT_ARTIFACT_ROOT", "outputs/runs"))
GEOJSON_ROOT = Path(os.environ.get("SPATIAL_AGENT_GEOJSON_ROOT", "outputs/geojson"))
WEB_ROOT = Path(__file__).parent / "web"


def runtime_capability_snapshot(max_files: int = 10) -> Dict[str, Any]:
    """Compatibility name backed by the Service/Domain Pack runtime seam."""
    return service.runtime_capabilities(max_files=max_files, backend="local")


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    body = {"error": str(exc.detail)}
    # Preserve the structured contract when the detail is already a payload.
    if isinstance(exc.detail, dict):
        body = exc.detail
    return JSONResponse(status_code=exc.status_code, content=body)


def _raise_for(exc: Exception, *, not_found: bool = False, service_unavailable: bool = False):
    status = error_status(exc, not_found=not_found, service_unavailable=service_unavailable)
    raise HTTPException(status_code=status, detail=error_response(
        exc, not_found=not_found, service_unavailable=service_unavailable
    )) from exc


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
    planner: str = "rule",
    backend: str = "memory",
) -> Dict[str, Any]:
    return service.capabilities(planner=planner, backend=backend)


@app.get("/domains")
def domains() -> Dict[str, Any]:
    return domain_registry().catalog()


@app.get("/actions")
def actions(planner: str = "rule", backend: str = "memory") -> Dict[str, Any]:
    return service.actions(planner=planner, backend=backend)


@app.get("/action-executions/{execution_id}")
def action_execution(execution_id: str) -> Dict[str, Any]:
    try:
        return service.get_action_execution(execution_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/action-executions")
def action_executions(limit: int = 20) -> Dict[str, Any]:
    try:
        return service.list_action_executions(limit=limit)
    except Exception as exc:
        _raise_for(exc)


@app.get("/capabilities/runtime")
def runtime_capabilities(max_files: int = 10) -> Dict[str, Any]:
    try:
        if max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        return runtime_capability_snapshot(max_files=max_files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/release-evidence")
def release_evidence(max_files: int = 10) -> Dict[str, Any]:
    try:
        if max_files < 1 or max_files > 10:
            raise ValueError("max_files must be between 1 and 10")
        return service.release_evidence(max_files=max_files, backend="local")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def console():
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/index.html")
def console_index():
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.post("/runs")
def run(payload: Dict[str, Any]):
    try:
        return service.run(**run_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/preview")
def preview(payload: Dict[str, Any]):
    try:
        return service.preview(**preview_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/async")
def run_async(payload: Dict[str, Any]):
    try:
        return service.run_async(**async_run_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.get("/runs")
def list_runs(limit: int = 20):
    try:
        return service.list_runs(limit=limit)
    except Exception as exc:
        _raise_for(exc)


@app.get("/sessions")
def list_sessions(limit: int = 50):
    try:
        return service.list_sessions(limit=limit)
    except Exception as exc:
        _raise_for(exc)


@app.get("/sessions/{session_id}/runs")
def list_session_runs(session_id: str, limit: int = 20):
    try:
        return service.list_session_runs(session_id=session_id, limit=limit)
    except Exception as exc:
        _raise_for(exc)


@app.post("/sessions")
def create_session():
    try:
        return service.create_session()
    except Exception as exc:
        _raise_for(exc, service_unavailable=True)


@app.post("/sessions/{session_id}/clear")
def clear_session(session_id: str):
    try:
        return service.clear_session(session_id)
    except Exception as exc:
        _raise_for(exc)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        return service.delete_session(session_id)
    except Exception as exc:
        _raise_for(exc)


@app.get("/metrics")
def metrics():
    return service.metrics()


@app.get("/memory")
def memory(
    session_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    global_scope: bool = False,
):
    try:
        return service.list_memory(
            session_id=session_id,
            query=query,
            limit=limit,
            global_scope=global_scope,
        )
    except ValueError as exc:
        _raise_for(exc)


@app.get("/observability/health")
def observability_health():
    state = service._state.observability
    return {
        "schema_version": "spatial-agent.observability.v1",
        "enabled": state.enabled,
        "event_count": state.event_count,
    }


@app.get("/tools/dynamic")
def list_dynamic_tools():
    return service.list_dynamic_tools()


@app.post("/tools")
def register_tool(payload: Dict[str, Any]):
    try:
        return service.register_tool(
            name=payload.get("name", ""),
            definition=payload.get("definition", {}),
            handler=AgentService.estimate_area_handler,
        )
    except Exception as exc:
        _raise_for(exc)


@app.get("/workflows")
def workflows():
    return {"templates": workflow_template_catalog()}


@app.post("/workflows/{template_id}/validate")
def validate_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        return workflow_action_result(template_id, "validate", payload)
    except Exception as exc:
        _raise_for(exc)


@app.post("/workflows/{template_id}/revise")
def revise_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        return workflow_action_result(template_id, "revise", payload)
    except Exception as exc:
        _raise_for(exc)


@app.get("/runs/{run_id}")
def get_run(run_id: str, planner: str = "rule", backend: str = "memory"):
    try:
        return service.get_run(run_id=run_id, planner=planner, backend=backend)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.get("/runs/{run_id}/observability")
@app.get("/runs/{run_id}/async")
def async_observability(run_id: str):
    try:
        return service.get_async_observability(run_id=run_id)
    except Exception as exc:
        _raise_for(exc, not_found=True)


@app.post("/comparisons")
def compare(payload: Dict[str, Any]):
    try:
        return service.compare_buildability(**comparison_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/region-comparisons")
def compare_regions(payload: Dict[str, Any]):
    try:
        return service.compare_buildability_regions(**region_comparison_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/constrained-comparisons")
def compare_constrained(payload: Dict[str, Any]):
    try:
        return service.compare_constrained_buildability(**constrained_comparison_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/actions/{action_id}")
def execute_action(action_id: str, payload: Dict[str, Any]):
    try:
        return service.execute_action(
            action_id,
            payload,
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
            idempotency_key=payload.get("idempotency_key"),
        )
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/{run_id}/retry")
def retry(run_id: str, payload: Dict[str, Any]):
    try:
        return service.retry(run_id=run_id, **retry_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


@app.post("/runs/{run_id}/cancel")
def cancel(run_id: str, payload: Dict[str, Any]):
    try:
        return service.cancel(run_id=run_id, **cancel_kwargs(payload))
    except Exception as exc:
        _raise_for(exc)


def _safe_artifact(root: Path, name: str, suffix: str, prefix: str = "") -> Path:
    candidate = (root / Path(name).name).resolve()
    if (
        root.resolve() not in candidate.parents
        or candidate.suffix != suffix
        or (prefix and not candidate.name.startswith(prefix))
    ):
        raise HTTPException(status_code=404, detail="artifact not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return candidate


@app.get("/artifacts/runs/{name}")
def run_artifact(name: str):
    return FileResponse(_safe_artifact(ARTIFACT_ROOT, name, ".json"), media_type="application/json")


@app.get("/artifacts/actions/{name}")
def action_artifact(name: str):
    return FileResponse(_safe_artifact(ARTIFACT_ROOT, name, ".json", prefix="action-"), media_type="application/json")


@app.get("/artifacts/geojson/{name}")
def geojson_artifact(name: str):
    return FileResponse(_safe_artifact(GEOJSON_ROOT, name, ".geojson"), media_type="application/geo+json")
