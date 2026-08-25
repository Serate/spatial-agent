"""Compact contracts for extending GIS with a file-backed vector dataset."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from agent.dataset_catalog import DatasetCatalog
from agent.planner import RuleBasedPlanner
from agent.spatial_backend import GeoPackageBackend, SpatialToolAdapter
from agent.tools import ToolRegistry
from domains.gis.domain import GIS_CATALOG_SPEC, GisDomainPack
from domains.gis.request_model import parse_spatial_request


ROOT = Path(__file__).parents[1]


def _write_vector_fixture(root: Path) -> Path:
    path = root / "events.geojson"
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [114.30, 30.50]},
                "properties": {"mag": 2.4, "place": "西侧"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [114.35, 30.55]},
                "properties": {"mag": 3.1, "place": "东侧"},
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class M268GenericVectorQueryTests(unittest.TestCase):
    def _catalog(self, root: Path) -> DatasetCatalog:
        _write_vector_fixture(root)
        config = root / "datasets.json"
        config.write_text(
            json.dumps(
                {
                    "root": str(root),
                    "datasets": {
                        "earthquakes_wuhan": {
                            "kind": "vector",
                            "format": "geojson",
                            "path": "events.geojson",
                            "role": "test events",
                            "status": "ready",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return DatasetCatalog.from_json(str(config))

    def test_geojson_schema_and_filtered_query_use_generic_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = GeoPackageBackend(self._catalog(Path(directory)))
            schema = backend.get_dataset_schema("earthquakes_wuhan")
            self.assertEqual(schema["metrics"]["backend"], "geojson")
            self.assertIn("mag", schema["fields"])

            registry = ToolRegistry.from_json(
                str(ROOT / "tools" / "schema" / "tool-definitions.json"),
                SpatialToolAdapter(backend),
            )
            result = registry.invoke(
                "range_query",
                {
                    "dataset": "earthquakes_wuhan",
                    "conditions": [
                        {"field": "mag", "operator": "gte", "value": 2.5}
                    ],
                    "bbox": [114.0, 30.0, 114.6, 30.8],
                    "limit": 100,
                },
            )
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["first_name"], "东侧")
            exported = backend.export_result(result["result_ref"], max_features=10)
            self.assertEqual(exported["geometry_source"], "geojson")
            self.assertEqual(len(exported["features"]), 1)

    def test_catalog_discovery_and_rule_planner_reuse_existing_workflow_tools(self):
        discovery = GisDomainPack().discover(
            "查询武汉周边地震事件",
            parse_spatial_request("查询武汉周边地震事件"),
        )
        self.assertEqual(discovery.selected.capability_id, "earthquake_event_query")

        plan = RuleBasedPlanner().plan(
            "查询武汉周边地震事件",
            context={
                "sections": {
                    "spatial_request": {
                        "schema_version": "test",
                        "tasks": [],
                        "datasets": ["earthquakes_wuhan"],
                        "constraints": {},
                    },
                    "capability_discovery": {
                        "selected_capability_id": "earthquake_event_query",
                        "selection_state": "selected",
                    },
                }
            },
        )
        self.assertEqual(
            [step.tool for step in plan.steps],
            ["get_dataset_schema", "range_query"],
        )
        self.assertEqual(plan.steps[-1].args["dataset"], "earthquakes_wuhan")

    def test_catalog_declares_dataset_without_new_tool_or_runtime_surface(self):
        from agent.domain_catalog import validate_domain_catalog_spec

        validate_domain_catalog_spec(GIS_CATALOG_SPEC)
        capability = next(
            item
            for item in GIS_CATALOG_SPEC.capabilities
            if item["id"] == "earthquake_event_query"
        )
        self.assertEqual(capability["tools"], ["get_dataset_schema", "range_query"])
        self.assertEqual(capability["result_types"], ["vector_result"])
        self.assertEqual(
            GIS_CATALOG_SPEC.workflow_templates["earthquake_event_query"]["allowed_tools"],
            ["get_dataset_schema", "range_query"],
        )


if __name__ == "__main__":
    unittest.main()
