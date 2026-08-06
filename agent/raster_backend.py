import math
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

    def get_raster_statistics(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        entry = self._catalog.require(dataset)
        if entry.kind != "raster":
            raise ToolError("dataset is not raster: " + dataset)
        return raster_statistics_for_entry(entry, max_files=max_files)

    def get_zonal_raster_statistics(
        self,
        dataset: str,
        geometry: Dict[str, Any],
        geometry_crs: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        entry = self._catalog.require(dataset)
        if entry.kind != "raster":
            raise ToolError("dataset is not raster: " + dataset)
        return zonal_statistics_for_entry(
            entry, geometry, geometry_crs, admin_name, max_files=max_files
        )

    def get_zonal_slope_statistics(
        self,
        admin_geometry: Dict[str, Any],
        geometry_crs: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        entry = self._catalog.require("dem")
        return zonal_slope_statistics_for_entry(
            entry, admin_geometry, geometry_crs, admin_name, max_files=max_files
        )

    def get_zonal_land_use_distribution(
        self,
        admin_geometry: Dict[str, Any],
        geometry_crs: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        entry = self._catalog.require("land_use")
        return zonal_land_use_distribution_for_entry(
            entry, admin_geometry, geometry_crs, admin_name, max_files=max_files
        )


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


def raster_statistics_for_entry(entry: DatasetEntry, max_files: int = 3) -> Dict[str, Any]:
    """Compute bounded streaming statistics without loading a complete raster."""
    if max_files < 1:
        raise ToolError("max_files must be at least 1")
    if not entry.files:
        return {
            "dataset": entry.name,
            "kind": entry.kind,
            "file_count": 0,
            "statistics": {"error": "no files matched dataset entry"},
            "metrics": {"backend": "rasterio", "analyzed_files": 0},
        }
    try:
        import numpy
        import rasterio
    except ImportError as exc:
        raise ToolError("rasterio and numpy are required for RasterMetadataBackend") from exc

    total_pixels = 0
    valid_pixels = 0
    value_sum = 0.0
    value_sum_squares = 0.0
    minimum = None
    maximum = None
    file_summaries = []
    distribution_samples = []
    sampled_values_seen = 0
    combined_bounds = None
    crs_values = set()
    for path in entry.files[:max_files]:
        file_total = 0
        file_valid = 0
        file_sum = 0.0
        file_minimum = None
        file_maximum = None
        with rasterio.open(path) as src:
            combined_bounds = _merge_bounds(
                combined_bounds,
                _as_float_list([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]),
            )
            if src.crs:
                crs_values.add(str(src.crs))
            for _, window in src.block_windows(1):
                values = src.read(1, window=window, masked=True).compressed()
                file_total += int(window.width * window.height)
                if not len(values):
                    continue
                values = values[numpy.isfinite(values)]
                if not len(values):
                    continue
                values = values.astype("float64", copy=False)
                sampled_values_seen = _append_distribution_sample(
                    distribution_samples, values, sampled_values_seen
                )
                count = int(values.size)
                chunk_minimum = float(values.min())
                chunk_maximum = float(values.max())
                chunk_sum = float(values.sum(dtype=numpy.float64))
                chunk_sum_squares = float(numpy.square(values).sum(dtype=numpy.float64))
                file_valid += count
                file_sum += chunk_sum
                file_minimum = chunk_minimum if file_minimum is None else min(file_minimum, chunk_minimum)
                file_maximum = chunk_maximum if file_maximum is None else max(file_maximum, chunk_maximum)
                valid_pixels += count
                value_sum += chunk_sum
                value_sum_squares += chunk_sum_squares
                minimum = chunk_minimum if minimum is None else min(minimum, chunk_minimum)
                maximum = chunk_maximum if maximum is None else max(maximum, chunk_maximum)
        total_pixels += file_total
        file_summaries.append(
            {
                "path": path,
                "valid_pixel_count": file_valid,
                "nodata_pixel_count": file_total - file_valid,
                "minimum": file_minimum,
                "maximum": file_maximum,
                "mean": round(file_sum / file_valid, 3) if file_valid else None,
            }
        )

    mean = value_sum / valid_pixels if valid_pixels else None
    variance = max(0.0, value_sum_squares / valid_pixels - mean * mean) if mean is not None else None
    distribution = _distribution_summary(distribution_samples, minimum, maximum)
    return {
        "dataset": entry.name,
        "kind": entry.kind,
        "role": entry.role,
        "file_count": len(entry.files),
        "bounds": combined_bounds,
        "crs": sorted(crs_values)[0] if len(crs_values) == 1 else sorted(crs_values),
        "statistics": {
            "minimum": minimum,
            "maximum": maximum,
            "mean": round(mean, 3) if mean is not None else None,
            "standard_deviation": round(math.sqrt(variance), 3) if variance is not None else None,
            "valid_pixel_count": valid_pixels,
            "nodata_pixel_count": total_pixels - valid_pixels,
            "nodata_ratio": round((total_pixels - valid_pixels) / total_pixels, 6) if total_pixels else None,
            "distribution": distribution,
            "files": file_summaries,
        },
        "metrics": {"backend": "rasterio", "analyzed_files": len(file_summaries)},
    }


def zonal_statistics_for_entry(
    entry: DatasetEntry,
    geometry: Dict[str, Any],
    geometry_crs: str,
    admin_name: str,
    max_files: int = 10,
) -> Dict[str, Any]:
    """Compute raster statistics inside a vector geometry after CRS conversion."""
    if max_files < 1:
        raise ToolError("max_files must be at least 1")
    try:
        import numpy
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except ImportError as exc:
        raise ToolError("rasterio and numpy are required for zonal raster statistics") from exc

    total_pixels = 0
    valid_pixels = 0
    value_sum = 0.0
    value_sum_squares = 0.0
    minimum = None
    maximum = None
    matched_files = []
    distribution_samples = []
    sampled_values_seen = 0
    combined_bounds = None
    crs_values = set()
    for path in entry.files[:max_files]:
        try:
            with rasterio.open(path) as src:
                raster_bounds = _as_float_list(
                    [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
                )
                projected_geometry = transform_geom(
                    geometry_crs, src.crs, geometry, precision=6
                )
                values, _ = mask(src, [projected_geometry], crop=True, filled=False)
        except ValueError:
            continue
        masked_values = values[0]
        total_pixels += int(masked_values.size)
        values = masked_values.compressed()
        values = values[numpy.isfinite(values)].astype("float64", copy=False)
        if not len(values):
            continue
        combined_bounds = _merge_bounds(combined_bounds, raster_bounds)
        if src.crs:
            crs_values.add(str(src.crs))
        sampled_values_seen = _append_distribution_sample(
            distribution_samples, values, sampled_values_seen
        )
        matched_files.append(path)
        valid_pixels += int(values.size)
        value_sum += float(values.sum(dtype=numpy.float64))
        value_sum_squares += float(numpy.square(values).sum(dtype=numpy.float64))
        minimum = float(values.min()) if minimum is None else min(minimum, float(values.min()))
        maximum = float(values.max()) if maximum is None else max(maximum, float(values.max()))

    if not valid_pixels:
        statistics = {
            "error": "no raster pixels intersected the selected administrative area",
            "valid_pixel_count": 0,
            "nodata_pixel_count": 0,
            "nodata_ratio": None,
        }
    else:
        mean = value_sum / valid_pixels
        variance = max(0.0, value_sum_squares / valid_pixels - mean * mean)
        statistics = {
            "minimum": minimum,
            "maximum": maximum,
            "mean": round(mean, 3),
            "standard_deviation": round(math.sqrt(variance), 3),
            "valid_pixel_count": valid_pixels,
            "nodata_pixel_count": total_pixels - valid_pixels,
            "nodata_ratio": round((total_pixels - valid_pixels) / total_pixels, 6),
            "distribution": _distribution_summary(distribution_samples, minimum, maximum),
        }
    return {
        "dataset": entry.name,
        "admin_name": admin_name,
        "file_count": len(entry.files),
        "matched_files": matched_files,
        "bounds": combined_bounds,
        "crs": sorted(crs_values)[0] if len(crs_values) == 1 else sorted(crs_values),
        "statistics": statistics,
        "metrics": {
            "backend": "rasterio",
            "analyzed_files": len(entry.files[:max_files]),
            "matched_files": len(matched_files),
            "geometry_crs": geometry_crs,
        },
    }


def zonal_slope_statistics_for_entry(
    entry: DatasetEntry,
    geometry: Dict[str, Any],
    geometry_crs: str,
    admin_name: str,
    max_files: int = 10,
) -> Dict[str, Any]:
    """Derive slope in degrees from DEM pixels and summarize the masked area."""
    if max_files < 1:
        raise ToolError("max_files must be at least 1")
    try:
        import numpy
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except ImportError as exc:
        raise ToolError("rasterio and numpy are required for slope statistics") from exc

    values = []
    matched_files = []
    combined_bounds = None
    crs_values = set()
    total_pixels = 0
    for path in entry.files[:max_files]:
        try:
            with rasterio.open(path) as src:
                projected_geometry = transform_geom(geometry_crs, src.crs, geometry, precision=6)
                elevation, _ = mask(src, [projected_geometry], crop=True, filled=False)
                elevation = elevation[0]
                valid = ~elevation.mask if hasattr(elevation, "mask") else numpy.ones(elevation.shape, dtype=bool)
                finite = numpy.isfinite(elevation.data)
                valid &= finite
                total_pixels += int(valid.size)
                if not valid.any():
                    continue
                data = elevation.data.astype("float64", copy=False)
                fill_value = float(numpy.nanmedian(data[valid]))
                filled = numpy.where(valid, data, fill_value)
                dy, dx = numpy.gradient(filled, abs(float(src.transform.e)), abs(float(src.transform.a)))
                slope = numpy.degrees(numpy.arctan(numpy.sqrt(numpy.square(dx) + numpy.square(dy))))
                area_values = slope[valid]
                values.extend(float(value) for value in area_values if numpy.isfinite(value))
                matched_files.append(path)
                combined_bounds = _merge_bounds(combined_bounds, _as_float_list([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]))
                if src.crs:
                    crs_values.add(str(src.crs))
        except ValueError:
            continue

    statistics = _numeric_summary(values, total_pixels)
    if not values:
        statistics = {"error": "no raster pixels intersected the selected administrative area", "valid_pixel_count": 0, "nodata_pixel_count": 0, "nodata_ratio": None}
    return {
        "dataset": "slope_from_dem",
        "admin_name": admin_name,
        "file_count": len(entry.files),
        "matched_files": matched_files,
        "bounds": combined_bounds,
        "crs": sorted(crs_values)[0] if len(crs_values) == 1 else sorted(crs_values),
        "statistics": statistics,
        "metrics": {"backend": "rasterio", "analyzed_files": len(entry.files[:max_files]), "matched_files": len(matched_files), "source_dataset": "dem", "geometry_crs": geometry_crs, "derived": True},
    }


def zonal_land_use_distribution_for_entry(
    entry: DatasetEntry,
    geometry: Dict[str, Any],
    geometry_crs: str,
    admin_name: str,
    max_files: int = 10,
) -> Dict[str, Any]:
    """Return bounded categorical counts and shares for land-use raster values."""
    if max_files < 1:
        raise ToolError("max_files must be at least 1")
    try:
        import numpy
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except ImportError as exc:
        raise ToolError("rasterio and numpy are required for land-use distribution") from exc

    counts = {}
    total_pixels = 0
    matched_files = []
    combined_bounds = None
    crs_values = set()
    for path in entry.files[:max_files]:
        try:
            with rasterio.open(path) as src:
                projected_geometry = transform_geom(geometry_crs, src.crs, geometry, precision=6)
                masked, _ = mask(src, [projected_geometry], crop=True, filled=False)
                band = masked[0]
                values = band.compressed().astype("float64", copy=False)
                values = values[numpy.isfinite(values)]
                if not len(values):
                    continue
                total_pixels += int(values.size)
                for value, count in zip(*numpy.unique(values, return_counts=True)):
                    key = str(int(value)) if float(value).is_integer() else str(round(float(value), 3))
                    counts[key] = counts.get(key, 0) + int(count)
                matched_files.append(path)
                combined_bounds = _merge_bounds(combined_bounds, _as_float_list([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]))
                if src.crs:
                    crs_values.add(str(src.crs))
        except ValueError:
            continue
    categories = sorted(
        [{"value": value, "pixel_count": count, "share": round(count / total_pixels, 6)} for value, count in counts.items()],
        key=lambda item: (-item["pixel_count"], item["value"]),
    )
    statistics = {"category_count": len(categories), "valid_pixel_count": total_pixels, "categories": categories[:50]}
    if not total_pixels:
        statistics = {"error": "no raster pixels intersected the selected administrative area", "category_count": 0, "valid_pixel_count": 0, "categories": []}
    return {
        "dataset": "land_use",
        "admin_name": admin_name,
        "file_count": len(entry.files),
        "matched_files": matched_files,
        "bounds": combined_bounds,
        "crs": sorted(crs_values)[0] if len(crs_values) == 1 else sorted(crs_values),
        "statistics": statistics,
        "metrics": {"backend": "rasterio", "analyzed_files": len(entry.files[:max_files]), "matched_files": len(matched_files), "geometry_crs": geometry_crs, "categorical": True},
    }


def _numeric_summary(values, total_pixels: int) -> Dict[str, Any]:
    if not values:
        return {"valid_pixel_count": 0, "nodata_pixel_count": total_pixels, "nodata_ratio": 1.0 if total_pixels else None}
    import numpy
    array = numpy.asarray(values, dtype="float64")
    mean = float(array.mean())
    return {
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "mean": round(mean, 3),
        "standard_deviation": round(float(array.std()), 3),
        "valid_pixel_count": int(array.size),
        "nodata_pixel_count": max(0, total_pixels - int(array.size)),
        "nodata_ratio": round(max(0, total_pixels - int(array.size)) / total_pixels, 6) if total_pixels else 0.0,
        "distribution": _distribution_summary([float(value) for value in array[:10000]], float(array.min()), float(array.max())),
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


def _append_distribution_sample(sample: List[float], values, seen: int, limit: int = 10000) -> int:
    """Keep a bounded deterministic sample for an approximate value distribution."""
    import numpy

    values = numpy.asarray(values).reshape(-1)
    if not len(values):
        return seen
    remaining = max(0, limit - len(sample))
    if remaining:
        sample.extend(float(value) for value in values[:remaining])
    return seen + int(values.size)


def _distribution_summary(sample: List[float], minimum, maximum, bins: int = 10) -> Dict[str, Any]:
    if not sample or minimum is None or maximum is None:
        return {"sampled": True, "sample_count": 0, "bins": []}
    if minimum == maximum:
        return {
            "sampled": True,
            "sample_count": len(sample),
            "bins": [{"lower": float(minimum), "upper": float(maximum), "count": len(sample)}],
        }
    width = (float(maximum) - float(minimum)) / bins
    counts = [0] * bins
    for value in sample:
        index = int((float(value) - float(minimum)) / width)
        counts[min(bins - 1, max(0, index))] += 1
    return {
        "sampled": True,
        "sample_count": len(sample),
        "bins": [
            {
                "lower": round(float(minimum) + index * width, 3),
                "upper": round(float(minimum) + (index + 1) * width, 3),
                "count": count,
            }
            for index, count in enumerate(counts)
        ],
    }
