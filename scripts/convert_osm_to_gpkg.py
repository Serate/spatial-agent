"""Convert merged Overpass ways into boundary-clipped GeoPackage layers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

WUHAN_DISTRICTS = {
    "青山区", "江岸区", "武昌区", "汉阳区", "硚口区", "江汉区",
    "汉南区", "东西湖区", "洪山区", "新洲区", "黄陂区", "江夏区", "蔡甸区",
}


def load_boundary(boundary_path: str | Path, district_names: Iterable[str] = WUHAN_DISTRICTS):
    import geopandas as gpd
    from shapely.ops import unary_union

    gdf = gpd.read_file(boundary_path)
    selected = gdf[gdf["name"].isin(set(district_names))]
    if selected.empty:
        raise ValueError("no Wuhan district geometries found in boundary dataset")
    boundary = unary_union(selected.geometry.tolist())
    source_crs = str(gdf.crs) if gdf.crs else "EPSG:4326"
    if source_crs.upper() not in {"EPSG:4326", "OGC:CRS84"}:
        boundary = gpd.GeoSeries([boundary], crs=source_crs).to_crs("EPSG:4326").iloc[0]
    return boundary


def _coordinates(element: dict[str, Any]) -> list[tuple[float, float]]:
    return [(float(point["lon"]), float(point["lat"])) for point in element.get("geometry", [])]


def _tags(element: dict[str, Any]) -> dict[str, Any]:
    tags = element.get("tags") or {}
    return tags if isinstance(tags, dict) else {}


def _road_level(tags: dict[str, Any]) -> str:
    highway = str(tags.get("highway", ""))
    return {
        "motorway": "motorway", "trunk": "trunk", "primary": "primary",
        "secondary": "secondary", "tertiary": "tertiary",
    }.get(highway, "local")


def _water_geometry(element: dict[str, Any], tags: dict[str, Any]):
    from shapely.geometry import LineString, Polygon

    points = _coordinates(element)
    if len(points) < 2:
        return None
    if tags.get("natural") == "water" and points[0] == points[-1] and len(points) >= 4:
        return Polygon(points)
    return LineString(points)


def convert(merged_path: str | Path, boundary_path: str | Path, output_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    import geopandas as gpd
    from shapely.geometry import LineString

    payload = json.loads(Path(merged_path).read_text(encoding="utf-8"))
    boundary = load_boundary(boundary_path)
    road_rows: list[dict[str, Any]] = []
    water_rows: list[dict[str, Any]] = []
    counters = {
        "input_elements": len(payload.get("elements", [])),
        "road_candidates": 0,
        "water_candidates": 0,
        "road_features": 0,
        "water_features": 0,
        "empty_geometry": 0,
        "invalid_geometry": 0,
        "empty_after_clip": 0,
    }
    for element in payload.get("elements", []):
        tags = _tags(element)
        is_road = "highway" in tags
        is_water = tags.get("natural") == "water" or "waterway" in tags
        if not is_road and not is_water:
            continue
        geometry = LineString(_coordinates(element)) if is_road else _water_geometry(element, tags)
        if geometry is None or geometry.is_empty:
            counters["empty_geometry"] += 1
            continue
        if is_road:
            counters["road_candidates"] += 1
        if is_water:
            counters["water_candidates"] += 1
        if not geometry.is_valid:
            counters["invalid_geometry"] += 1
            geometry = geometry.make_valid()
        clipped = geometry.intersection(boundary)
        if clipped.is_empty:
            counters["empty_after_clip"] += 1
            continue
        row = {
            "osm_id": int(element.get("id", 0)),
            "osm_type": str(element.get("type", "way")),
            "name": str(tags.get("name", ""))[:250],
            "tags_json": json.dumps(tags, ensure_ascii=False, sort_keys=True),
            "geometry": clipped,
        }
        if is_road:
            row.update({"highway": str(tags.get("highway", "")), "road_level": _road_level(tags)})
            road_rows.append(row)
            counters["road_features"] += 1
        if is_water:
            water_rows.append({**row, "natural": str(tags.get("natural", "")), "waterway": str(tags.get("waterway", ""))})
            counters["water_features"] += 1
    roads = gpd.GeoDataFrame(road_rows, geometry="geometry", crs="EPSG:4326")
    water = gpd.GeoDataFrame(water_rows, geometry="geometry", crs="EPSG:4326")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    if not roads.empty:
        roads.to_file(output, layer="roads", driver="GPKG", index=False)
    if not water.empty:
        water.to_file(output, layer="water", driver="GPKG", index=False)
    report = {
        "source": str(merged_path),
        "boundary": str(boundary_path),
        "output": str(output),
        "crs": "EPSG:4326",
        "layers": {"roads": len(roads), "water": len(water)},
        "quality": counters,
        "provenance": {
            "provider": "OpenStreetMap contributors",
            "license": "ODbL 1.0",
            "attribution": "© OpenStreetMap contributors",
            "geometry_scope": "ways with highway, natural=water, or waterway tags",
            "boundary_scope": "union of Wuhan 13 district geometries; clipped from envelope download",
        },
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Wuhan OSM ways to clipped GeoPackage layers")
    parser.add_argument("--merged", required=True)
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--output", default="D:/tmp/wuhan-gis/wuhan-osm.gpkg")
    parser.add_argument("--report", default="D:/tmp/wuhan-gis/quality-report.json")
    args = parser.parse_args()
    report = convert(args.merged, args.boundary, args.output, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
