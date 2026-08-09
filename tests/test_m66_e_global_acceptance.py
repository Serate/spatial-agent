import unittest
from pathlib import Path

from agent.service import AgentService
from evaluation.global_runner import run_global_cases
from evaluation.runner import load_cases
from run_demo import build_runtime


ROOT = Path(__file__).parents[1]


class M66EGlobalAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(str(ROOT / "evaluation" / "cases" / "m66-e-acceptance.json"))

    def test_known_capability_missing_parameters_is_structured_clarification(self):
        case = next(
            item for item in self.cases if item["id"] == "known-capability-missing-parameters"
        )
        result = build_runtime("rule", "memory").run(case["input"])

        self.assertEqual(result.status.value, case["expected_status"])
        self.assertIsNone(result.plan)
        self.assertEqual(result.steps, [])
        self.assertEqual(
            result.clarification["state"], case["expected_clarification_state"]
        )
        self.assertEqual(
            result.clarification["matched_capabilities"],
            [case["expected_capability_id"]],
        )
        self.assertEqual(result.clarification["missing"], case["expected_missing"])

    def test_global_runner_keeps_clarification_case_executable_without_false_success(self):
        case = next(
            item for item in self.cases if item["id"] == "known-capability-missing-parameters"
        )
        report = run_global_cases([case], backend="memory")

        self.assertEqual(report["executed"], 1)
        self.assertEqual(report["failed"], 0)
        item = report["results"][0]
        self.assertEqual(item["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(item["actual_tools"], [])
        self.assertEqual(item["result_type"], "unknown")

    def test_region_comparison_contract_preserves_all_named_regions(self):
        case = next(item for item in self.cases if item["id"] == "region-comparison-contract")
        result = AgentService().compare_buildability_regions(
            **case["input"], backend=case["backend"]
        )

        self.assertEqual(result["scenario"]["operation"], "buildability_comparison")
        self.assertEqual(result["scenario"]["admin_names"], case["expected_admin_names"])
        self.assertEqual(result["scenario"]["thresholds"], [float(case["expected_threshold"])])
        self.assertEqual(result["admin_names"], case["expected_admin_names"])
        self.assertEqual(result["slope_limit_degrees"], float(case["expected_threshold"]))
        self.assertEqual(len(result["results"]), case["expected_row_count"])
        self.assertEqual(
            [row["admin_name"] for row in result["results"]],
            case["expected_admin_names"],
        )
        self.assertTrue(all(row["slope_limit_degrees"] == 20.0 for row in result["results"]))

    def test_matrix_contains_both_m66_e_contracts(self):
        ids = {case["id"] for case in self.cases}
        self.assertIn("known-capability-missing-parameters", ids)
        self.assertIn("region-comparison-contract", ids)


if __name__ == "__main__":
    unittest.main()
