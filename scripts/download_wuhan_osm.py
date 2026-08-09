"""Download Wuhan OSM road and water ways from Overpass in resumable tiles.

The script deliberately keeps raw Overpass JSON files. Conversion to a GIS
format is a separate step so that the source response remains auditable.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BBOX = (113.698077, 29.971928, 115.076651, 31.362866)
WUHAN_DISTRICTS = {
    "青山区", "江岸区", "武昌区", "汉阳区", "硚口区", "江汉区",
    "汉南区", "东西湖区", "洪山区", "新洲区", "黄陂区", "江夏区", "蔡甸区",
}
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "SpatialAgent/1.0 (OSM data validation; contact project owner)"


@dataclass
class TileRecord:
    row: int
    column: int
    bbox: list[float]
    status: str
    file: str | None = None
    element_count: int = 0
    error: str | None = None


def iter_tiles(bbox: Sequence[float], tile_size: float) -> Iterator[tuple[int, int, list[float]]]:
    """Yield (row, column, [west, south, east, north]) tiles."""
    west, south, east, north = map(float, bbox)
    if not west < east or not south < north or tile_size <= 0:
        raise ValueError("bbox must be [west, south, east, north] and tile_size must be positive")
    row_count = math.ceil((north - south) / tile_size)
    column_count = math.ceil((east - west) / tile_size)
    for row in range(row_count):
        y = south + row * tile_size
        tile_north = min(south + (row + 1) * tile_size, north)
        for column in range(column_count):
            x = west + column * tile_size
            tile_east = min(west + (column + 1) * tile_size, east)
            if x < tile_east and y < tile_north:
                yield row, column, [x, y, tile_east, tile_north]


def build_query(bbox: Sequence[float], timeout: int = 60) -> str:
    west, south, east, north = bbox
    box = f"{south:.7f},{west:.7f},{north:.7f},{east:.7f}"
    return (
        f"[out:json][timeout:{int(timeout)}];"
        f"(way[highway]({box});"
        f"way[natural=water]({box});"
        f"way[waterway]({box}););"
        "out geom;"
    )


def boundary_bbox(path: str | Path, district_names: Iterable[str] = WUHAN_DISTRICTS) -> list[float]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    wanted = set(district_names)
    values: list[tuple[float, float]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            values.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for feature in payload.get("features", []):
        if (feature.get("properties") or {}).get("name") in wanted:
            visit((feature.get("geometry") or {}).get("coordinates", []))
    if not values:
        raise ValueError("no matching Wuhan district geometries found")
    xs, ys = zip(*values)
    return [min(xs), min(ys), max(xs), max(ys)]


def _request_json(endpoint: str, query: str, timeout: int) -> Mapping[str, Any]:
    url = endpoint + ("&" if "?" in endpoint else "?") + urlencode({"data": query})
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def merge_tile_files(paths: Iterable[Path]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for element in payload.get("elements", []):
            key = f"{element.get('type')}:{element.get('id')}"
            merged[key] = element
    return [merged[key] for key in sorted(merged)]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumable Wuhan OSM road/water tile downloader")
    parser.add_argument("--boundary", help="Wuhan district GeoJSON; defaults to the recorded Wuhan bbox")
    parser.add_argument("--output", default="D:/tmp/wuhan-osm", help="Output directory outside the repository")
    parser.add_argument("--tile-size", type=float, default=0.1, help="Tile size in degrees (default: 0.1)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--dry-run", action="store_true", help="Write planned tiles without network requests")
    parser.add_argument("--merge", action="store_true", help="Merge successful tile JSON into merged.json")
    parser.add_argument("--require-complete", action="store_true", help="Do not merge when any tile failed")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    bbox = args.bbox or (boundary_bbox(args.boundary) if args.boundary else list(DEFAULT_BBOX))
    root = Path(args.output)
    tile_dir = root / "tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)
    records: list[TileRecord] = []
    for row, column, tile_bbox in iter_tiles(bbox, args.tile_size):
        target = tile_dir / f"tile_{row:03d}_{column:03d}.json"
        if target.exists() and not args.dry_run:
            try:
                count = len(json.loads(target.read_text(encoding="utf-8")).get("elements", []))
                records.append(TileRecord(row, column, tile_bbox, "completed", str(target), count))
                continue
            except (OSError, json.JSONDecodeError):
                target.unlink(missing_ok=True)
        if args.dry_run:
            records.append(TileRecord(row, column, tile_bbox, "planned", str(target)))
            continue
        error = None
        for attempt in range(args.retries + 1):
            try:
                payload = _request_json(args.endpoint, build_query(tile_bbox, args.timeout), args.timeout + 10)
                target.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
                records.append(TileRecord(row, column, tile_bbox, "completed", str(target), len(payload.get("elements", []))))
                break
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt < args.retries:
                    time.sleep(min(30, 2**attempt))
        else:
            records.append(TileRecord(row, column, tile_bbox, "failed", error=error))

    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"bbox": bbox, "tile_size": args.tile_size, "records": [asdict(r) for r in records]}, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    failed = [record for record in records if record.status == "failed"]
    if args.merge and not failed:
        elements = merge_tile_files(tile_dir.glob("tile_*.json"))
        (root / "merged.json").write_text(json.dumps({"version": 0.6, "generator": "Spatial Agent tile merge", "elements": elements}, ensure_ascii=True), encoding="utf-8")
        print(f"merged {len(elements)} unique elements")
    elif args.merge and args.require_complete:
        print(f"cannot merge: {len(failed)} failed tiles")
    print(f"tiles={len(records)} completed={len(records) - len(failed)} failed={len(failed)} manifest={manifest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
