from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from .dataset_catalog import DatasetCatalog
from .errors import ToolError


@dataclass(frozen=True)
class DatasetSchema:
    dataset: str
    geometry_type: str
    crs: str
    fields: List[str]

    def to_result(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset,
            "geometry_type": self.geometry_type,
            "crs": self.crs,
            "fields": list(self.fields),
        }


class SpatialBackend(Protocol):
    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        ...

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        ...

    def spatial_join(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        ...


class InMemorySpatialBackend:
    """Small deterministic backend used before real spatial datasets are connected."""

    def __init__(self):
        self._schemas = {
            "roads": DatasetSchema(
                dataset="roads",
                geometry_type="LineString",
                crs="EPSG:4326",
                fields=["id", "road_level", "geometry"],
            ),
            "slope": DatasetSchema(
                dataset="slope",
                geometry_type="Polygon",
                crs="EPSG:4326",
                fields=["id", "slope_degree", "geometry"],
            ),
            "admin_areas": DatasetSchema(
                dataset="admin_areas",
                geometry_type="Polygon",
                crs="EPSG:4326",
                fields=["id", "name", "geometry"],
            ),
        }

    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        return self._require_schema(dataset).to_result()

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        self._require_schema(dataset)
        count = min(limit, self._estimate_range_count(dataset, conditions, bbox))
        return {
            "result_ref": "memory://range/" + dataset,
            "count": count,
            "crs": "EPSG:4326",
            "metrics": {
                "backend": "in_memory",
                "scanned_features": self._base_count(dataset),
                "returned_features": count,
                "used_bbox": bbox is not None,
            },
        }

    def spatial_join(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        self._require_schema(left_dataset)
        self._require_schema(right_dataset)
        if relation == "near" and distance_m is None:
            raise ToolError("near relation requires distance_m")
        count = self._estimate_join_count(left_dataset, right_dataset, relation, distance_m)
        return {
            "result_ref": "memory://join/" + left_dataset + "-" + right_dataset,
            "count": count,
            "left_dataset": left_dataset,
            "right_dataset": right_dataset,
            "metrics": {
                "backend": "in_memory",
                "relation": relation,
                "distance_m": distance_m,
                "estimated_pairs": count,
            },
        }

    def _require_schema(self, dataset: str) -> DatasetSchema:
        try:
            return self._schemas[dataset]
        except KeyError as exc:
            raise ToolError("unknown dataset: " + dataset) from exc

    def _base_count(self, dataset: str) -> int:
        return {"roads": 32, "slope": 48, "admin_areas": 6}[dataset]

    def _estimate_range_count(
        self, dataset: str, conditions: List[Dict[str, Any]], bbox: Optional[List[float]]
    ) -> int:
        count = self._base_count(dataset)
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")
            if dataset == "slope" and field == "slope_degree" and operator == "gt":
                count = max(1, min(count, 40 - int(value)))
            elif dataset == "roads" and field == "road_level" and operator == "eq":
                count = min(count, 12 if value == "primary" else 20)
            elif dataset == "admin_areas" and field == "name" and operator == "eq":
                count = 1
        if bbox is not None:
            count = max(1, count // 2)
        return count

    def _estimate_join_count(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float],
    ) -> int:
        if relation == "near":
            distance_factor = 1 if distance_m is None else max(1, min(10, int(distance_m // 100)))
            return min(25, distance_factor + 2)
        if relation in ("intersects", "within", "contains"):
            return 6
        return 1


class GeoJSONAdminBackend:
    """Reads the real admin_areas GeoJSON dataset from DatasetCatalog."""

    def __init__(self, catalog: DatasetCatalog):
        self._entry = catalog.require("admin_areas")
        if not self._entry.files:
            raise ToolError("admin_areas dataset has no files")
        self._path = self._entry.files[0]
        self._gdf = None

    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        self._require_admin(dataset)
        gdf = self._load()
        return {
            "dataset": "admin_areas",
            "geometry_type": _single_or_mixed([str(item) for item in gdf.geometry.geom_type.dropna().unique()]),
            "crs": str(gdf.crs) if gdf.crs else None,
            "fields": [str(column) for column in gdf.columns if column != "geometry"],
            "metrics": {
                "backend": "geojson",
                "feature_count": int(len(gdf)),
                "source": self._path,
            },
        }

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        self._require_admin(dataset)
        gdf = self._load()
        filtered = gdf
        for condition in conditions:
            filtered = _apply_condition(filtered, condition)
        if bbox is not None:
            minx, miny, maxx, maxy = bbox
            filtered = filtered.cx[minx:maxx, miny:maxy]
        returned = min(len(filtered), limit)
        names = []
        if "name" in filtered.columns:
            names = [str(item) for item in filtered["name"].head(returned).tolist()]
        return {
            "result_ref": "geojson://range/admin_areas",
            "count": int(returned),
            "crs": str(gdf.crs) if gdf.crs else None,
            "sample_names": names,
            "metrics": {
                "backend": "geojson",
                "scanned_features": int(len(gdf)),
                "returned_features": int(returned),
                "used_bbox": bbox is not None,
                "source": self._path,
            },
        }

    def _load(self):
        if self._gdf is None:
            try:
                import geopandas as gpd
            except ImportError as exc:
                raise ToolError("geopandas is required for GeoJSONAdminBackend") from exc
            self._gdf = gpd.read_file(self._path)
        return self._gdf

    @staticmethod
    def _require_admin(dataset: str) -> None:
        if dataset != "admin_areas":
            raise ToolError("GeoJSONAdminBackend only supports admin_areas")


class HybridSpatialBackend:
    """Routes real datasets to file-backed backends and falls back to memory."""

    def __init__(self, catalog: DatasetCatalog, fallback: Optional[SpatialBackend] = None):
        self._fallback = fallback or InMemorySpatialBackend()
        self._admin = GeoJSONAdminBackend(catalog)

    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        if dataset == "admin_areas":
            return self._admin.get_dataset_schema(dataset)
        return self._fallback.get_dataset_schema(dataset)

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        if dataset == "admin_areas":
            return self._admin.range_query(dataset, conditions, limit, bbox)
        return self._fallback.range_query(dataset, conditions, limit, bbox)

    def spatial_join(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self._fallback.spatial_join(left_dataset, right_dataset, relation, distance_m)


def _apply_condition(gdf, condition: Dict[str, Any]):
    field = condition.get("field")
    operator = condition.get("operator")
    value = condition.get("value")
    if field not in gdf.columns:
        raise ToolError("unknown admin_areas field: " + str(field))
    if operator == "eq":
        return gdf[gdf[field] == value]
    if operator == "neq":
        return gdf[gdf[field] != value]
    if operator == "in":
        return gdf[gdf[field].isin(value)]
    if operator == "gt":
        return gdf[gdf[field] > value]
    if operator == "gte":
        return gdf[gdf[field] >= value]
    if operator == "lt":
        return gdf[gdf[field] < value]
    if operator == "lte":
        return gdf[gdf[field] <= value]
    raise ToolError("unsupported operator: " + str(operator))


def _single_or_mixed(values: List[str]) -> str:
    if not values:
        return "Unknown"
    if len(values) == 1:
        return values[0]
    return "Mixed(" + ",".join(sorted(values)) + ")"


class SpatialToolAdapter:
    """Tool Adapter that translates registry calls into SpatialBackend methods."""

    def __init__(self, backend: SpatialBackend):
        self._backend = backend

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "get_dataset_schema":
            return self._backend.get_dataset_schema(arguments["dataset"])
        if name == "range_query":
            return self._backend.range_query(
                dataset=arguments["dataset"],
                conditions=arguments["conditions"],
                limit=arguments["limit"],
                bbox=arguments.get("bbox"),
            )
        if name == "spatial_join":
            return self._backend.spatial_join(
                left_dataset=arguments["left_dataset"],
                right_dataset=arguments["right_dataset"],
                relation=arguments["relation"],
                distance_m=arguments.get("distance_m"),
            )
        raise ToolError("Adapter does not implement: " + name)
