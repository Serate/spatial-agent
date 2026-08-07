import os
from typing import Any, Dict, Tuple

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import export_run_summary
from agent.provenance import build_provenance
from agent.trace_formatter import format_trace
from run_demo import build_runtime
from agent.sqlite_store import SQLiteConversationStore, SQLiteStateStore
from result_contract import build_result_contract


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(self, artifact_store: ArtifactStore = None, state_db_path: str = None):
        self._runtimes = {}
        self._artifact_store = artifact_store or ArtifactStore()
        self._state_db_path = state_db_path or os.environ.get("SPATIAL_AGENT_STATE_DB")
        self._state_store = SQLiteStateStore(self._state_db_path) if self._state_db_path else None
        self._conversation_store = (
            SQLiteConversationStore(self._state_db_path) if self._state_db_path else None
        )

    def run(
        self,
        request: str,
        session_id: str = "default",
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
        timeout_seconds: float = None,
        spatial_context: Dict[str, Any] = None,
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if self._conversation_store is not None:
            self._conversation_store.ensure_session(session_id)
        normalized_context = _normalize_spatial_context(spatial_context)
        runtime = self._runtime(planner, backend)
        result = runtime.run(
            _contextualize_request(request, normalized_context),
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        payload = result.to_dict()
        payload["spatial_context"] = normalized_context
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"] = len(geometry_features)
            payload["result"] = build_result_contract(payload)
            payload.pop("_geometry_feature_count", None)
        return payload

    def retry(
        self,
        run_id: str,
        planner: str = "rule",
        backend: str = "memory",
        export_artifact: bool = False,
        export_geojson: bool = False,
        geojson_max_features: int = 100,
    ) -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        runtime = self._runtime(planner, backend)
        result = runtime.retry_failed(run_id)
        payload = result.to_dict()
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        if export_artifact:
            payload["artifact_ref"] = self._artifact_store.write_run(payload)
        if export_geojson:
            geometry_features = []
            for step in payload.get("steps", []):
                result_ref = (step.get("result") or {}).get("result_ref")
                if result_ref:
                    exported = runtime.export_result(result_ref, max_features=geojson_max_features)
                    geometry_features.extend(
                        _tag_geometry_features(
                            exported.get("features", []),
                            source=exported.get("geometry_source"),
                            crs=exported.get("crs"),
                            source_crs=exported.get("source_crs"),
                        )
                    )
            payload["geojson_ref"] = export_run_summary(
                payload,
                geometry_features=geometry_features or None,
            )
            payload["_geometry_feature_count"] = len(geometry_features)
            payload["result"] = build_result_contract(payload)
            payload.pop("_geometry_feature_count", None)
        return payload

    def cancel(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = self._runtime(planner, backend).cancel(run_id)
        return {
            "run_id": run_id,
            "status": "CANCEL_REQUESTED",
            "current_status": result.status.value,
        }

    def get_run(self, run_id: str, planner: str = "rule", backend: str = "memory") -> Dict:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        result = (
            self._state_store.get(run_id)
            if self._state_store is not None
            else self._runtime(planner, backend).get_run(run_id)
        )
        if result is None:
            raise ValueError("run not found: " + run_id)
        payload = result.to_dict()
        payload["result_type"] = _result_type(payload)
        payload["result"] = build_result_contract(payload)
        payload["trace_summary"] = format_trace(result)
        payload["provenance"] = build_provenance(payload)
        return payload

    def list_runs(self, limit: int = 20) -> Dict:
        if self._state_store is not None:
            return {"runs": self._state_store.list_runs(limit=limit)}
        return {"runs": self._artifact_store.list_runs(limit=limit)}

    def list_session_runs(self, session_id: str, limit: int = 20) -> Dict:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if self._state_store is None:
            return {"runs": []}
        return {"runs": self._state_store.list_runs(limit=limit, session_id=session_id)}

    def list_sessions(self, limit: int = 50) -> Dict:
        if self._conversation_store is None:
            return {"sessions": []}
        return {"sessions": self._conversation_store.list_sessions(limit=limit)}

    def create_session(self) -> Dict:
        if self._conversation_store is None:
            raise ValueError("session persistence is not configured")
        return self._conversation_store.create_session()

    def clear_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state_store.clear_session_runs(session_id) if self._state_store else 0
        if self._conversation_store:
            self._conversation_store.clear_session(session_id)
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "cleared_runs": cleared_runs}

    def delete_session(self, session_id: str) -> Dict:
        _validate_session_id(session_id)
        cleared_runs = self._state_store.clear_session_runs(session_id) if self._state_store else 0
        deleted = self._conversation_store.delete_session(session_id) if self._conversation_store else False
        for runtime in self._runtimes.values():
            runtime.clear_session(session_id)
        return {"session_id": session_id, "deleted": deleted, "cleared_runs": cleared_runs}

    def metrics(self) -> Dict:
        if self._state_store is not None:
            return self._state_store.metrics()
        return self._artifact_store.metrics()

    def compare_buildability(
        self,
        admin_name: str,
        thresholds,
        planner: str = "rule",
        backend: str = "local",
        spatial_context: Dict[str, Any] = None,
    ) -> Dict:
        if not isinstance(admin_name, str) or not admin_name.strip():
            raise ValueError("admin_name must be a non-empty string")
        normalized_context = _normalize_spatial_context(spatial_context)
        context_admin_name = normalized_context.get("admin_name")
        if context_admin_name:
            admin_name = context_admin_name
        if not isinstance(thresholds, list) or not thresholds or len(thresholds) > 6:
            raise ValueError("thresholds must contain 1 to 6 values")
        normalized = []
        for threshold in thresholds:
            value = float(threshold)
            if not 1 <= value <= 45:
                raise ValueError("slope thresholds must be between 1 and 45 degrees")
            if value not in normalized:
                normalized.append(value)
        rows = []
        for value in normalized:
            result = self.run(
                f"分析{admin_name}建设适宜性，坡度不超过{value:g}度",
                session_id=f"comparison-{admin_name}-{value:g}",
                planner=planner,
                backend=backend,
                spatial_context=normalized_context,
            )
            step = next((item for item in result.get("steps", []) if item.get("tool") == "get_zonal_buildability_analysis"), {})
            tool_result = step.get("result") or {}
            statistics = tool_result.get("statistics") or {}
            rows.append({
                "slope_limit_degrees": value,
                "status": result.get("status"),
                "candidate_pixel_count": statistics.get("candidate_pixel_count"),
                "valid_pixel_count": statistics.get("valid_pixel_count"),
                "candidate_ratio": statistics.get("candidate_ratio"),
                "error": statistics.get("error") or result.get("error"),
            })
        return {
            "admin_name": admin_name,
            "thresholds": normalized,
            "spatial_context": normalized_context,
            "results": rows,
        }

    def _runtime(self, planner: str, backend: str):
        key = _runtime_key(planner, backend)
        if key not in self._runtimes:
            self._runtimes[key] = build_runtime(
                planner,
                backend,
                state_store=self._state_store,
                conversation_store=self._conversation_store,
            )
        return self._runtimes[key]


def _runtime_key(planner: str, backend: str) -> Tuple[str, str]:
    if planner not in ("rule", "openai"):
        raise ValueError("planner must be one of: rule, openai")
    if backend not in ("memory", "local"):
        raise ValueError("backend must be one of: memory, local")
    return planner, backend


def _validate_session_id(session_id: str) -> None:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")


def _normalize_spatial_context(context: Dict[str, Any]) -> Dict[str, Any]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise ValueError("spatial_context must be an object")
    normalized = {}
    for key in ("admin_name", "source", "crs", "geometry_type"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()[:160]
    if context.get("geometry_available") is True:
        normalized["geometry_available"] = True
    return normalized


def _contextualize_request(request: str, context: Dict[str, Any]) -> str:
    admin_name = context.get("admin_name")
    if not admin_name:
        return request
    return f"{request}（当前地图选中区域：{admin_name}）"


def _tag_geometry_features(features, source=None, crs=None, source_crs=None):
    """Keep CRS/source beside each feature when result collections are merged."""
    tagged = []
    crs_name = _crs_name(crs)
    for feature in features or []:
        if not isinstance(feature, dict):
            continue
        properties = dict(feature.get("properties") or {})
        if source:
            properties["geometry_source"] = source
        if crs_name:
            properties["geometry_crs"] = crs_name
        if source_crs:
            properties["geometry_source_crs"] = source_crs
        tagged.append({**feature, "properties": properties})
    return tagged


def _result_type(payload: Dict) -> str:
    return str(((payload.get("plan") or {}).get("output") or {}).get("type") or "unknown")


def _crs_name(crs):
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        return (crs.get("properties") or {}).get("name")
    if isinstance(crs, list) and len(crs) == 1:
        return _crs_name(crs[0])
    return None
