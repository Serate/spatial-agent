"""Small helpers for producing map-ready GeoJSON exports."""

from typing import Any, Dict


DISPLAY_CRS = "EPSG:4326"


def normalize_feature_collection(collection: Dict[str, Any], target_crs: str = DISPLAY_CRS) -> Dict[str, Any]:
    """Reproject feature geometries to one display CRS while retaining provenance."""
    source_crs = _crs_name(collection.get("crs"))
    features = []
    for feature in collection.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        properties = dict(feature.get("properties") or {})
        if geometry and source_crs and source_crs != target_crs:
            geometry = _transform_geometry(geometry, source_crs, target_crs)
        if source_crs:
            properties["geometry_source_crs"] = source_crs
        properties["geometry_crs"] = target_crs
        features.append({**feature, "geometry": geometry, "properties": properties})
    return {
        "type": "FeatureCollection",
        "features": features,
        "geometry_source": collection.get("geometry_source"),
        "source_crs": source_crs,
        "crs": {"type": "name", "properties": {"name": target_crs}},
    }


def _transform_geometry(geometry: Dict[str, Any], source_crs: str, target_crs: str) -> Dict[str, Any]:
    try:
        from rasterio.warp import transform_geom
    except ImportError as exc:
        raise RuntimeError("rasterio is required to normalize GeoJSON geometry CRS") from exc
    return transform_geom(source_crs, target_crs, geometry, precision=6)


def _crs_name(crs: Any):
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        return (crs.get("properties") or {}).get("name")
    return None
