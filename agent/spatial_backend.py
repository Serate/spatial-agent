import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from .dataset_catalog import DatasetCatalog
from .data_quality import dataset_health_report
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

    def get_dataset_health_report(self, dataset: str = "all", max_files: int = 10) -> Dict[str, Any]:
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

    def get_zonal_vector_summary(
        self, dataset: str, admin_name: str, max_features: int = 10000
    ) -> Dict[str, Any]:
        ...

    def get_zonal_constrained_buildability_analysis(
        self,
        admin_name: str,
        slope_limit_degrees: float = 15.0,
        road_distance_m: float = 500.0,
        exclude_water: bool = True,
        max_files: int = 10,
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
            "water": DatasetSchema(
                dataset="water",
                geometry_type="Polygon/LineString",
                crs="EPSG:4326",
                fields=["id", "name", "natural", "waterway", "geometry"],
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

    def get_dataset_health_report(self, dataset: str = "all", max_files: int = 10) -> Dict[str, Any]:
        allowed = ("admin_areas", "dem", "land_use", "roads", "water")
        names = allowed if dataset == "all" else (dataset,)
        if dataset != "all" and dataset not in allowed:
            raise ToolError("unknown health dataset: " + dataset)
        reports = [
            {
                "dataset": name,
                "status": "degraded",
                "kind": "raster" if name in ("dem", "land_use") else "vector",
                "file_count": 0,
                "checks": [{"name": "backend", "status": "warning", "message": "当前为内存演示后端"}],
                "errors": ["未连接本地数据文件"],
                "usable_for": [],
                "metrics": {"checked_files": 0, "backend": "in_memory"},
            }
            for name in names
        ]
        return {
            "dataset": dataset,
            "status": "degraded",
            "datasets": reports,
            "capabilities": {name: [] for name in names},
            "metrics": {"backend": "in_memory", "checked_datasets": len(reports), "max_files_per_dataset": max_files},
            "warning": "内存演示后端不代表真实 GIS 数据可用性。",
        }

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

    def get_zonal_vector_summary(self, dataset: str, admin_name: str, max_features: int = 10000) -> Dict[str, Any]:
        if dataset not in ("roads", "water"):
            raise ToolError("unknown vector dataset: " + dataset)
        return {
            "dataset": dataset,
            "admin_name": admin_name,
            "summary": {"error": "in-memory backend has no vector geometry"},
            "metrics": {"backend": "in_memory", "matched_features": 0},
        }

    def get_zonal_constrained_buildability_analysis(self, admin_name: str, slope_limit_degrees: float = 15.0, road_distance_m: float = 500.0, exclude_water: bool = True, max_files: int = 10) -> Dict[str, Any]:
        return {
            "dataset": "dem+land_use+roads+water",
            "admin_name": admin_name,
            "statistics": {"error": "in-memory backend has no aligned raster and vector geometry"},
            "metrics": {"backend": "in_memory", "constraint_sampled": True},
        }

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        return {"type": "FeatureCollection", "features": [], "geometry_source": "none"}

    def _require_schema(self, dataset: str) -> DatasetSchema:
        try:
            return self._schemas[dataset]
        except KeyError as exc:
            raise ToolError("unknown dataset: " + dataset) from exc

    def _base_count(self, dataset: str) -> int:
        return {"roads": 32, "water": 24, "slope": 48, "admin_areas": 6}[dataset]

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
        from .geometry_export import normalize_feature_collection

        return normalize_feature_collection({
            "type": "FeatureCollection",
            "features": features,
            "geometry_source": "geojson",
            "crs": {"type": "name", "properties": {"name": str(self._load().crs)}}
            if self._load().crs
            else None,
        })

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


class GeoPackageBackend:
    """Reads clipped OSM vector layers from a local GeoPackage."""

    def __init__(self, catalog: DatasetCatalog):
        self._entries = {
            name: entry
            for name in ("roads", "water")
            if (entry := catalog.get(name)) is not None and entry.files
        }
        self._cache = {}
        self._result_cache = {}
        self._result_number = 0

    def supports(self, dataset: str) -> bool:
        return dataset in self._entries

    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        gdf = self._load(dataset)
        geometry_types = sorted(str(item) for item in gdf.geometry.geom_type.dropna().unique())
        return {
            "dataset": dataset,
            "geometry_type": _single_or_mixed(geometry_types),
            "crs": str(gdf.crs) if gdf.crs else None,
            "fields": [str(column) for column in gdf.columns if column != "geometry"],
            "metrics": {
                "backend": "geopackage",
                "feature_count": int(len(gdf)),
                "source": self._entries[dataset].files[0],
            },
        }

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        gdf = self._load(dataset)
        filtered = gdf
        for condition in conditions:
            filtered = _apply_vector_condition(filtered, condition)
        if bbox is not None:
            filtered = _clip_bbox(filtered, bbox)
        returned = filtered.head(limit).copy()
        self._result_number += 1
        result_ref = f"gpkg://range/{dataset}/{self._result_number}"
        self._result_cache[result_ref] = returned
        names = [str(value) for value in returned.get("name", []).tolist() if value]
        return {
            "result_ref": result_ref,
            "count": int(len(returned)),
            "crs": str(gdf.crs) if gdf.crs else None,
            "sample_names": names[:10],
            "first_name": names[0] if names else None,
            "metrics": {
                "backend": "geopackage",
                "scanned_features": int(len(gdf)),
                "returned_features": int(len(returned)),
                "used_bbox": bbox is not None,
                "source": self._entries[dataset].files[0],
            },
        }

    def spatial_join(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self.supports(left_dataset) or not self.supports(right_dataset):
            raise ToolError("GeoPackage spatial join requires roads or water datasets")
        if relation == "near" and distance_m is None:
            raise ToolError("near relation requires distance_m")
        import geopandas as gpd

        left = self._load(left_dataset)
        right = self._load(right_dataset)
        if relation == "near":
            projected_left = left.to_crs("EPSG:3857")
            projected_right = right.to_crs("EPSG:3857")
            joined = gpd.sjoin_nearest(
                projected_left,
                projected_right,
                how="inner",
                max_distance=float(distance_m),
                distance_col="distance_m",
            )
        else:
            joined = gpd.sjoin(left, right, how="inner", predicate=relation)
        result_ref = f"gpkg://join/{left_dataset}-{right_dataset}"
        self._result_cache[result_ref] = joined.head(10000).copy()
        return {
            "result_ref": result_ref,
            "count": int(len(joined)),
            "left_dataset": left_dataset,
            "right_dataset": right_dataset,
            "distance_m": distance_m,
            "metrics": {
                "backend": "geopackage",
                "relation": relation,
                "distance_m": distance_m,
                "left_features": int(len(left)),
                "right_features": int(len(right)),
            },
        }

    def get_zonal_vector_summary(
        self,
        dataset: str,
        geometry: dict,
        geometry_crs: str | None,
        admin_name: str,
        max_features: int = 10000,
    ) -> Dict[str, Any]:
        import geopandas as gpd
        from shapely.geometry import shape

        gdf = self._load(dataset)
        boundary = gpd.GeoSeries([shape(geometry)], crs=geometry_crs or "EPSG:4326")
        if gdf.crs and boundary.crs and str(gdf.crs) != str(boundary.crs):
            boundary = boundary.to_crs(gdf.crs)
        boundary_geometry = boundary.iloc[0]
        matched = gdf[gdf.intersects(boundary_geometry)].copy()
        clipped = matched.head(max_features).copy()
        if not clipped.empty:
            clipped["geometry"] = clipped.geometry.intersection(boundary_geometry)
        self._result_number += 1
        result_ref = f"gpkg://zonal/{dataset}/{self._result_number}"
        self._result_cache[result_ref] = clipped
        category_field = "road_level" if dataset == "roads" else "waterway"
        if dataset == "water":
            categories = clipped["waterway"].replace("", None).fillna(clipped["natural"]).fillna("unknown")
        else:
            categories = clipped[category_field].fillna("unknown")
        category_counts = {
            str(key): int(value)
            for key, value in categories.value_counts().to_dict().items()
        }
        return {
            "result_ref": result_ref,
            "dataset": dataset,
            "admin_name": admin_name,
            "count": int(len(matched)),
            "summary": {
                "matched_features": int(len(matched)),
                "returned_features": int(len(clipped)),
                "category_field": category_field,
                "category_counts": category_counts,
                "named_features": int((matched["name"].fillna("") != "").sum()),
            },
            "crs": str(gdf.crs) if gdf.crs else None,
            "metrics": {
                "backend": "geopackage",
                "source": self._entries[dataset].files[0],
                "max_features": max_features,
            },
        }

    def constrain_candidate_geometry(
        self,
        collection: Dict[str, Any],
        road_distance_m: float,
        exclude_water: bool,
    ) -> Dict[str, Any]:
        import geopandas as gpd
        import pandas as pd

        if not self.supports("roads"):
            raise ToolError("roads dataset is not configured")
        if road_distance_m < 0:
            raise ToolError("road_distance_m must be non-negative")
        candidate_crs = _collection_crs(collection) or "EPSG:4326"
        candidates = gpd.GeoDataFrame.from_features(collection.get("features", []), crs=candidate_crs)
        if candidates.empty:
            return {"collection": collection, "summary": {"candidate_features": 0, "eligible_features": 0, "water_excluded_features": 0, "road_distance_m": road_distance_m}}
        target_crs = _metric_crs(candidate_crs)
        projected = candidates.to_crs(target_crs)
        roads = self._load("roads").to_crs(target_crs)
        road_index = roads.sindex
        near_roads = []
        for candidate in projected.geometry:
            nearby = road_index.query(candidate.buffer(float(road_distance_m)))
            near_roads.append(
                any(candidate.distance(roads.geometry.iloc[int(index)]) <= float(road_distance_m) for index in nearby)
            )
        near_roads = pd.Series(near_roads, index=projected.index, dtype=bool)
        water_excluded = pd.Series(False, index=projected.index, dtype=bool)
        if exclude_water and self.supports("water"):
            water = self._load("water").to_crs(target_crs)
            water_index = water.sindex
            water_excluded = pd.Series(
                [
                    any(candidate.intersects(water.geometry.iloc[int(index)]) for index in water_index.query(candidate))
                    for candidate in projected.geometry
                ],
                index=projected.index,
                dtype=bool,
            )
        eligible = near_roads & ~water_excluded
        filtered = candidates[eligible].copy()
        output = json.loads(filtered.to_json())
        output["crs"] = {
            "type": "name",
            "properties": {"name": str(candidates.crs)},
        }
        summary = {
            "candidate_features": int(len(candidates)),
            "eligible_features": int(len(filtered)),
            "road_distance_m": float(road_distance_m),
            "water_excluded_features": int(water_excluded.sum()),
            "road_rejected_features": int((~near_roads).sum()),
            "constraint_sampled": True,
            "sample_limit": int(len(candidates)),
        }
        return {"collection": output, "summary": summary}

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        if result_ref not in self._result_cache:
            raise ToolError("result_ref is not available for export: " + result_ref)
        selected = self._result_cache[result_ref].head(max_features)
        features = []
        for _, row in selected.iterrows():
            properties = {
                str(column): str(row[column])
                for column in selected.columns
                if column != "geometry" and row[column] is not None
            }
            features.append({
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__ if row.geometry is not None else None,
                "properties": properties,
            })
        from .geometry_export import normalize_feature_collection

        return normalize_feature_collection({
            "type": "FeatureCollection",
            "features": features,
            "geometry_source": "geopackage",
            "crs": {"type": "name", "properties": {"name": str(selected.crs)}}
            if selected.crs
            else None,
        })

    def _load(self, dataset: str):
        if not self.supports(dataset):
            raise ToolError("GeoPackage dataset is not configured: " + dataset)
        if dataset not in self._cache:
            try:
                import geopandas as gpd
                self._cache[dataset] = gpd.read_file(self._entries[dataset].files[0], layer=dataset)
            except ImportError as exc:
                raise ToolError("geopandas is required for GeoPackageBackend") from exc
        return self._cache[dataset]


class HybridSpatialBackend:
    """Routes real datasets to file-backed backends and falls back to memory."""

    def __init__(self, catalog: DatasetCatalog, fallback: Optional[SpatialBackend] = None):
        self._catalog = catalog
        self._fallback = fallback or InMemorySpatialBackend()
        self._admin = GeoJSONAdminBackend(catalog)
        self._vectors = GeoPackageBackend(catalog)
        self._raster = RasterMetadataBackend(catalog)

    def get_dataset_schema(self, dataset: str) -> Dict[str, Any]:
        if dataset == "admin_areas":
            return self._admin.get_dataset_schema(dataset)
        if self._vectors.supports(dataset):
            return self._vectors.get_dataset_schema(dataset)
        return self._fallback.get_dataset_schema(dataset)

    def get_dataset_health_report(self, dataset: str = "all", max_files: int = 10) -> Dict[str, Any]:
        return dataset_health_report(self._catalog, dataset=dataset, max_files=max_files)

    def range_query(
        self,
        dataset: str,
        conditions: List[Dict[str, Any]],
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        if dataset == "admin_areas":
            return self._admin.range_query(dataset, conditions, limit, bbox)
        if self._vectors.supports(dataset):
            return self._vectors.range_query(dataset, conditions, limit, bbox)
        return self._fallback.range_query(dataset, conditions, limit, bbox)

    def spatial_join(
        self,
        left_dataset: str,
        right_dataset: str,
        relation: str,
        distance_m: Optional[float] = None,
    ) -> Dict[str, Any]:
        if self._vectors.supports(left_dataset) and self._vectors.supports(right_dataset):
            return self._vectors.spatial_join(left_dataset, right_dataset, relation, distance_m)
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

    def get_zonal_vector_summary(self, dataset: str, admin_name: str, max_features: int = 10000) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {
                "dataset": dataset,
                "admin_name": admin_name,
                "summary": {"error": "administrative area was not found"},
                "metrics": {"backend": "geojson", "matched_features": 0},
            }
        if self._vectors.supports(dataset):
            return self._vectors.get_zonal_vector_summary(dataset, area["geometry"], area["crs"], admin_name, max_features)
        return self._fallback.get_zonal_vector_summary(dataset, admin_name, max_features)

    def get_zonal_constrained_buildability_analysis(self, admin_name: str, slope_limit_degrees: float = 15.0, road_distance_m: float = 500.0, exclude_water: bool = True, max_files: int = 10) -> Dict[str, Any]:
        area = self._admin.geometry_for_name(admin_name)
        if area["geometry"] is None:
            return {"dataset": "dem+land_use+roads+water", "admin_name": admin_name, "statistics": {"error": "administrative area was not found"}, "metrics": {"backend": "geojson", "constraint_sampled": True}}
        base = self._raster.get_zonal_buildability_analysis(area["geometry"], area["crs"], admin_name, max_files=max_files, slope_limit_degrees=slope_limit_degrees)
        base_ref = base.get("result_ref")
        if not base_ref or not self._vectors.supports("roads"):
            base["statistics"] = {**(base.get("statistics") or {}), "constraint_error": "roads dataset is not configured"}
            return base
        candidates = self._raster.export_result(base_ref, max_features=10000)
        constrained = self._vectors.constrain_candidate_geometry(candidates, road_distance_m, exclude_water)
        result_ref = self._raster.cache_geometry_result(constrained["collection"], "constrained-buildability")
        base["result_ref"] = result_ref
        base["constraints"] = {
            "road_distance_m": road_distance_m,
            "exclude_water": exclude_water,
            "warning": "道路/水体约束仅应用于有限候选几何样本，不代表全像元精确适宜性或法定规划结论。",
        }
        base["constraint_summary"] = constrained["summary"]
        base["metrics"] = {**(base.get("metrics") or {}), "constraint_sampled": True, "vector_backend": "geopackage"}
        return base

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        if result_ref.startswith("geojson://"):
            return self._admin.export_result(result_ref, max_features=max_features)
        if result_ref.startswith("raster://"):
            return self._raster.export_result(result_ref, max_features=max_features)
        if result_ref.startswith("gpkg://"):
            return self._vectors.export_result(result_ref, max_features=max_features)
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


def _apply_vector_condition(gdf, condition: Dict[str, Any]):
    field = condition.get("field")
    if field not in gdf.columns:
        raise ToolError("unknown vector field: " + str(field))
    return _apply_condition(gdf, condition)


def _clip_bbox(gdf, bbox: List[float]):
    if len(bbox) != 4 or not bbox[0] < bbox[2] or not bbox[1] < bbox[3]:
        raise ToolError("bbox must be [minx, miny, maxx, maxy]")
    source = gdf
    if source.crs and str(source.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
        source = source.to_crs("EPSG:4326")
    return source.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]


def _collection_crs(collection: Dict[str, Any]) -> Optional[str]:
    crs = collection.get("crs")
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        properties = crs.get("properties") or {}
        name = properties.get("name")
        if name:
            return str(name)
    return None


def _metric_crs(crs: str) -> str:
    from pyproj import CRS

    parsed = CRS.from_user_input(crs)
    return crs if parsed.is_projected else "EPSG:3857"


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
        if name == "get_dataset_health_report":
            return self._backend.get_dataset_health_report(
                dataset=arguments.get("dataset", "all"),
                max_files=arguments.get("max_files", 10),
            )
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
        if name == "get_zonal_vector_summary":
            return self._backend.get_zonal_vector_summary(
                dataset=arguments["dataset"],
                admin_name=arguments["admin_name"],
                max_features=arguments.get("max_features", 10000),
            )
        if name == "get_zonal_constrained_buildability_analysis":
            return self._backend.get_zonal_constrained_buildability_analysis(
                admin_name=arguments["admin_name"],
                slope_limit_degrees=arguments.get("slope_limit_degrees", 15.0),
                road_distance_m=arguments.get("road_distance_m", 500.0),
                exclude_water=arguments.get("exclude_water", True),
                max_files=arguments.get("max_files", 10),
            )
        raise ToolError("Adapter does not implement: " + name)

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._backend, "export_result", None)
        if not callable(exporter):
            raise ToolError("backend does not support result export")
        return exporter(result_ref, max_features=max_features)
