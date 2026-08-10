"""Bounded health checks for configured local spatial datasets."""

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .dataset_catalog import DatasetCatalog, DatasetEntry
from .dataset_manifest import load_manifest, verify_dataset_manifest
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
    analysis_ready = _analysis_ready_health(
        catalog, dem_entry=dem_entry, land_use_entry=land_use_entry
    )
    analysis_ready_ok = (
        not catalog.analysis_ready_required
        or (
            isinstance(analysis_ready, dict)
            and analysis_ready.get("status") == "ready"
        )
    )
    alignment = relationships.get("dem_land_use") or {}
    grid_alignment = alignment.get("grid_alignment") or {}
    if (
        alignment.get("status") == "ready"
        and grid_alignment.get("status") == "aligned"
        and analysis_ready_ok
    ):
        for name in ("dem", "land_use"):
            if name in capabilities and reports[names.index(name)]["status"] != "unavailable":
                capabilities[name].append("get_zonal_buildability_analysis")
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = {
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
        **({"analysis_ready": analysis_ready} if analysis_ready is not None else {}),
        "capabilities": capabilities,
        "capability_catalog": capability_catalog(
            environment="local",
            dataset_capabilities=capabilities,
            dataset_statuses=dataset_statuses,
            analysis_ready=analysis_ready,
        ),
        "metrics": {
            "backend": "catalog_health",
            "checked_datasets": len(reports),
            "max_files_per_dataset": max_files,
        },
        "warning": "健康检查只验证数据可读取性和基础质量，不代表数据的法定权威性或规划合规性。",
    }
    if catalog.manifest_path:
        result["manifest"] = _manifest_health(catalog)
    manifest = result.get("manifest")
    manifest_ready = (
        not catalog.manifest_required
        or (isinstance(manifest, dict) and manifest.get("status") == "ready")
    )
    if catalog.manifest_required or catalog.analysis_ready_required:
        result["data_readiness"] = (
            "ready"
            if manifest_ready and analysis_ready_ok
            else "not_ready"
        )
    elif isinstance(manifest, dict) and manifest.get("status") != "ready":
        result["data_readiness"] = "degraded"
    else:
        result["data_readiness"] = "ready"
    return result


