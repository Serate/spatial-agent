import unittest

from agent.scenario import (
    BuildabilityComparisonScenario,
    ConstrainedBuildabilityComparisonScenario,
)
from agent.service import AgentService


class M57ScenarioTests(unittest.TestCase):
    def test_threshold_and_region_inputs_share_normalized_scenario_contract(self):
        threshold = BuildabilityComparisonScenario.for_thresholds(
            " 洪山区 ", [20, "20", 15]
        )
        regions = BuildabilityComparisonScenario.for_regions(
            ["洪山区", " 江夏区 ", "洪山区"], 20
        )

        self.assertEqual(threshold.to_dict(), {
            "operation": "buildability_comparison",
            "admin_names": ["洪山区"],
            "thresholds": [20.0, 15.0],
        })
        self.assertEqual(regions.admin_names, ("洪山区", "江夏区"))
        self.assertEqual(regions.thresholds, (20.0,))

    def test_service_exposes_scenario_for_both_comparison_shapes(self):
        service = AgentService()
        thresholds = service.compare_buildability("洪山区", [15, 20], backend="memory")
        regions = service.compare_buildability_regions(
            ["洪山区", "江夏区"], threshold=20, backend="memory"
        )

        self.assertEqual(thresholds["scenario"]["admin_names"], ["洪山区"])
        self.assertEqual(regions["scenario"]["admin_names"], ["洪山区", "江夏区"])
        self.assertEqual(regions["scenario"]["thresholds"], [20.0])

    def test_scenario_rejects_out_of_range_threshold(self):
        with self.assertRaises(ValueError):
            BuildabilityComparisonScenario.for_thresholds("洪山区", [0])

    def test_constrained_scenario_normalizes_and_sorts_distances(self):
        scenario = ConstrainedBuildabilityComparisonScenario.for_road_distances(
            " 洪山区 ", 15, [1000, "500", 200, 500]
        )
        self.assertEqual(scenario.admin_name, "洪山区")
        self.assertEqual(scenario.slope_limit_degrees, 15.0)
        self.assertEqual(scenario.road_distances, (200.0, 500.0, 1000.0))
        self.assertEqual(scenario.to_dict(), {
            "operation": "constrained_buildability_comparison",
            "admin_name": "洪山区",
            "slope_limit_degrees": 15.0,
            "road_distances": [200.0, 500.0, 1000.0],
        })

    def test_constrained_scenario_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            ConstrainedBuildabilityComparisonScenario.for_road_distances("洪山区", 15, [])
        with self.assertRaises(ValueError):
            ConstrainedBuildabilityComparisonScenario.for_road_distances("洪山区", 15, [200, -5])
        with self.assertRaises(ValueError):
            ConstrainedBuildabilityComparisonScenario.for_road_distances("洪山区", 0, [200])
        with self.assertRaises(ValueError):
            ConstrainedBuildabilityComparisonScenario.for_road_distances("洪山区", "x", [200])

    def test_service_exposes_constrained_scenario(self):
        service = AgentService()
        result = service.compare_constrained_buildability(
            "洪山区", [200, 500], slope_limit_degrees=15, backend="memory"
        )
        self.assertEqual(result["scenario"]["operation"], "constrained_buildability_comparison")
        self.assertEqual(result["road_distances"], [200.0, 500.0])
        self.assertIn("monotonic_eligible_features", result)
        self.assertEqual(len(result["results"]), 2)


if __name__ == "__main__":
    unittest.main()
