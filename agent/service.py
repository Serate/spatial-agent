from typing import Dict, Tuple

from agent.artifact_store import ArtifactStore
from agent.geojson_exporter import export_run_summary
from agent.provenance import build_provenance
from agent.trace_formatter import format_trace
from run_demo import build_runtime


class AgentService:
    """Application boundary for running Agent sessions from a CLI or HTTP API."""

    def __init__(self, artifact_store: ArtifactStore = None):
        self._runtimes = {}
        self._artifact_store = artifact_store or ArtifactStore()

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
    ) -> Dict:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be a non-empty string")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        runtime = self._runtime(planner, backend)
        result = runtime.run(
            request,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        payload = result.to_dict()
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

    def list_runs(self, limit: int = 20) -> Dict:
        return {"runs": self._artifact_store.list_runs(limit=limit)}

    def metrics(self) -> Dict:
        return self._artifact_store.metrics()

    def compare_buildability(
        self,
        admin_name: str,
        thresholds,
        planner: str = "rule",
        backend: str = "local",
    ) -> Dict:
        if not isinstance(admin_name, str) or not admin_name.strip():
            raise ValueError("admin_name must be a non-empty string")
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
        return {"admin_name": admin_name, "thresholds": normalized, "results": rows}

    def _runtime(self, planner: str, backend: str):
        key = _runtime_key(planner, backend)
        if key not in self._runtimes:
            self._runtimes[key] = build_runtime(planner, backend)
        return self._runtimes[key]


def _runtime_key(planner: str, backend: str) -> Tuple[str, str]:
    if planner not in ("rule", "openai"):
        raise ValueError("planner must be one of: rule, openai")
    if backend not in ("memory", "local"):
        raise ValueError("backend must be one of: memory, local")
    return planner, backend


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


def _crs_name(crs):
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        return (crs.get("properties") or {}).get("name")
    if isinstance(crs, list) and len(crs) == 1:
        return _crs_name(crs[0])
    return None
