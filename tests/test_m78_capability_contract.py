"""M78.1 contract: capability routing ids must converge on the catalog ids."""

import unittest

from agent.capability_catalog import capability_catalog
from agent.capability_routing import CapabilityRouter
from agent.rule_planning import RuleBasedPlanComposer


class M78CapabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog_ids = {
            str(item["id"])
            for item in capability_catalog()["capabilities"]
        }
        cls.route_ids = set(CapabilityRouter().route_ids)
        cls.builder_ids = set(RuleBasedPlanComposer().rule_ids)

    def test_every_route_id_is_declared_in_catalog(self):
        missing = sorted(self.route_ids - self.catalog_ids)
        self.assertEqual(missing, [])

    def test_planner_builders_cover_every_route_id(self):
        missing = sorted(self.route_ids - self.builder_ids)
        self.assertEqual(missing, [])

    def test_no_builder_orphan_without_a_route(self):
        orphans = sorted(self.builder_ids - self.route_ids)
        self.assertEqual(orphans, [])

    def test_catalog_declares_composed_and_legacy_capabilities(self):
        expected = {
            "spatial_analysis",
            "zonal_terrain_land_use",
            "vector_summary",
            "constrained_buildability_screening",
            "dataset_health",
            "raster_statistics",
            "vector_query",
            "vector_relation",
            "legacy_road_slope",
            "admin_raster_composite",
        }
        self.assertTrue(expected.issubset(self.catalog_ids))

    def test_evaluation_capability_ids_exist_in_catalog(self):
        """Global acceptance uses catalog ids; they must never drift."""
        import json
        from pathlib import Path

        cases = json.loads(
            (Path(__file__).parents[1] / "evaluation" / "cases" / "global-acceptance.json").read_text(
                encoding="utf-8"
            )
        )
        used = {
            str(case.get("capability_id"))
            for case in cases
            if case.get("capability_id")
        }
        missing = sorted(used - self.catalog_ids)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
