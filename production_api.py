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
from agent.service import AgentService


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
    ready = True
    if required_gis and (
        not status["capabilities"]["local_gis_backend"]
        or not status["data"]["gdal_data_available"]
        or not status["data"]["proj_data_available"]
    ):
        ready = False
    if not ready:
        response.status_code = 503
    status["status"] = "ready" if ready else "not_ready"
    return status


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", **environment_status()}


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


@app.get("/metrics")
def metrics():
    return service.metrics()


@app.get("/runs/{run_id}")
def get_run(run_id: str, planner: str = "rule", backend: str = "memory"):
    try:
        return service.get_run(run_id=run_id, planner=planner, backend=backend)
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
