import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.global_runner import run_global_cases
from evaluation.model_evaluation import (
    classify_provider_error,
    evaluate_plan_quality,
    evaluate_model_fixture,
    evaluate_model_replay_suite_file,
    load_model_fixture,
    sanitize_provider_metrics,
)
from evaluation.runner import load_cases


ROOT = Path(__file__).parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "m67_spatial_overview_model.json"


class M67ModelEvaluationTests(unittest.TestCase):
    def test_default_fixture_evaluates_offline_with_all_plan_quality_metrics(self):
        fixture = load_model_fixture(FIXTURE_PATH)

        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            report = evaluate_model_fixture(fixture)

        self.assertTrue(report["passed"])
        self.assertEqual(report["status"], "COMPLETED")
        self.assertTrue(report["plan_quality"]["tool_coverage"]["passed"])
        self.assertTrue(report["plan_quality"]["dependency_dag"]["passed"])
        self.assertTrue(report["plan_quality"]["result_type_match"]["passed"])
        self.assertTrue(report["plan_quality"]["workflow_template_match"]["passed"])
        self.assertIn(
            "spatial_overview",
            report["plan_quality"]["workflow_template_match"]["matched_template_ids"],
        )
        self.assertIn(
            "spatial_overview",
            report["plan_quality"]["workflow_template_match"]["exact_template_ids"],
        )
        self.assertTrue(report["plan_quality"]["chinese_answer"]["passed"])
        self.assertEqual(report["safety"]["provider_error"]["class"], "none")
        self.assertEqual(report["safety"]["token_usage"]["total_tokens"], 1440)
        self.assertGreaterEqual(report["safety"]["latency"]["latency_ms"], 0)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("api_key", encoded.lower())
        self.assertNotIn("sk-", encoded.lower())

    def test_global_runner_includes_offline_model_evaluation_by_default(self):
        cases = [
            case
            for case in load_cases(ROOT / "evaluation" / "cases" / "global-acceptance.json")
            if case.get("surface") == "runtime"
        ]

        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            report = run_global_cases(cases, planner="rule", backend="memory")

        self.assertIn("model_evaluation", report)
        self.assertTrue(report["model_evaluation"]["passed"])
        self.assertEqual(report["model_evaluation"]["execution_mode"], "offline_fixture")

    def test_global_runner_can_disable_model_fixture_without_network(self):
        cases = [
            {
                "id": "offline-greeting",
                "surface": "runtime",
                "input": "你好",
                "expected_status": "COMPLETED",
                "expected_result_type": "direct_answer",
                "expected_tools": [],
            }
        ]

        with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            report = run_global_cases(cases, planner="rule", backend="memory", model_fixture=None)

        self.assertNotIn("model_evaluation", report)
        self.assertEqual(report["failed"], 0)

    def test_invalid_dependency_graph_is_reported_without_running_tools(self):
        plan = {
            "steps": [
                {"id": "a", "tool": "first", "args": {}, "depends_on": ["b"]},
                {"id": "b", "tool": "second", "args": {}, "depends_on": ["a"]},
            ],
            "output": {"type": "demo_result"},
        }

        quality = evaluate_plan_quality(
            plan,
            expected_tools=["first", "second"],
            expected_result_type="demo_result",
            answer="这是中文答案。",
        )

        self.assertFalse(quality["dependency_dag"]["passed"])
        self.assertIn("cycle", quality["dependency_dag"]["issues"])
        self.assertFalse(quality["passed"])

    def test_tool_coverage_reports_missing_and_unexpected_occurrences(self):
        quality = evaluate_plan_quality(
            {
                "steps": [
                    {"id": "one", "tool": "schema", "args": {}, "depends_on": []},
                    {"id": "extra", "tool": "health", "args": {}, "depends_on": []},
                ],
                "output": {"type": "demo_result"},
            },
            expected_tools=["schema", "query"],
            expected_result_type="demo_result",
            answer="中文结果",
        )

        coverage = quality["tool_coverage"]
        self.assertEqual(coverage["covered_count"], 1)
        self.assertEqual(coverage["expected_count"], 2)
        self.assertEqual(coverage["missing"], ["query"])
        self.assertEqual(coverage["unexpected"], ["health"])
        self.assertFalse(coverage["passed"])

    def test_template_contract_reports_missing_result_references(self):
        fixture = load_model_fixture(FIXTURE_PATH)
        plan = copy.deepcopy(fixture["response"])
        for step in plan["steps"]:
            if step["id"] == "overview-elevation":
                step["args"]["admin_name"] = "洪山区"

        quality = evaluate_plan_quality(
            plan,
            expected_tools=fixture["expected"]["expected_tools"],
            expected_result_type=fixture["expected"]["expected_result_type"],
            expected_template_id="spatial_overview",
            answer="这是中文结果。",
        )

        template_match = quality["workflow_template_match"]
        self.assertFalse(template_match["passed"])
        self.assertIn("spatial_overview", template_match["matched_template_ids"])
        self.assertNotIn("spatial_overview", template_match["exact_template_ids"])
        self.assertIn(
            "blueprint_result_ref",
            template_match["issues"]["spatial_overview"],
        )

    def test_safe_metrics_and_provider_errors_are_allowlisted_and_classified(self):
        metrics = sanitize_provider_metrics(
            {
                "provider": "deepseek-compatible",
                "status": "error",
                "error_type": "http_error",
                "response_status": 503,
                "latency_ms": 12.34567,
                "attempts": 2,
                "retries": 1,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "secret": "sk-never-return-this",
                },
                "raw_error": "Authorization: Bearer sk-never-return-this",
            }
        )

        self.assertEqual(metrics["provider_error"]["class"], "transient_http")
        self.assertEqual(metrics["token_usage"]["total_tokens"], 120)
        self.assertEqual(metrics["latency"]["latency_ms"], 12.346)
        encoded = json.dumps(metrics, ensure_ascii=False)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("sk-never-return-this", encoded)
        self.assertEqual(classify_provider_error("http_error", 401), "authentication")
        self.assertEqual(classify_provider_error("timeout", None), "timeout")
        self.assertEqual(classify_provider_error("response_json_error", None), "invalid_response")

    def test_fixture_loader_returns_a_copy_and_rejects_private_fields(self):
        first = load_model_fixture(FIXTURE_PATH)
        second = copy.deepcopy(first)
        first["response"]["goal"] = "changed"
        self.assertNotEqual(first["response"]["goal"], second["response"]["goal"])
        self.assertNotIn("api_key", json.dumps(second).lower())

    def test_m69_replay_suite_covers_clarification_and_plan_repair(self):
        report = evaluate_model_replay_suite_file(
            ROOT / "tests" / "fixtures" / "m69_model_replay_suite.json"
        )
        self.assertEqual(report["passed"], 4)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(
            {item["replay_type"] for item in report["results"]},
            {"clarification_follow_up", "plan_repair", "open_region_query", "open_capability_query"},
        )
        self.assertEqual(
            {item["repair_count"] for item in report["results"]},
            {0, 1},
        )


if __name__ == "__main__":
    unittest.main()
