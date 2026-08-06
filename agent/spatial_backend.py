from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from .dataset_catalog import DatasetCatalog
from .errors import ToolError
from .raster_backend import RasterMetadataBackend


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

    def get_raster_metadata(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        ...

    def get_raster_statistics(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        ...

    def get_zonal_raster_statistics(
        self,
        dataset: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        ...

    def get_zonal_slope_statistics(
        self, admin_name: str, max_files: int = 10
    ) -> Dict[str, Any]:
        ...

    def get_zonal_land_use_distribution(
        self, admin_name: str, max_files: int = 10
    ) -> Dict[str, Any]:
        ...

    def get_zonal_buildability_analysis(
        self, admin_name: str, max_files: int = 10, slope_limit_degrees: float = 15.0
    ) -> Dict[str, Any]:
        ...

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
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
            "first_name": next(
                (
                    str(condition.get("value"))
                    for condition in conditions
                    if dataset == "admin_areas" and condition.get("field") == "name"
                ),
                None,
            ),
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

    def get_raster_metadata(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        if dataset not in ("dem", "land_use"):
            raise ToolError("unknown raster dataset: " + dataset)
        return {
            "dataset": dataset,
            "kind": "raster",
            "format": "img" if dataset == "dem" else "tif",
            "role": "deterministic in-memory raster metadata placeholder",
            "file_count": 0,
            "sample_files": [],
            "metadata": {
                "width": 0,
                "height": 0,
                "band_count": 0,
                "dtypes": [],
                "crs_values": [],
                "bounds": None,
                "pixel_size": None,
                "files": [],
            },
            "metrics": {"backend": "in_memory", "probed_files": 0, "max_files": max_files},
        }

    def get_raster_statistics(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        if dataset not in ("dem", "land_use"):
            raise ToolError("unknown raster dataset: " + dataset)
        return {
            "dataset": dataset,
            "kind": "raster",
            "role": "deterministic in-memory raster statistics placeholder",
            "file_count": 0,
            "statistics": {
                "minimum": 0.0,
                "maximum": 0.0,
                "mean": 0.0,
                "standard_deviation": 0.0,
                "valid_pixel_count": 0,
                "nodata_pixel_count": 0,
                "nodata_ratio": 0.0,
                "files": [],
            },
            "metrics": {"backend": "in_memory", "analyzed_files": 0, "max_files": max_files},
        }

    def get_zonal_raster_statistics(
        self,
        dataset: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        return {
            "dataset": dataset,
            "admin_name": admin_name,
            "file_count": 0,
            "matched_files": [],
            "statistics": {"error": "in-memory backend has no raster geometry"},
            "metrics": {"backend": "in_memory", "analyzed_files": 0},
        }

    def get_zonal_slope_statistics(self, admin_name: str, max_files: int = 10) -> Dict[str, Any]:
        return {"dataset": "slope_from_dem", "admin_name": admin_name, "statistics": {"error": "in-memory backend has no DEM pixels"}, "metrics": {"backend": "in_memory", "analyzed_files": 0}}

    def get_zonal_land_use_distribution(self, admin_name: str, max_files: int = 10) -> Dict[str, Any]:
        return {"dataset": "land_use", "admin_name": admin_name, "statistics": {"error": "in-memory backend has no land-use pixels", "categories": []}, "metrics": {"backend": "in_memory", "analyzed_files": 0}}

    def get_zonal_buildability_analysis(self, admin_name: str, max_files: int = 10, slope_limit_degrees: float = 15.0) -> Dict[str, Any]:
        return {"dataset": "dem+land_use", "admin_name": admin_name, "statistics": {"error": "in-memory backend has no aligned DEM and land-use pixels"}, "metrics": {"backend": "in_memory", "analyzed_files": 0}}

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        return {"type": "FeatureCollection", "features": [], "geometry_source": "none"}

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
        self._result_cache = {}

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

    def geometry_for_name(self, name: str) -> Dict[str, Any]:
        gdf = self._load()
        if "name" not in gdf.columns:
            raise ToolError("admin_areas dataset has no name field")
        selected = gdf[gdf["name"] == name]
        if selected.empty:
            return {"geometry": None, "crs": str(gdf.crs) if gdf.crs else None}
        geometry = selected.geometry.iloc[0]
        if len(selected) > 1:
            geometry = selected.geometry.unary_union
        return {
            "geometry": geometry.__geo_interface__,
            "crs": str(gdf.crs) if gdf.crs else None,
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
        result_ref = "geojson://range/admin_areas"
        self._result_cache[result_ref] = filtered.head(returned).copy()
        return {
            "result_ref": result_ref,
            "count": int(returned),
            "crs": str(gdf.crs) if gdf.crs else None,
            "sample_names": names,
            "first_name": names[0] if names else None,
            "metrics": {
                "backend": "geojson",
                "scanned_features": int(len(gdf)),
                "returned_features": int(returned),
                "used_bbox": bbox is not None,
                "source": self._path,
            },
        }

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        if result_ref not in self._result_cache:
            raise ToolError("result_ref is not available for export: " + result_ref)
        selected = self._result_cache[result_ref].head(max_features)
        features = []
        for _, row in selected.iterrows():
            properties = {}
            for column in ("name", "gb"):
                if column in row and row[column] is not None:
                    properties[column] = str(row[column])
            geometry = row.geometry.__geo_interface__ if row.geometry is not None else None
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
        return {
            "type": "FeatureCollection",
            "features": features,
            "geometry_source": "geojson",
            "crs": {"type": "name", "properties": {"name": str(self._load().crs)}}
            if self._load().crs
            else None,
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
        self._raster = RasterMetadataBackend(catalog)

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

    def get_raster_metadata(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        if dataset in ("dem", "land_use"):
            return self._raster.get_raster_metadata(dataset, max_files=max_files)
        return self._fallback.get_raster_metadata(dataset, max_files=max_files)

    def get_raster_statistics(self, dataset: str, max_files: int = 3) -> Dict[str, Any]:
        if dataset in ("dem", "land_use"):
            return self._raster.get_raster_statistics(dataset, max_files=max_files)
        return self._fallback.get_raster_statistics(dataset, max_files=max_files)

    def get_zonal_raster_statistics(
        self,
        dataset: str,
        admin_name: str,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {
                "dataset": dataset,
                "admin_name": admin_name,
                "file_count": 0,
                "matched_files": [],
                "statistics": {"error": "administrative area was not found"},
                "metrics": {"backend": "geojson", "analyzed_files": 0},
            }
        return self._raster.get_zonal_raster_statistics(
            dataset=dataset,
            geometry=area["geometry"],
            geometry_crs=area["crs"],
            admin_name=admin_name,
            max_files=max_files,
        )

    def get_zonal_slope_statistics(self, admin_name: str, max_files: int = 10) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {"dataset": "slope_from_dem", "admin_name": admin_name, "statistics": {"error": "administrative area was not found"}, "metrics": {"backend": "geojson", "analyzed_files": 0}}
        return self._raster.get_zonal_slope_statistics(area["geometry"], area["crs"], admin_name, max_files=max_files)

    def get_zonal_land_use_distribution(self, admin_name: str, max_files: int = 10) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {"dataset": "land_use", "admin_name": admin_name, "statistics": {"error": "administrative area was not found", "categories": []}, "metrics": {"backend": "geojson", "analyzed_files": 0}}
        return self._raster.get_zonal_land_use_distribution(area["geometry"], area["crs"], admin_name, max_files=max_files)

    def get_zonal_buildability_analysis(self, admin_name: str, max_files: int = 10, slope_limit_degrees: float = 15.0) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {"dataset": "dem+land_use", "admin_name": admin_name, "statistics": {"error": "administrative area was not found"}, "metrics": {"backend": "geojson", "analyzed_files": 0}}
        return self._raster.get_zonal_buildability_analysis(area["geometry"], area["crs"], admin_name, max_files=max_files, slope_limit_degrees=slope_limit_degrees)

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        if result_ref.startswith("geojson://"):
            return self._admin.export_result(result_ref, max_features=max_features)
        if result_ref.startswith("raster://"):
            return self._raster.export_result(result_ref, max_features=max_features)
        return self._fallback.export_result(result_ref, max_features=max_features)


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
        if name == "get_raster_metadata":
            return self._backend.get_raster_metadata(
                dataset=arguments["dataset"],
                max_files=arguments.get("max_files", 3),
            )
        if name == "get_raster_statistics":
            return self._backend.get_raster_statistics(
                dataset=arguments["dataset"],
                max_files=arguments.get("max_files", 3),
            )
        if name == "get_zonal_raster_statistics":
            return self._backend.get_zonal_raster_statistics(
                dataset=arguments["dataset"],
                admin_name=arguments["admin_name"],
                max_files=arguments.get("max_files", 10),
            )
        if name == "get_zonal_slope_statistics":
            return self._backend.get_zonal_slope_statistics(
                admin_name=arguments["admin_name"], max_files=arguments.get("max_files", 10)
            )
        if name == "get_zonal_land_use_distribution":
            return self._backend.get_zonal_land_use_distribution(
                admin_name=arguments["admin_name"], max_files=arguments.get("max_files", 10)
            )
        if name == "get_zonal_buildability_analysis":
            return self._backend.get_zonal_buildability_analysis(
                admin_name=arguments["admin_name"],
                max_files=arguments.get("max_files", 10),
                slope_limit_degrees=arguments.get("slope_limit_degrees", 15.0),
            )
        raise ToolError("Adapter does not implement: " + name)

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._backend, "export_result", None)
        if not callable(exporter):
            raise ToolError("backend does not support result export")
        return exporter(result_ref, max_features=max_features)
