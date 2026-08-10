"""Metadata-only evidence for comparing two raster grids.

The module deliberately accepts controlled metadata rather than raster paths.
It can therefore be used by data-quality checks, planners, and tests without
opening a raster or reading any pixel values.  A metadata object may either be
the direct mapping returned by a probe or the ``metadata`` member of a raster
tool result.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional, Tuple


ALIGNMENT_STATUSES = (
    "missing_metadata",
    "crs_mismatch",
    "no_overlap",
    "resolution_mismatch",
    "grid_mismatch",
    "aligned",
)

_REQUIRED_FIELDS = ("crs", "bounds", "width", "height", "pixel_size")
_DEFAULT_TOLERANCE = 1e-9


def raster_alignment_report(
    dem_metadata: Mapping[str, Any],
    land_use_metadata: Mapping[str, Any],
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Return a bounded comparison report for DEM and land-use metadata.

    ``aligned`` is intentionally strict: both inputs must describe the same
    CRS, extent, dimensions, resolution, and pixel grid.  This is the useful
    precondition for a direct pixel-wise operation.  The report still exposes
    overlap and grid-phase evidence when the strict condition is not met.

    The function only reads the allowlisted metadata fields.  In particular,
    it never accesses a ``pixels`` or raster path field.
    """
    _validate_tolerance(tolerance)
    dem = _normalise_metadata(dem_metadata, tolerance=tolerance)
    land_use = _normalise_metadata(land_use_metadata, tolerance=tolerance)

    report: Dict[str, Any] = {
        "status": "missing_metadata",
        "aligned": False,
        "comparable": False,
        "dem": _public_metadata(dem),
        "land_use": _public_metadata(land_use),
        "missing_fields": {
            "dem": list(dem["missing_fields"]),
            "land_use": list(land_use["missing_fields"]),
        },
        "validation_errors": {
            "dem": list(dem["validation_errors"]),
            "land_use": list(land_use["validation_errors"]),
        },
        "comparison": {
            "crs": _comparison_pair(dem["crs"], land_use["crs"]),
            "bounds": _empty_bounds_comparison(),
            "resolution": _empty_resolution_comparison(dem, land_use),
            "grid": _empty_grid_comparison(dem, land_use),
        },
        "evidence": {
            "metadata_only": True,
            "pixels_read": False,
            "compared_fields": ["crs", "bounds", "width", "height", "pixel_size", "transform"],
        },
        "metadata_only": True,
        "pixels_read": False,
    }

    if dem["missing_fields"] or land_use["missing_fields"] or dem["validation_errors"] or land_use["validation_errors"]:
        report["reason"] = "required raster metadata is missing or invalid"
        return report

    if not _same_crs(dem["crs"], land_use["crs"]):
        report["status"] = "crs_mismatch"
        report["reason"] = "DEM and land-use CRS values differ"
        return report

    bounds_comparison = _compare_bounds(dem["bounds"], land_use["bounds"], tolerance)
    report["comparison"]["bounds"] = bounds_comparison
    if not bounds_comparison["overlap"]:
        report["status"] = "no_overlap"
        report["reason"] = "DEM and land-use bounds do not have a positive-area intersection"
        return report

    resolution_comparison = _compare_resolution(dem, land_use, tolerance)
    report["comparison"]["resolution"] = resolution_comparison
    if not resolution_comparison["match"]:
        report["status"] = "resolution_mismatch"
        report["reason"] = "DEM and land-use pixel sizes differ"
        return report

    grid_comparison = _compare_grid(dem, land_use, bounds_comparison, tolerance)
    report["comparison"]["grid"] = grid_comparison
    if not grid_comparison["match"]:
        report["status"] = "grid_mismatch"
        report["reason"] = "DEM and land-use metadata describe different pixel grids"
        return report

    report["status"] = "aligned"
    report["aligned"] = True
    report["comparable"] = True
    report["reason"] = "DEM and land-use metadata describe the same raster grid"
    return report