def _analysis_ready_health(
    catalog: DatasetCatalog,
    *,
    dem_entry: Optional[DatasetEntry],
    land_use_entry: Optional[DatasetEntry],
) -> Optional[Dict[str, Any]]:
    """Validate the bounded report for a reproducible common raster grid.

    The report is a release-time artifact. Health checks only read its JSON
    metadata and compare output basenames with the configured derived files;
    they never expose its local path or read raster pixels.
    """
    report_path = catalog.analysis_ready_report_path
    if not report_path:
        return None
    base = {
        "required": catalog.analysis_ready_required,
        "verification_mode": "metadata",
        "metadata_only": True,
        "pixels_read": False,
    }
    path = Path(report_path)
    if not path.is_file():
        return {
            **base,
            "status": "unavailable",
            "checks": [{"name": "report", "status": "failed", "message": "分析就绪报告不存在"}],
            "errors": ["analysis-ready report does not exist"],
        }
    try:
        payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            **base,
            "status": "degraded",
            "checks": [{"name": "report", "status": "failed", "message": "分析就绪报告不是有效 JSON"}],
            "errors": [str(exc)[:240]],
        }
    if not isinstance(payload, dict):
        return {
            **base,
            "status": "degraded",
            "checks": [{"name": "schema", "status": "failed", "message": "分析就绪报告结构无效"}],
            "errors": ["analysis-ready report must be an object"],
        }
    target = payload.get("target_grid")
    alignment = payload.get("grid_alignment")
    outputs = payload.get("outputs")
    errors: List[str] = []
    checks = []
    if not isinstance(target, dict):
        errors.append("缺少目标网格")
    else:
        required_grid = ("crs", "resolution", "bounds", "width", "height")
        missing = [name for name in required_grid if name not in target]
        if missing:
            errors.append("目标网格缺少字段：" + "、".join(missing))
        else:
            errors.extend(_validate_analysis_target(target))
    if not isinstance(alignment, dict) or alignment.get("status") != "aligned":
        errors.append("派生栅格网格未标记为 aligned")
    if not isinstance(outputs, dict) or not outputs.get("dem") or not outputs.get("land_use"):
        errors.append("缺少 DEM/土地利用派生输出记录")
    else:
        for name, entry in (("dem", dem_entry), ("land_use", land_use_entry)):
            configured = Path(entry.files[0]).name if entry and len(entry.files) == 1 else None
            reported = Path(str(outputs.get(name))).name
            if configured and configured != reported:
                errors.append(f"{name} 派生输出与配置文件不匹配")
    derivation = payload.get("derivation")
    if isinstance(derivation, dict):
        errors.extend(_validate_analysis_derivation(derivation))
    checks.append({
        "name": "schema",
        "status": "passed" if not errors else "failed",
        "message": "目标网格、对齐状态和派生输出已核对" if not errors else "分析就绪报告核对失败",
    })
    safe_target = _safe_analysis_target(target)
    safe_alignment = _safe_analysis_alignment(alignment)
    result = {
        **base,
        "status": "ready" if not errors else "degraded",
        "derived_version": str(
            payload.get("derived_version")
            or (dem_entry.version if dem_entry else "")
            or "unknown"
        )[:128],
        "target_grid": safe_target,
        "grid_alignment": safe_alignment,
        "outputs": {
            name: Path(str(outputs[name])).name
            for name in ("dem", "land_use")
            if isinstance(outputs, dict) and outputs.get(name)
        },
        "checks": checks,
        "errors": errors,
        "evidence": {
            "boundary_scope": str((payload.get("evidence") or {}).get("boundary_scope", ""))[:160],
            "source_pixel_read": bool((payload.get("evidence") or {}).get("pixels_read", False)),
        },
    }
    if isinstance(derivation, dict):
        result["derivation"] = _safe_analysis_derivation(derivation)
    source_binding = payload.get("source_binding")
    if isinstance(source_binding, dict):
        result["source_binding"] = _safe_source_binding(source_binding)
    return result


def _safe_analysis_target(target: Any) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return {}
    result: Dict[str, Any] = {}
    if target.get("crs") is not None:
        result["crs"] = str(target["crs"])[:80]
    for name in ("resolution", "bounds"):
        value = target.get(name)
        if isinstance(value, list) and len(value) <= 4:
            try:
                result[name] = [float(item) for item in value]
            except (TypeError, ValueError):
                pass
    for name in ("width", "height"):
        try:
            value = int(target[name])
        except (KeyError, TypeError, ValueError):
            continue
        if value > 0:
            result[name] = value
    return result


def _validate_analysis_target(target: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(target.get("crs"), str) or not target["crs"].strip():
        errors.append("目标网格 CRS 无效")
    resolution = target.get("resolution")
    if not isinstance(resolution, list) or len(resolution) != 2:
        errors.append("目标网格分辨率必须包含两个正数")
    else:
        try:
            values = [float(value) for value in resolution]
            if any(not math.isfinite(value) or value <= 0 for value in values):
                errors.append("目标网格分辨率必须为正数")
        except (TypeError, ValueError):
            errors.append("目标网格分辨率必须为数字")
    bounds = target.get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        errors.append("目标网格范围必须包含四个数字")
    else:
        try:
            left, bottom, right, top = [float(value) for value in bounds]
            if any(not math.isfinite(value) for value in (left, bottom, right, top)):
                errors.append("目标网格范围包含非有限数字")
            elif right <= left or top <= bottom:
                errors.append("目标网格范围必须具有正面积")
        except (TypeError, ValueError):
            errors.append("目标网格范围必须为数字")
    for name in ("width", "height"):
        value = target.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"目标网格{name}必须为正整数")
    return errors


