"""Production ASGI entry point.

The development ``serve_api.py`` remains dependency-free. This module is the
container/process-manager entry point and expects FastAPI/Uvicorn to be installed.
"""

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from agent.environment_status import environment_status
from agent.capability_catalog import capability_catalog
from agent.service import AgentService
from agent.runtime_capabilities import runtime_capability_snapshot
from agent.workflow_templates import (
    WorkflowTemplateError,
    get_workflow_template,
    normalize_workflow_constraints,
    normalize_workflow_evidence,
    revise_workflow_plan,
    validate_workflow_plan,
    workflow_template_catalog,
)


app = FastAPI(title="Spatial Agent", version="0.1.0")
service = AgentService(
    state_db_path=os.environ.get("SPATIAL_AGENT_STATE_DB", "outputs/spatial-agent.db")
)
ROOT = Path(__file__).parent
WEB_ROOT = ROOT / "web"
ARTIFACT_ROOT = Path(os.environ.get("SPATIAL_AGENT_ARTIFACT_ROOT", "outputs/runs"))
GEOJSON_ROOT = Path(os.environ.get("SPATIAL_AGENT_GEOJSON_ROOT", "outputs/geojson"))


@app.exception_handler(HTTPException)
async def http_error_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


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
def capabilities() -> Dict[str, Any]:
    status = environment_status()
    environment = "local" if status["capabilities"]["local_gis_backend"] else "memory"
    return capability_catalog(environment=environment)


@app.get("/capabilities/runtime")
def runtime_capabilities(max_files: int = 10) -> Dict[str, Any]:
    if max_files < 1 or max_files > 10:
        raise HTTPException(status_code=400, detail="max_files must be between 1 and 10")
    return runtime_capability_snapshot(max_files=max_files)


@app.get("/")
def console():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/index.html")
def console_index():
    return FileResponse(WEB_ROOT / "index.html")


@app.post("/runs")
def run(payload: Dict[str, Any]):
    try:
        return service.run(
            request=payload.get("request", ""),
            session_id=payload.get("session_id", "default"),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "memory"),
            export_artifact=bool(payload.get("export_artifact", False)),
            export_geojson=bool(payload.get("export_geojson", False)),
            geojson_max_features=payload.get("geojson_max_features", 100),
            timeout_seconds=payload.get("timeout_seconds"),
            spatial_context=payload.get("spatial_context"),
            workflow=payload.get("workflow"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/runs/async")
def run_async(payload: Dict[str, Any]):
    try:
        return service.run_async(
            request=payload.get("request", ""),
            session_id=payload.get("session_id", "default"),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "memory"),
            export_artifact=bool(payload.get("export_artifact", False)),
            export_geojson=bool(payload.get("export_geojson", False)),
            geojson_max_features=payload.get("geojson_max_features", 100),
            timeout_seconds=payload.get("timeout_seconds"),
            spatial_context=payload.get("spatial_context"),
            workflow=payload.get("workflow"),
            idempotency_key=payload.get("idempotency_key"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/runs")
def list_runs(limit: int = 20):
    try:
        return service.list_runs(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sessions")
def list_sessions(limit: int = 50):
    try:
        return service.list_sessions(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sessions/{session_id}/runs")
def list_session_runs(session_id: str, limit: int = 20):
    try:
        return service.list_session_runs(session_id=session_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sessions")
def create_session():
    try:
        return service.create_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/clear")
def clear_session(session_id: str):
    try:
        return service.clear_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        return service.delete_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/metrics")
def metrics():
    return service.metrics()


@app.get("/workflows")
def workflows():
    return {"templates": workflow_template_catalog()}


@app.post("/workflows/{template_id}/validate")
def validate_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        template = get_workflow_template(template_id)
        constraints = normalize_workflow_constraints(template, payload.get("constraints", {}))
        evidence = normalize_workflow_evidence(template, payload.get("evidence"))
        plan = payload.get("plan")
        result = {"valid": True, "template": template, "constraints": constraints, "evidence": evidence}
        if plan is not None:
            result["plan"] = validate_workflow_plan(template, plan)
        return result
    except (ValueError, WorkflowTemplateError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/workflows/{template_id}/revise")
def revise_workflow(template_id: str, payload: Dict[str, Any]):
    try:
        template = get_workflow_template(template_id)
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
    except (ValueError, WorkflowTemplateError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs/{run_id}")
def get_run(run_id: str, planner: str = "rule", backend: str = "memory"):
    try:
        return service.get_run(run_id=run_id, planner=planner, backend=backend)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/runs/{run_id}/observability")
@app.get("/runs/{run_id}/async")
def async_observability(run_id: str):
    try:
        return service.get_async_observability(run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/comparisons")
def compare(payload: Dict[str, Any]):
    try:
        return service.compare_buildability(
            admin_name=payload.get("admin_name", ""),
            thresholds=payload.get("thresholds", []),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
            spatial_context=payload.get("spatial_context"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/region-comparisons")
def compare_regions(payload: Dict[str, Any]):
    try:
        return service.compare_buildability_regions(
            admin_names=payload.get("admin_names", []),
            threshold=payload.get("threshold", 20),
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "local"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/runs/{run_id}/retry")
def retry(run_id: str, payload: Dict[str, Any]):
    try:
        return service.retry(
            run_id=run_id,
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "memory"),
            export_artifact=bool(payload.get("export_artifact", False)),
            export_geojson=bool(payload.get("export_geojson", False)),
            geojson_max_features=payload.get("geojson_max_features", 100),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/runs/{run_id}/cancel")
def cancel(run_id: str, payload: Dict[str, Any]):
    try:
        return service.cancel(
            run_id=run_id,
            planner=payload.get("planner", "rule"),
            backend=payload.get("backend", "memory"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _safe_artifact(root: Path, name: str, suffix: str) -> Path:
    candidate = (root / Path(name).name).resolve()
    if root.resolve() not in candidate.parents or candidate.suffix != suffix:
        raise HTTPException(status_code=404, detail="artifact not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return candidate


@app.get("/artifacts/runs/{name}")
def run_artifact(name: str):
    return FileResponse(_safe_artifact(ARTIFACT_ROOT, name, ".json"), media_type="application/json")


@app.get("/artifacts/geojson/{name}")
def geojson_artifact(name: str):
    return FileResponse(_safe_artifact(GEOJSON_ROOT, name, ".geojson"), media_type="application/geo+json")
