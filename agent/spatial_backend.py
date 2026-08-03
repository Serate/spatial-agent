from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

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