def _safe_analysis_alignment(alignment: Any) -> Dict[str, Any]:
    if not isinstance(alignment, dict):
        return {"status": "unknown"}
    return {
        "status": str(alignment.get("status", "unknown"))[:40],
        "metadata_only": bool(alignment.get("metadata_only", True)),
        "pixels_read": bool(alignment.get("pixels_read", False)),
        "reason": str(alignment.get("reason", ""))[:240],
    }


def _safe_source_binding(binding: Mapping[str, Any]) -> Dict[str, Any]:
    """Expose binding identity while keeping per-file hashes out of responses."""

    result = {
        "binding_version": binding.get("binding_version"),
        "fingerprint": str(binding.get("fingerprint", ""))[:80],
        "verification_mode": str(binding.get("verification_mode", "sha256"))[:20],
        "datasets": sorted(
            str(name)[:64] for name in (binding.get("datasets") or {}).keys()
        ),
        "status": "recorded" if binding.get("fingerprint") else "invalid",
    }
    missing = binding.get("missing_datasets")
    if isinstance(missing, list) and missing:
        result["missing_datasets"] = [str(item)[:64] for item in missing[:20]]
        result["status"] = "degraded"
    return result


def _validate_analysis_derivation(derivation: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    resampling = derivation.get("resampling")
    if not isinstance(resampling, Mapping):
        errors.append("缺少派生重采样策略")
    else:
        if resampling.get("dem") != "bilinear":
            errors.append("DEM 派生必须使用 bilinear 重采样")
        if resampling.get("land_use") != "nearest":
            errors.append("土地利用派生必须使用 nearest 重采样")
    nodata = derivation.get("nodata")
    if not isinstance(nodata, Mapping):
        errors.append("缺少派生 nodata 策略")
    else:
        for name in ("dem", "land_use"):
            value = nodata.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                errors.append(f"{name} nodata 值无效")
    boundary = derivation.get("boundary")
    if not isinstance(boundary, Mapping):
        errors.append("缺少派生边界范围证据")
    else:
        if not isinstance(boundary.get("source_crs"), str) or not boundary["source_crs"].strip():
            errors.append("派生边界 source_crs 无效")
        count = boundary.get("district_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            errors.append("派生边界 district_count 无效")
    return errors


def _safe_analysis_derivation(derivation: Mapping[str, Any]) -> Dict[str, Any]:
    resampling = derivation.get("resampling") or {}
    nodata = derivation.get("nodata") or {}
    boundary = derivation.get("boundary") or {}
    result: Dict[str, Any] = {
        "resampling": {
            "dem": str(resampling.get("dem", ""))[:24],
            "land_use": str(resampling.get("land_use", ""))[:24],
        },
        "nodata": {},
        "boundary": {
            "scope": str(boundary.get("scope", ""))[:160],
            "source_crs": str(boundary.get("source_crs", ""))[:80],
        },
    }
    for name in ("dem", "land_use"):
        value = nodata.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            result["nodata"][name] = float(value)
    count = boundary.get("district_count")
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        result["boundary"]["district_count"] = count
    return result


def _manifest_health(catalog: DatasetCatalog) -> Dict[str, Any]:
    path = Path(catalog.manifest_path)
    if not path.is_file():
        return {
            "status": "unavailable",
            "path_configured": True,
            "required": catalog.manifest_required,
            "verification_mode": "metadata",
            "hashes_verified": False,
            "mismatches": ["manifest file does not exist"],
        }
    try:
        manifest = load_manifest(path)
        verification = verify_dataset_manifest(catalog, manifest, verify_hashes=False)
    except Exception as exc:
        return {
            "status": "unavailable",
            "path_configured": True,
            "required": catalog.manifest_required,
            "verification_mode": "metadata",
            "hashes_verified": False,
            "mismatches": [str(exc)[:240]],
        }
    verification["path_configured"] = True
    verification["required"] = catalog.manifest_required
    return verification


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
