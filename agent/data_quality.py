"""Bounded health checks for configured local spatial datasets."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .dataset_catalog import DatasetCatalog, DatasetEntry
from .capability_catalog import (
    DATASET_GROUPS,
    DATASET_TOOL_CAPABILITIES,
    capability_catalog,
)
from .errors import ToolError
from .raster_alignment import raster_alignment_report


HEALTH_DATASETS = ("admin_areas", "dem", "land_use", "roads", "water")
CORE_DATASETS = DATASET_GROUPS["core"]
OPTIONAL_DATASETS = DATASET_GROUPS["optional"]

# These are product capabilities, rather than raw file types. Keeping the
# mapping here lets health results explain which registered tools are safe to
# attempt after the preflight step.
DATASET_CAPABILITIES = DATASET_TOOL_CAPABILITIES


def dataset_health_report(
    catalog: DatasetCatalog,
    dataset: str = "all",
    max_files: int = 10,
) -> Dict[str, Any]:
    if dataset != "all" and dataset not in HEALTH_DATASETS:
        raise ToolError("unknown health dataset: " + dataset)
    if max_files < 1 or max_files > 10:
        raise ToolError("max_files must be between 1 and 10")

    names = HEALTH_DATASETS if dataset == "all" else (dataset,)
    reports = [
        _health_for_entry(catalog.get(name), name, max_files)
        for name in names
    ]
    for item in reports:
        item["layer"] = _dataset_layer(item["dataset"])
    statuses = [item["status"] for item in reports]
    core_status = _layer_status(reports, CORE_DATASETS)
    optional_status = _layer_status(reports, OPTIONAL_DATASETS)
    # For an all-dataset health check, status deliberately describes the core
    # product layer. Optional data remains visible through its own status.
    overall = core_status if dataset == "all" else _aggregate_status(statuses)
    relationships = {}
    dem_entry = catalog.get("dem")
    land_use_entry = catalog.get("land_use")
    if dem_entry is not None and land_use_entry is not None:
        relationships["dem_land_use"] = _raster_alignment_summary(
            dem_entry, land_use_entry, max_files
        )
        dem_report = next(
            (item for item in reports if item.get("dataset") == "dem"), {}
        )
        land_use_report = next(
            (item for item in reports if item.get("dataset") == "land_use"), {}
        )
        dem_metadata = (dem_report.get("metadata_samples") or [None])[0]
        land_use_metadata = (land_use_report.get("metadata_samples") or [None])[0]
        relationships["dem_land_use"]["grid_alignment"] = raster_alignment_report(
            dem_metadata or {}, land_use_metadata or {}
        )
    capabilities = {
        item["dataset"]: list(item.get("usable_for", [])) for item in reports
    }
    dataset_statuses = {item["dataset"]: item["status"] for item in reports}
    provenance = {
        item["dataset"]: dict(item.get("provenance") or {})
        for item in reports
    }
    alignment = relationships.get("dem_land_use") or {}
    if alignment.get("status") == "ready":
        for name in ("dem", "land_use"):
            if name in capabilities and reports[names.index(name)]["status"] != "unavailable":
                capabilities[name].append("get_zonal_buildability_analysis")
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "dataset": dataset,
        "status": overall,
        "core_status": core_status,
        "optional_status": optional_status,
        "status_by_layer": {
            "core": core_status,
            "optional": optional_status,
        },
        "core_datasets": list(CORE_DATASETS),
        "optional_datasets": list(OPTIONAL_DATASETS),
        "updated_at": updated_at,
        "datasets": reports,
        "provenance": provenance,
        "relationships": relationships,
        "capabilities": capabilities,
        "capability_catalog": capability_catalog(
            environment="local",
            dataset_capabilities=capabilities,
            dataset_statuses=dataset_statuses,
        ),
        "metrics": {
            "backend": "catalog_health",
            "checked_datasets": len(reports),
            "max_files_per_dataset": max_files,
        },
        "warning": "健康检查只验证数据可读取性和基础质量，不代表数据的法定权威性或规划合规性。",
    }


def _aggregate_status(statuses: Iterable[str]) -> str:
    values = list(statuses)
    if not values:
        return "not_checked"
    if any(status == "unavailable" for status in values):
        return "unavailable"
    if any(status == "degraded" for status in values):
        return "degraded"
    if all(status == "ready" for status in values):
        return "ready"
    return "unknown"


def _layer_status(reports: Iterable[Dict[str, Any]], layer: Iterable[str]) -> str:
    names = set(layer)
    return _aggregate_status(
        item["status"] for item in reports if item.get("dataset") in names
    )


def _dataset_layer(name: str) -> str:
    if name in CORE_DATASETS:
        return "core"
    if name in OPTIONAL_DATASETS:
        return "optional"
    return "unknown"


def _health_for_entry(
    entry: Optional[DatasetEntry],
    name: str,
    max_files: int,
) -> Dict[str, Any]:
    if entry is None or not entry.files:
        return _attach_provenance({
            "dataset": name,
            "status": "unavailable",
            "kind": entry.kind if entry else None,
            "file_count": len(entry.files) if entry else 0,
            "checks": [{"name": "files", "status": "failed", "message": "没有匹配到配置文件"}],
            "usable_for": [],
            "metrics": {"checked_files": 0},
        }, entry)
    if entry.kind == "raster":
        return _attach_provenance(_health_raster(entry, max_files), entry)
    if entry.kind == "vector":
        return _attach_provenance(_health_vector(entry, max_files), entry)
    return _attach_provenance({
        "dataset": name,
        "status": "degraded",
        "kind": entry.kind,
        "file_count": len(entry.files),
        "checks": [{"name": "kind", "status": "failed", "message": "不支持的数据类型"}],
        "metrics": {"checked_files": 0},
    }, entry)


def _attach_provenance(
    report: Dict[str, Any], entry: Optional[DatasetEntry]
) -> Dict[str, Any]:
    """Expose only catalog provenance, never resolved paths or raw config."""
    report["provenance"] = dict(entry.provenance) if entry is not None else {}
    return report


def _health_raster(entry: DatasetEntry, max_files: int) -> Dict[str, Any]:
    checks = [{"name": "files", "status": "passed", "message": "已匹配配置文件"}]
    try:
        import rasterio
    except ImportError:
        return _unavailable_dependency(entry, "rasterio")

    crs_values = set()
    bounds = None
    errors = []
    dimensions = []
    metadata_samples = []
    checked = 0
    for path in entry.files[:max_files]:
        try:
            with rasterio.open(path) as src:
                checked += 1
                dimensions.append([int(src.width), int(src.height)])
                if src.crs:
                    crs_values.add(str(src.crs))
                current = [float(src.bounds.left), float(src.bounds.bottom), float(src.bounds.right), float(src.bounds.top)]
                bounds = _merge_bounds(bounds, current)
                metadata_samples.append(
                    {
                        "crs": str(src.crs) if src.crs else None,
                        "bounds": current,
                        "width": int(src.width),
                        "height": int(src.height),
                        "pixel_size": [abs(float(src.transform.a)), abs(float(src.transform.e))],
                        "transform": [
                            float(src.transform.a), float(src.transform.b), float(src.transform.c),
                            float(src.transform.d), float(src.transform.e), float(src.transform.f),
                        ],
                    }
                )
        except Exception as exc:  # a health report must describe bad files, not hide them
            errors.append({"path": str(path), "message": str(exc)[:240]})
    if errors:
        checks.append({"name": "readability", "status": "failed", "message": f"{len(errors)} 个文件读取失败"})
    else:
        checks.append({"name": "readability", "status": "passed", "message": f"{checked} 个文件可读取"})
    if len(crs_values) > 1:
        checks.append({"name": "crs_consistency", "status": "warning", "message": "文件包含多个 CRS"})
    else:
        checks.append({"name": "crs_consistency", "status": "passed", "message": "CRS 一致或未声明"})
    status = "degraded" if errors or len(crs_values) > 1 else "ready"
    return {
        "dataset": entry.name,
        "status": status,
        "kind": entry.kind,
        "format": entry.format,
        "role": entry.role,
        "file_count": len(entry.files),
        "crs_values": sorted(crs_values),
        "bounds": bounds,
        "dimensions": dimensions[:max_files],
        "metadata_samples": metadata_samples[:max_files],
        "errors": errors,
        "usable_for": list(DATASET_CAPABILITIES.get(entry.name, [])),
        "checks": checks,
        "metrics": {"checked_files": checked, "sampled": checked < len(entry.files)},
    }


def _health_vector(entry: DatasetEntry, max_files: int) -> Dict[str, Any]:
    checks = [{"name": "files", "status": "passed", "message": "已匹配配置文件"}]
    try:
        import geopandas as gpd
    except ImportError:
        return _unavailable_dependency(entry, "geopandas")
    errors = []
    crs_values = set()
    bounds = None
    feature_count = 0
    empty_count = 0
    invalid_count = 0
    checked = 0
    for path in entry.files[:max_files]:
        try:
            kwargs = {"layer": entry.name} if entry.format == "gpkg" else {}
            frame = gpd.read_file(path, **kwargs)
            checked += 1
            feature_count += len(frame)
            empty_count += int(frame.geometry.is_empty.sum())
            invalid_count += int((~frame.geometry.is_valid).sum())
            if frame.crs:
                crs_values.add(str(frame.crs))
            if len(frame):
                current = [float(value) for value in frame.total_bounds]
                bounds = _merge_bounds(bounds, current)
        except Exception as exc:
            errors.append({"path": str(path), "message": str(exc)[:240]})
    if errors:
        checks.append({"name": "readability", "status": "failed", "message": f"{len(errors)} 个图层读取失败"})
    else:
        checks.append({"name": "readability", "status": "passed", "message": f"{checked} 个图层可读取"})
    geometry_status = "passed" if not empty_count and not invalid_count else "warning"
    checks.append({"name": "geometry_validity", "status": geometry_status, "message": f"空几何 {empty_count} 个，无效几何 {invalid_count} 个"})
    status = "degraded" if errors or empty_count or invalid_count or len(crs_values) > 1 else "ready"
    return {
        "dataset": entry.name,
        "status": status,
        "kind": entry.kind,
        "format": entry.format,
        "role": entry.role,
        "file_count": len(entry.files),
        "crs_values": sorted(crs_values),
        "bounds": bounds,
        "feature_count": feature_count,
        "empty_geometry_count": empty_count,
        "invalid_geometry_count": invalid_count,
        "errors": errors,
        "usable_for": list(DATASET_CAPABILITIES.get(entry.name, [])),
        "checks": checks,
        "metrics": {"checked_files": checked, "sampled": checked < len(entry.files)},
    }


def _unavailable_dependency(entry: DatasetEntry, dependency: str) -> Dict[str, Any]:
    return {
        "dataset": entry.name,
        "status": "unavailable",
        "kind": entry.kind,
        "format": entry.format,
        "file_count": len(entry.files),
        "checks": [{"name": "dependency", "status": "failed", "message": f"缺少 {dependency}"}],
        "errors": [f"{dependency} is required"],
        "usable_for": [],
        "metrics": {"checked_files": 0},
    }


def _raster_alignment_summary(
    dem_entry: DatasetEntry,
    land_use_entry: DatasetEntry,
    max_files: int,
) -> Dict[str, Any]:
    """Check file-level coverage compatibility without reading pixel arrays."""
    try:
        import rasterio
        from rasterio.warp import transform_bounds
    except ImportError:
        return {
            "status": "unavailable",
            "overlapping_pairs": 0,
            "checked_dem_files": 0,
            "checked_land_use_files": 0,
            "errors": ["rasterio is required"],
        }
    pairs = []
    errors = []
    checked_dem_paths = set()
    checked_land = 0
    for land_path in land_use_entry.files[:max_files]:
        try:
            with rasterio.open(land_path) as land_src:
                checked_land += 1
                land_bounds = [
                    float(land_src.bounds.left),
                    float(land_src.bounds.bottom),
                    float(land_src.bounds.right),
                    float(land_src.bounds.top),
                ]
                for dem_path in dem_entry.files[:max_files]:
                    try:
                        with rasterio.open(dem_path) as dem_src:
                            checked_dem_paths.add(str(dem_path))
                            dem_bounds = transform_bounds(
                                land_src.crs,
                                dem_src.crs,
                                *land_bounds,
                            )
                            overlap = not (
                                dem_src.bounds.right <= dem_bounds[0]
                                or dem_src.bounds.left >= dem_bounds[2]
                                or dem_src.bounds.top <= dem_bounds[1]
                                or dem_src.bounds.bottom >= dem_bounds[3]
                            )
                            if overlap:
                                pairs.append(
                                    {
                                        "dem_file": Path(dem_path).name,
                                        "land_use_file": Path(land_path).name,
                                        "dem_crs": str(dem_src.crs) if dem_src.crs else None,
                                        "land_use_crs": str(land_src.crs) if land_src.crs else None,
                                    }
                                )
                    except Exception as exc:
                        errors.append(str(exc)[:240])
        except Exception as exc:
            errors.append(str(exc)[:240])
    status = "ready" if pairs and not errors else "degraded" if pairs else "unavailable"
    return {
        "status": status,
        "overlapping_pairs": len(pairs),
        "sample_pairs": pairs[:20],
        "checked_dem_files": len(checked_dem_paths),
        "checked_land_use_files": checked_land,
        "errors": errors[:20],
        "message": "发现可用于跨栅格分析的文件覆盖关系" if pairs else "没有发现 DEM 与土地利用文件覆盖关系",
    }


def _merge_bounds(current: Optional[List[float]], next_bounds: Iterable[float]) -> List[float]:
    values = [float(value) for value in next_bounds]
    if current is None:
        return values
    return [
        min(current[0], values[0]),
        min(current[1], values[1]),
        max(current[2], values[2]),
        max(current[3], values[3]),
    ]
