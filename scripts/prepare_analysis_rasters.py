"""Build a bounded, analysis-ready DEM/land-use raster pair.

The source rasters are kept untouched.  Both derived outputs use one explicit
target grid, so pixel-level tools can rely on an actual alignment artifact
instead of inferring alignment from overlapping source files.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.analysis_ready_binding import build_source_binding
from agent.dataset_catalog import DatasetCatalog
from agent.raster_alignment import raster_alignment_report


DEFAULT_DISTRICTS = (
    "青山区", "江岸区", "武昌区", "汉阳区", "硚口区", "江汉区",
    "汉南区", "东西湖区", "洪山区", "新洲区", "黄陂区", "江夏区", "蔡甸区",
)


def build_analysis_rasters(
    catalog: DatasetCatalog,
    output_dir: str | Path,
    *,
    target_crs: str = "EPSG:32649",
    resolution: float = 30.0,
    district_names: Iterable[str] = DEFAULT_DISTRICTS,
) -> dict[str, Any]:
    """Create aligned DEM and land-use GeoTIFFs and a bounded quality report."""

    if resolution <= 0:
        raise ValueError("resolution must be positive")
    try:
        import geopandas as gpd
        import numpy
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.warp import Resampling, reproject, transform_bounds
        from shapely.ops import unary_union
    except ImportError as exc:
        raise RuntimeError("geopandas, rasterio, numpy and shapely are required") from exc

    admin_entry = catalog.require("admin_areas")
    dem_entry = catalog.require("dem")
    land_use_entry = catalog.require("land_use")
    if not admin_entry.files or not dem_entry.files or not land_use_entry.files:
        raise ValueError("admin_areas, dem and land_use must all have resolved files")

    boundary_frame = gpd.read_file(admin_entry.files[0])
    names = set(district_names)
    if "name" not in boundary_frame.columns:
        raise ValueError("admin_areas must contain a name field")
    selected = boundary_frame[boundary_frame["name"].isin(names)]
    if selected.empty:
        raise ValueError("no requested Wuhan districts were found")
    boundary = unary_union(selected.geometry.tolist())
    source_crs = str(boundary_frame.crs) if boundary_frame.crs else "EPSG:4326"
    if not source_crs:
        raise ValueError("admin_areas CRS is required")
    left, bottom, right, top = transform_bounds(
        source_crs,
        target_crs,
        *boundary.bounds,
        densify_pts=21,
    )
    left = math.floor(left / resolution) * resolution
    bottom = math.floor(bottom / resolution) * resolution
    right = math.ceil(right / resolution) * resolution
    top = math.ceil(top / resolution) * resolution
    width = int(round((right - left) / resolution))
    height = int(round((top - bottom) / resolution))
    if width < 1 or height < 1:
        raise ValueError("target grid has no cells")
    transform = from_origin(left, top, resolution, resolution)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dem_path = output / "dem_aligned.tif"
    land_use_path = output / "land_use_aligned.tif"
    _warp_sources(
        dem_entry.files,
        dem_path,
        target_crs=target_crs,
        transform=transform,
        width=width,
        height=height,
        dtype="float32",
        nodata=-9999.0,
        resampling=Resampling.bilinear,
        rasterio=rasterio,
        numpy=numpy,
        reproject=reproject,
    )
    _warp_sources(
        land_use_entry.files,
        land_use_path,
        target_crs=target_crs,
        transform=transform,
        width=width,
        height=height,
        dtype="uint16",
        nodata=0,
        resampling=Resampling.nearest,
        rasterio=rasterio,
        numpy=numpy,
        reproject=reproject,
    )

    dem_metadata = _raster_metadata(rasterio, dem_path)
    land_use_metadata = _raster_metadata(rasterio, land_use_path)
    alignment = raster_alignment_report(dem_metadata, land_use_metadata)
    report = {
        "status": "ready" if alignment.get("status") == "aligned" else "degraded",
        "report_version": "1",
        "derived_version": "analysis-ready-v1",
        "target_grid": {
            "crs": target_crs,
            "resolution": [resolution, resolution],
            "bounds": [left, bottom, right, top],
            "width": width,
            "height": height,
            "nodata": {"dem": -9999.0, "land_use": 0},
        },
        "source_datasets": {
            "admin_areas": {"file_count": len(admin_entry.files), "crs": source_crs},
            "dem": {"file_count": len(dem_entry.files), "provenance": dem_entry.provenance},
            "land_use": {"file_count": len(land_use_entry.files), "provenance": land_use_entry.provenance},
        },
        "source_binding": build_source_binding(catalog),
        "derivation": {
            "resampling": {"dem": "bilinear", "land_use": "nearest"},
            "nodata": {"dem": -9999.0, "land_use": 0},
            "boundary": {
                "scope": "Wuhan 13 district union bounding grid",
                "source_crs": source_crs,
                "district_count": len(selected),
            },
        },
        "outputs": {
            "dem": dem_path.name,
            "land_use": land_use_path.name,
        },
        "grid_alignment": alignment,
        "evidence": {
            "metadata_only": True,
            "pixels_read": False,
            "boundary_scope": "Wuhan 13 district union bounding grid",
            "warning": "派生栅格用于 demo 空间筛选，不代表法定规划或许可结论。",
        },
    }
    (output / "analysis-ready-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _warp_sources(
    paths: Iterable[str],
    output_path: Path,
    *,
    target_crs: str,
    transform,
    width: int,
    height: int,
    dtype: str,
    nodata,
    resampling,
    rasterio,
    numpy,
    reproject,
) -> None:
    if dtype == "float32":
        target = numpy.full((height, width), nodata, dtype=dtype)
        missing = target == nodata
    else:
        target = numpy.full((height, width), nodata, dtype=dtype)
        missing = target == nodata
    for path in paths:
        with rasterio.open(path) as source:
            temporary = numpy.full((height, width), nodata, dtype=dtype)
            reproject(
                source=rasterio.band(source, 1),
                destination=temporary,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs=target_crs,
                dst_nodata=nodata,
                resampling=resampling,
            )
            if numpy.issubdtype(temporary.dtype, numpy.floating):
                valid = numpy.isfinite(temporary) & (temporary != nodata)
            else:
                valid = temporary != nodata
            fill = valid & missing
            target[fill] = temporary[fill]
            missing[fill] = False
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": dtype,
        "crs": target_crs,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "predictor": 2 if dtype == "float32" else 1,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(output_path, "w", **profile) as destination:
        destination.write(target, 1)
        destination.update_tags(
            preparation="spatial-agent-analysis-ready",
            target_grid="explicit common DEM/land-use grid",
        )


def _raster_metadata(rasterio, path: Path) -> dict[str, Any]:
    with rasterio.open(path) as source:
        return {
            "crs": str(source.crs) if source.crs else None,
            "bounds": [float(source.bounds.left), float(source.bounds.bottom), float(source.bounds.right), float(source.bounds.top)],
            "width": int(source.width),
            "height": int(source.height),
            "pixel_size": [abs(float(source.transform.a)), abs(float(source.transform.e))],
            "transform": [float(source.transform.a), float(source.transform.b), float(source.transform.c), float(source.transform.d), float(source.transform.e), float(source.transform.f)],
        }


def _write_analysis_config(
    source_config: Path,
    output_config: Path,
    output_dir: Path,
    source_binding: dict[str, Any] | None = None,
) -> None:
    payload = json.loads(source_config.read_text(encoding="utf-8"))
    for name, filename in (("dem", "dem_aligned.tif"), ("land_use", "land_use_aligned.tif")):
        definition = dict(payload["datasets"][name])
        definition.pop("glob", None)
        definition["path"] = str((output_dir / filename).resolve())
        definition["version"] = str(definition.get("version", "source")) + "-analysis-ready"
        definition["source"] = "Spatial Agent reproducible aligned derivative"
        payload["datasets"][name] = definition
    report_path = output_dir / "analysis-ready-report.json"
    try:
        report_reference = os.path.relpath(report_path, output_config.parent)
    except ValueError:
        report_reference = str(report_path)
    payload["analysis_ready"] = {
        "report": report_reference.replace("\\", "/"),
        "required": True,
    }
    if source_binding:
        payload["analysis_ready"]["source_binding"] = {
            "binding_version": source_binding.get("binding_version"),
            "fingerprint": source_binding.get("fingerprint"),
            "datasets": sorted((source_binding.get("datasets") or {}).keys()),
        }
    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare aligned Wuhan DEM and land-use rasters.")
    parser.add_argument("--config", required=True, help="source dataset catalog JSON")
    parser.add_argument("--output-dir", required=True, help="derived raster output directory")
    parser.add_argument("--config-output", help="optional derived dataset catalog JSON")
    parser.add_argument("--target-crs", default="EPSG:32649")
    parser.add_argument("--resolution", type=float, default=30.0)
    args = parser.parse_args()
    catalog = DatasetCatalog.from_json(args.config)
    report = build_analysis_rasters(
        catalog,
        args.output_dir,
        target_crs=args.target_crs,
        resolution=args.resolution,
    )
    if args.config_output:
        _write_analysis_config(
            Path(args.config),
            Path(args.config_output),
            Path(args.output_dir),
            source_binding=report.get("source_binding"),
        )
    print(json.dumps({"status": report["status"], "grid_alignment": report["grid_alignment"]["status"], "output_dir": str(Path(args.output_dir))}, ensure_ascii=False))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
