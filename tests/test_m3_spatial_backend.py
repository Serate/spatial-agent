import unittest
from pathlib import Path

from agent.errors import ToolError
from domains.gis.adapters.spatial_backend import InMemorySpatialBackend, SpatialToolAdapter
from agent.tools import ToolRegistry


ROOT = Path(__file__).parents[1]


class M3SpatialBackendTests(unittest.TestCase):
    def test_in_memory_backend_returns_schema(self):
        backend = InMemorySpatialBackend()
        schema = backend.get_dataset_schema("roads")
        self.assertEqual(schema["geometry_type"], "LineString")
        self.assertIn("road_level", schema["fields"])

    def test_in_memory_backend_filters_range_query(self):
        backend = InMemorySpatialBackend()
        result = backend.range_query(
            dataset="slope",
            conditions=[{"field": "slope_degree", "operator": "gt", "value": 30}],
            limit=10000,
        )
        self.assertEqual(result["result_ref"], "memory://range/slope")
        self.assertLessEqual(result["count"], 10)
        self.assertEqual(result["metrics"]["backend"], "in_memory")

    def test_spatial_tool_adapter_dispatches_registry_calls(self):
        registry = ToolRegistry.from_json(
            str(ROOT / "tools" / "schema" / "tool-definitions.json"),
            SpatialToolAdapter(InMemorySpatialBackend()),
        )
        result = registry.invoke(
            "spatial_join",
            {
                "left_dataset": "roads",
                "right_dataset": "slope",
                "relation": "near",
                "distance_m": 500,
            },
        )
        self.assertEqual(result["result_ref"], "memory://join/roads-slope")
        self.assertEqual(result["metrics"]["relation"], "near")

    def test_near_join_requires_distance(self):
        backend = InMemorySpatialBackend()
        with self.assertRaises(ToolError):
            backend.spatial_join("roads", "slope", "near")


if __name__ == "__main__":
    unittest.main()