def compare_raster_alignment(
    dem_metadata: Mapping[str, Any],
    land_use_metadata: Mapping[str, Any],
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Compatibility name for callers that prefer a verb-led API."""
    return raster_alignment_report(
        dem_metadata,
        land_use_metadata,
        tolerance=tolerance,
    )


def _validate_tolerance(tolerance: float) -> None:
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance must be a non-negative finite number")
    if not math.isfinite(float(tolerance)) or float(tolerance) < 0:
        raise ValueError("tolerance must be a non-negative finite number")


def _normalise_metadata(value: Any, *, tolerance: float) -> Dict[str, Any]:
    source = value
    if isinstance(value, Mapping) and isinstance(value.get("metadata"), Mapping):
        source = value["metadata"]
    if not isinstance(source, Mapping):
        return {
            "crs": None,
            "bounds": None,
            "width": None,
            "height": None,
            "pixel_size": None,
            "transform": None,
            "origin": None,
            "rotated": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "validation_errors": ["metadata must be a mapping"],
        }

    missing = []
    errors = []
    crs, crs_error = _read_crs(source)
    if crs is None:
        missing.append("crs")
    if crs_error:
        errors.append(crs_error)

    bounds = _read_bounds(source.get("bounds"))
    if bounds is None:
        missing.append("bounds")

    width = _read_dimension(source.get("width"), "width", errors)
    if width is None:
        missing.append("width")
    height = _read_dimension(source.get("height"), "height", errors)
    if height is None:
        missing.append("height")

    transform, transform_error = _read_transform(source.get("transform"))
    if transform_error:
        errors.append(transform_error)

    pixel_value = source.get("pixel_size")
    pixel_size = _read_pixel_size(pixel_value)
    if pixel_value is not None and pixel_size is None:
        errors.append("pixel_size must contain two positive finite values")
    if pixel_value is None and pixel_size is None and transform is not None:
        pixel_size = [abs(transform[0]), abs(transform[4])]
    if pixel_size is None:
        missing.append("pixel_size")
    elif transform is not None and not _pair_close(
        pixel_size,
        [abs(transform[0]), abs(transform[4])],
        tolerance,
    ):
        errors.append("pixel_size does not agree with transform scale")

    if bounds is not None and width is not None and pixel_size is not None and not math.isclose(
        (bounds[2] - bounds[0]) / pixel_size[0], width, rel_tol=tolerance, abs_tol=tolerance
    ):
        errors.append("bounds width does not agree with width and pixel_size")
    if bounds is not None and height is not None and pixel_size is not None and not math.isclose(
        (bounds[3] - bounds[1]) / pixel_size[1], height, rel_tol=tolerance, abs_tol=tolerance
    ):
        errors.append("bounds height does not agree with height and pixel_size")
    if (
        transform is not None
        and bounds is not None
        and width is not None
        and height is not None
        and transform[1] == 0.0
        and transform[3] == 0.0
    ):
        transformed_bounds = [
            min(transform[2], transform[2] + transform[0] * width),
            min(transform[5], transform[5] + transform[4] * height),
            max(transform[2], transform[2] + transform[0] * width),
            max(transform[5], transform[5] + transform[4] * height),
        ]
        if not all(
            math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
            for a, b in zip(bounds, transformed_bounds)
        ):
            errors.append("bounds do not agree with transform and dimensions")

    origin = None
    if transform is not None:
        origin = [transform[2], transform[5]]
    elif bounds is not None:
        origin = [bounds[0], bounds[3]]

    return {
        "crs": crs,
        "bounds": bounds,
        "width": width,
        "height": height,
        "pixel_size": pixel_size,
        "transform": transform,
        "origin": origin,
        "rotated": bool(transform and (transform[1] != 0.0 or transform[3] != 0.0)),
        "missing_fields": missing,
        "validation_errors": errors,
    }


def _read_crs(source: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    value = source.get("crs")
    if value is None:
        values = source.get("crs_values")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            values = list(values)
            if len(values) == 1:
                value = values[0]
            elif values:
                return None, "crs_values must contain exactly one CRS"
    if isinstance(value, Mapping):
        properties = value.get("properties")
        value = properties.get("name") if isinstance(properties, Mapping) else None
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None, None
    text = "".join(str(value).split()).upper()
    return (text, None) if text else (None, None)


def _read_bounds(value: Any) -> Optional[list]:
    if isinstance(value, Mapping):
        values = [value.get(name) for name in ("left", "bottom", "right", "top")]
    elif all(hasattr(value, name) for name in ("left", "bottom", "right", "top")):
        values = [getattr(value, name) for name in ("left", "bottom", "right", "top")]
    elif isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    else:
        values = list(value)
    if len(values) != 4:
        return None
    try:
        values = [float(item) for item in values]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in values):
        return None
    if values[0] >= values[2] or values[1] >= values[3]:
        return None
    return values


def _read_dimension(value: Any, name: str, errors: list) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        if value is not None:
            errors.append(f"{name} must be a positive integer")
        return None
    if value <= 0:
        errors.append(f"{name} must be a positive integer")
        return None
    return value


def _read_pixel_size(value: Any) -> Optional[list]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    values = list(value)
    if len(values) != 2:
        return None
    try:
        values = [float(item) for item in values]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) and item > 0 for item in values):
        return None
    return values


def _read_transform(value: Any) -> Tuple[Optional[list], Optional[str]]:
    if value is None:
        return None, None
    if isinstance(value, Mapping):
        try:
            values = [float(value[name]) for name in ("a", "b", "c", "d", "e", "f")]
        except (KeyError, TypeError, ValueError):
            return None, "transform must contain finite a, b, c, d, e, and f values"
    elif hasattr(value, "a") and all(hasattr(value, name) for name in ("b", "c", "d", "e", "f")):
        try:
            values = [float(getattr(value, name)) for name in ("a", "b", "c", "d", "e", "f")]
        except (TypeError, ValueError):
            return None, "transform must contain finite a, b, c, d, e, and f values"
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) != 6:
            return None, "transform must contain six numeric values"
        try:
            values = [float(item) for item in value]
        except (TypeError, ValueError):
            return None, "transform must contain six numeric values"
    else:
        return None, "transform must contain six numeric values"
    if not all(math.isfinite(item) for item in values):
        return None, "transform must contain finite values"
    if values[0] == 0.0 or values[4] == 0.0:
        return None, "transform scale values must be non-zero"
    return values, None


def _public_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "crs": metadata["crs"],
        "bounds": metadata["bounds"],
        "width": metadata["width"],
        "height": metadata["height"],
        "pixel_size": metadata["pixel_size"],
        "transform": metadata["transform"],
        "origin": metadata["origin"],
    }


def _comparison_pair(dem_value: Any, land_use_value: Any) -> Dict[str, Any]:
    return {
        "match": dem_value is not None and dem_value == land_use_value,
        "dem": dem_value,
        "land_use": land_use_value,
    }


def _empty_bounds_comparison() -> Dict[str, Any]:
    return {
        "overlap": False,
        "intersection": None,
        "overlap_width": None,
        "overlap_height": None,
        "overlap_area": None,
        "match": False,
    }


def _empty_resolution_comparison(dem: Dict[str, Any], land_use: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "match": False,
        "dem": dem["pixel_size"],
        "land_use": land_use["pixel_size"],
    }


def _empty_grid_comparison(dem: Dict[str, Any], land_use: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "match": False,
        "origin_phase_match": False,
        "extent_match": False,
        "dimensions_match": False,
        "dem_origin": dem["origin"],
        "land_use_origin": land_use["origin"],
        "origin_delta_pixels": None,
        "rotated": bool(dem["rotated"] or land_use["rotated"]),
    }


def _compare_bounds(dem: list, land_use: list, tolerance: float) -> Dict[str, Any]:
    left = max(dem[0], land_use[0])
    bottom = max(dem[1], land_use[1])
    right = min(dem[2], land_use[2])
    top = min(dem[3], land_use[3])
    overlap_width = max(0.0, right - left)
    overlap_height = max(0.0, top - bottom)
    return {
        "overlap": overlap_width > tolerance and overlap_height > tolerance,
        "intersection": [left, bottom, right, top] if overlap_width > 0 and overlap_height > 0 else None,
        "overlap_width": overlap_width,
        "overlap_height": overlap_height,
        "overlap_area": overlap_width * overlap_height,
        "match": all(math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance) for a, b in zip(dem, land_use)),
    }


def _compare_resolution(dem: Dict[str, Any], land_use: Dict[str, Any], tolerance: float) -> Dict[str, Any]:
    first = dem["pixel_size"]
    second = land_use["pixel_size"]
    return {
        "match": _pair_close(first, second, tolerance),
        "dem": first,
        "land_use": second,
        "delta": [abs(first[0] - second[0]), abs(first[1] - second[1])],
    }


def _compare_grid(
    dem: Dict[str, Any],
    land_use: Dict[str, Any],
    bounds: Dict[str, Any],
    tolerance: float,
) -> Dict[str, Any]:
    dem_origin = dem["origin"]
    land_origin = land_use["origin"]
    resolution = dem["pixel_size"]
    delta = [dem_origin[0] - land_origin[0], dem_origin[1] - land_origin[1]]
    delta_pixels = [delta[0] / resolution[0], delta[1] / resolution[1]]
    phase_match = all(
        math.isclose(value, round(value), rel_tol=tolerance, abs_tol=tolerance)
        for value in delta_pixels
    )
    dimensions_match = dem["width"] == land_use["width"] and dem["height"] == land_use["height"]
    rotated = bool(dem["rotated"] or land_use["rotated"])
    match = phase_match and bounds["match"] and dimensions_match and not rotated
    return {
        "match": match,
        "origin_phase_match": phase_match,
        "extent_match": bounds["match"],
        "dimensions_match": dimensions_match,
        "dem_origin": dem_origin,
        "land_use_origin": land_origin,
        "origin_delta_pixels": delta_pixels,
        "rotated": rotated,
    }


def _same_crs(first: Optional[str], second: Optional[str]) -> bool:
    return first is not None and first == second


def _pair_close(first: Optional[list], second: Optional[list], tolerance: float) -> bool:
    return bool(
        first
        and second
        and len(first) == len(second)
        and all(math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance) for a, b in zip(first, second))
    )
