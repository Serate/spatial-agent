from typing import Any, Dict, List

from .dataset_catalog import DatasetCatalog, DatasetEntry
from .errors import ToolError


class RasterMetadataBackend:
    """Reads lightweight raster metadata from configured local datasets."""

    def __init__(self, catalog: DatasetCatalog):
        self._catalog = catalog

    def get_raster_metadata(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        entry = self._catalog.require(dataset)
        if entry.kind != "raster":
            raise ToolError("dataset is not raster: " + dataset)
        return raster_metadata_for_entry(entry, max_files=max_files)


def raster_metadata_for_entry(entry: DatasetEntry, max_files: int = 3) -> Dict[str, Any]:
    if max_files < 1:
        raise ToolError("max_files must be at least 1")
    if not entry.files:
        return {
            "dataset": entry.name,
            "kind": entry.kind,
            "format": entry.format,
            "role": entry.role,
            "file_count": 0,
            "sample_files": [],
            "metadata": {"error": "no files matched dataset entry"},
            "metrics": {"backend": "rasterio", "probed_files": 0},
        }

    try:
        import rasterio
    except ImportError as exc:
        raise ToolError("rasterio is required for RasterMetadataBackend") from exc

    file_summaries = []
    crs_values = set()
    dtype_values = set()
    combined_bounds = None
    for path in entry.files[:max_files]:
        with rasterio.open(path) as src:
            bounds = _as_float_list([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top])
            combined_bounds = _merge_bounds(combined_bounds, bounds)
            crs = str(src.crs) if src.crs else None
            if crs:
                crs_values.add(crs)
            dtype_values.update(str(dtype) for dtype in src.dtypes)
            file_summaries.append(
                {
                    "path": path,
                    "driver": src.driver,
                    "width": int(src.width),
                    "height": int(src.height),
                    "band_count": int(src.count),
                    "dtypes": [str(dtype) for dtype in src.dtypes],
                    "crs": crs,
                    "bounds": bounds,
                    "pixel_size": [float(src.transform.a), abs(float(src.transform.e))],
                }
            )

    first = file_summaries[0]
    return {
        "dataset": entry.name,
        "kind": entry.kind,
        "format": entry.format,
        "role": entry.role,
        "file_count": len(entry.files),
        "sample_files": [item["path"] for item in file_summaries],
        "metadata": {
            "width": first["width"],
            "height": first["height"],
            "band_count": first["band_count"],
            "dtypes": sorted(dtype_values),
            "crs_values": sorted(crs_values),
            "bounds": combined_bounds,
            "pixel_size": first["pixel_size"],
            "files": file_summaries,
        },
        "metrics": {"backend": "rasterio", "probed_files": len(file_summaries)},
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
