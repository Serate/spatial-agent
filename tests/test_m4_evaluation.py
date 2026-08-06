import json
import unittest
from pathlib import Path

from evaluation.runner import evaluate_case, load_cases, run_cases
from run_demo import build_runtime


ROOT = Path(__file__).parents[1]


class M4EvaluationTests(unittest.TestCase):
    def test_step_trace_includes_latency(self):
        result = build_runtime("rule").run("查询距离主干道500米以内、坡度超过25度的区域。")
        self.assertEqual(result.status.value, "COMPLETED")
        for step in result.steps:
            self.assertIsNotNone(step.started_at)
            self.assertIsNotNone(step.finished_at)
            self.assertIsNotNone(step.latency_ms)
            self.assertGreaterEqual(step.latency_ms, 0)

    def test_evaluate_case_checks_status_tools_and_step_limit(self):
        case = {
            "id": "case-1",
            "input": "查询距离主干道500米以内、坡度超过25度的区域。",
            "expected_tools": ["get_dataset_schema", "range_query", "spatial_join"],
            "max_steps": 8,
        }
        run = build_runtime("rule").run(case["input"])
        result = evaluate_case(run, case)
        self.assertTrue(result.status_match)
        self.assertTrue(result.tools_match)
        self.assertTrue(result.within_max_steps)

    def test_run_cases_summarizes_report(self):
        cases = load_cases(str(ROOT / "evaluation" / "cases" / "m0-cases.json"))
        report = run_cases(build_runtime("rule"), cases)
        self.assertEqual(report["total"], 5)
        self.assertIn("pass_rate", report)
        self.assertEqual(len(report["results"]), 5)
        self.assertGreaterEqual(report["status_match_rate"], 0.6)

    def test_report_is_json_serializable(self):
        cases = load_cases(str(ROOT / "evaluation" / "cases" / "m0-cases.json"))
        report = run_cases(build_runtime("rule"), cases)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertIn("tool_match_rate", encoded)
        self.assertIn("avg_total_latency_ms", report)
        self.assertIn("lineage_valid_rate", report)
        self.assertIn("total_tokens", report)
        self.assertIn("planner_error_type", encoded)


if __name__ == "__main__":
    unittest.main()
