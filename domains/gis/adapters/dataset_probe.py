from dataclasses import dataclass
from typing import Any, Dict, List

from .dataset_catalog import DatasetCatalog, DatasetEntry


@dataclass(frozen=True)
class ProbeResult:
    name: str
    kind: str
    format: str
    file_count: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "format": self.format,
            "file_count": self.file_count,
            "metadata": self.metadata,
        }


def probe_catalog(catalog: DatasetCatalog, max_files_per_dataset: int = 10) -> Dict[str, Any]:
    results = [
        probe_entry(entry, max_files=max_files_per_dataset).to_dict()
        for entry in catalog.list_entries()
    ]
    return {"root": catalog.root, "datasets": results}


def probe_entry(entry: DatasetEntry, max_files: int = 10) -> ProbeResult:
    if entry.kind == "vector":
        metadata = _probe_vector(entry, max_files=max_files)
    elif entry.kind == "raster":
        metadata = _probe_raster(entry, max_files=max_files)
    else:
        metadata = {"error": "unsupported dataset kind: " + entry.kind}
    return ProbeResult(
        name=entry.name,
        kind=entry.kind,
        format=entry.format,
        file_count=len(entry.files),
        metadata=metadata,
    )


def _probe_vector(entry: DatasetEntry, max_files: int) -> Dict[str, Any]:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("geopandas is required to probe vector datasets") from exc

    if not entry.files:
        return {"error": "no files matched dataset entry"}

    file_summaries = []
    total_features = 0
    fields = set()
    geometry_types = set()
    combined_bounds = None
    for path in entry.files[:max_files]:
        gdf = gpd.read_file(path)
        total_features += len(gdf)
        fields.update(str(column) for column in gdf.columns if column != "geometry")
        geometry_types.update(str(item) for item in gdf.geometry.geom_type.dropna().unique())
        bounds = _as_float_list(gdf.total_bounds)
        combined_bounds = _merge_bounds(combined_bounds, bounds)
        file_summaries.append(
            {
                "path": path,
                "feature_count": int(len(gdf)),
                "crs": str(gdf.crs) if gdf.crs else None,
                "bounds": bounds,
                "geometry_types": sorted(str(item) for item in gdf.geometry.geom_type.dropna().unique()),
                "fields": [str(column) for column in gdf.columns if column != "geometry"],
            }
        )

    return {
        "probed_files": len(file_summaries),
        "total_features": int(total_features),
        "fields": sorted(fields),
        "geometry_types": sorted(geometry_types),
        "bounds": combined_bounds,
        "files": file_summaries,
    }


def _probe_raster(entry: DatasetEntry, max_files: int) -> Dict[str, Any]:
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required to probe raster datasets") from exc

    if not entry.files:
        return {"error": "no files matched dataset entry"}

    file_summaries = []
    combined_bounds = None
    total_pixels = 0
    crs_values = set()
    for path in entry.files[:max_files]:
        with rasterio.open(path) as src:
            bounds = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
            bounds = _as_float_list(bounds)
            combined_bounds = _merge_bounds(combined_bounds, bounds)
            total_pixels += int(src.width * src.height)
            crs = str(src.crs) if src.crs else None
            if crs:
                crs_values.add(crs)
            file_summaries.append(
                {
                    "path": path,
                    "driver": src.driver,
                    "width": int(src.width),
                    "height": int(src.height),
                    "band_count": int(src.count),
                    "dtypes": list(src.dtypes),
                    "nodata": src.nodata,
                    "crs": crs,
                    "bounds": bounds,
                    "pixel_size": [float(src.transform.a), float(src.transform.e)],
                }
            )

    return {
        "probed_files": len(file_summaries),
        "total_pixels": total_pixels,
        "crs_values": sorted(crs_values),
        "bounds": combined_bounds,
        "files": file_summaries,
    }


def _as_float_list(values) -> List[float]:
    return [float(value) for value in values]


def _merge_bounds(current, next_bounds):
    if current is None:
        return list(next_bounds)
    return [
        min(current[0], next_bounds[0]),
        min(current[1], next_bounds[1]),
        max(current[2], next_bounds[2]),
        max(current[3], next_bounds[3]),
    ]
