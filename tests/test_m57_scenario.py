import unittest

from agent.scenario import BuildabilityComparisonScenario
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


if __name__ == "__main__":
    unittest.main()
