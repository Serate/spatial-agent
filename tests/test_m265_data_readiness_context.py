import unittest

from agent.capability_catalog import capability_context_summary
from agent.context_engineering import ContextBuilder
from agent.planner_context import project_planner_sections


class M265DataReadinessContextTests(unittest.TestCase):
    def _catalog(self):
        return {
            "schema_version": "catalog.v1",
            "domain_id": "gis",
            "version": "1.0",
            "environment": "local",
            "capabilities": [
                {
                    "id": "terrain_overview",
                    "label": "地形总览",
                    "description": "分析地形数据",
                    "datasets": ["dem", "land_use"],
                    "tools": ["get_zonal_raster_statistics"],
                    "result_types": ["terrain_result"],
                    "available": True,
                },
                {
                    "id": "roads_only",
                    "label": "道路摘要",
                    "description": "分析道路",
                    "datasets": ["roads"],
                    "tools": ["get_zonal_vector_summary"],
                    "result_types": ["roads_result"],
                    "available": True,
                },
            ],
            "data_evidence": {
                "dem": {
                    "status": "ready",
                    "coverage": [1, 2, 3, 4],
                    "crs": ["EPSG:32649"],
                    "discovery": {
                        "stage": "analysis-ready",
                        "status": "ready",
                        "resolution": [30, 30],
                        "time_range": "2024",
                        "availability_reason": "",
                        "private_path": "must-not-appear",
                    },
                    "analysis_ready": {
                        "status": "ready",
                        "derived_version": "v1",
                        "grid_alignment": {"status": "aligned"},
                    },
                    "path": "D:/private/secret.tif",
                },
                "land_use": {"status": "degraded", "crs": ["EPSG:32649"]},
                "roads": {"status": "ready", "path": "D:/private/roads.gpkg"},
            },
        }

    def test_selected_capability_gets_bounded_dataset_evidence(self):
        summary = capability_context_summary(
            catalog=self._catalog(),
            selected_capability_ids=["terrain_overview"],
            max_capabilities=1,
        )
        item = summary["capabilities"][0]
        self.assertEqual(item["id"], "terrain_overview")
        self.assertEqual(item["dataset_evidence"]["dem"]["status"], "ready")
        self.assertEqual(item["dataset_evidence"]["dem"]["analysis_ready"]["grid_alignment"], "aligned")
        self.assertNotIn("path", str(item["dataset_evidence"]))
        self.assertNotIn("private_path", str(item["dataset_evidence"]))

    def test_planner_context_propagates_readiness_without_unselected_data(self):
        summary = capability_context_summary(
            catalog=self._catalog(),
            selected_capability_ids=["terrain_overview"],
            max_capabilities=1,
        )
        sections = project_planner_sections(
            capability_discovery={"selected_capability_id": "terrain_overview"},
            capability_catalog=summary,
            workflow_selection={"workflow_template_id": "terrain"},
            workflow_templates={"terrain": {"id": "terrain"}},
        )
        packet = ContextBuilder(max_chars=12000).build(
            request="分析地形",
            resolved_request="分析地形",
            session_id="m265",
            available_tools=["get_zonal_raster_statistics"],
            capability_catalog=summary,
            capability_discovery={"selected_capability_id": "terrain_overview"},
            workflow_selection={"workflow_template_id": "terrain"},
            workflow_templates={"terrain": {"id": "terrain"}},
            planner_section_overrides=sections,
        )
        projected = packet.payload["sections"]["capability_catalog"]["capabilities"][0]
        self.assertEqual(projected["dataset_evidence"]["dem"]["crs"], ["EPSG:32649"])
        self.assertNotIn("roads", projected["dataset_evidence"])
        self.assertNotIn("D:/private", packet.rendered)

    def test_legacy_catalog_without_data_evidence_stays_compatible(self):
        summary = capability_context_summary(
            catalog={
                "domain_id": "text",
                "capabilities": [{"id": "conversation", "datasets": [], "tools": []}],
            },
            selected_capability_ids=["conversation"],
        )
        self.assertEqual(summary["capabilities"][0]["dataset_evidence"], {})


if __name__ == "__main__":
    unittest.main()
