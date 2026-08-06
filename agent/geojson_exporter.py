import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_GEOJSON_ROOT = "outputs/geojson"
DEFAULT_MAX_BYTES = 100_000


def export_run_summary(
    payload: Dict[str, Any],
    root: str = DEFAULT_GEOJSON_ROOT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    geometry_features=None,
) -> str:
    """Write a bounded GeoJSON summary without raw tool args or source data."""
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("payload must include run_id")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    features = geometry_features or [_step_feature(step) for step in payload.get("steps", [])]
    if not features:
        features = [{
            "type": "Feature",
            "geometry": None,
            "properties": {"run_id": run_id, "status": payload.get("status")},
        }]
    properties = {"run_id": run_id, "status": payload.get("status")}
    selected = []
    truncated = False
    for feature in features:
        candidate = {
            "type": "FeatureCollection",
            "properties": properties,
            "features": selected + [feature],
        }
        encoded = json.dumps(candidate, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) <= max_bytes:
            selected.append(feature)
            continue
        truncated = True
        if not selected:
            selected.append(
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        **(feature.get("properties") or {}),
                        "geometry_truncated": True,
                    },
                }
            )
        break
    properties["geometry_truncated"] = truncated
    document = {
        "type": "FeatureCollection",
        "properties": properties,
        "features": selected,
    }
    encoded = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("GeoJSON summary exceeds max_bytes")
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (run_id + ".geojson")
    path.write_bytes(encoded)
    return path.as_posix()


def _step_feature(step: Any) -> Dict[str, Any]:
    if not isinstance(step, dict):
        return {"type": "Feature", "geometry": None, "properties": {"status": "UNKNOWN"}}
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    properties = {"id": step.get("id"), "tool": step.get("tool"), "status": step.get("status")}
    for key in ("count", "result_ref", "crs", "file_count"):
        if key in result:
            properties[key] = result[key]
    if step.get("latency_ms") is not None:
        properties["latency_ms"] = step["latency_ms"]
    if step.get("error"):
        properties["error"] = step["error"]
    return {"type": "Feature", "geometry": None, "properties": properties}
