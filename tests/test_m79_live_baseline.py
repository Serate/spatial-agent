import unittest
from unittest.mock import patch

from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.request_model import parse_spatial_request
from evaluation.live_baseline import (
    _capability_tools,
    _comparison_evidence,
    _constrained_matrix_evidence,
    _matrix_evidence,
    _run_comparison_case,
    _run_comparison_matrix_case,
    _run_constrained_matrix_case,
    run_live_baseline,
)


def _result(status, *, metrics=None, plan=None, steps=None, answer="中文结果"):
    return AgentRunResult(
        run_id="run",
        status=RunStatus(status),
        request="request",
        plan=plan,
        planner_metrics=metrics or {},
        steps=steps or [],
        answer=answer,
    )


def _buildability_plan(kind="buildability"):
    tool = (
        "get_zonal_buildability_analysis"
        if kind == "buildability"
        else "get_zonal_constrained_buildability_analysis"
    )
    result_type = (
        "buildability_result"
        if kind == "buildability"
        else "constrained_buildability_result"
    )
    return TaskPlan(
        "筛选建设候选",
        [
            PlanStep("health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}, []),
            PlanStep("screening", tool, {"admin_name": "洪山区", "slope_limit_degrees": 15.0, "max_files": 10}, ["health"]),
        ],
        {"type": result_type},
    )


class M79LiveBaselineExtensionTests(unittest.TestCase):
    def test_capability_tools_fallback_for_buildability(self):
        self.assertEqual(
            _capability_tools({}, "buildability_screening"),
            ["get_dataset_health_report", "get_zonal_buildability_analysis"],
        )
        self.assertEqual(
            _capability_tools({}, "constrained_buildability_screening"),
            ["get_dataset_health_report", "get_zonal_constrained_buildability_analysis"],
        )

    def test_capability_tools_prefers_snapshot_entries(self):
        snapshot = {
            "capabilities": [
                {"id": "buildability_screening", "tools": ["a", "b"]},
            ]
        }
        self.assertEqual(_capability_tools(snapshot, "buildability_screening"), ["a", "b"])

    def test_buildability_kind_plans_and_quality(self):
        plan = _buildability_plan("buildability")
        result = _result(
            "COMPLETED",
            metrics={"status": "success", "usage": {"total_tokens": 30}, "latency_ms": 8, "attempts": 1, "retries": 0},
            plan=plan,
            steps=[StepRun(item.id, item.tool, item.args, item.depends_on, status="COMPLETED") for item in plan.steps],
        )
        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [], "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: result})(),
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 2, "evidence_registry_completeness": {"passed": True}},
                cases=[{"id": "buildability", "request": "筛选洪山区坡度不超过15度的建设候选区域", "expected_status": "COMPLETED", "kind": "buildability"}],
            )
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["token_usage"], 30)
        self.assertEqual(report["cases"][0]["result_type"], "buildability_result")
        self.assertIn("get_zonal_buildability_analysis", report["cases"][0]["actual_tools"])

    def test_constrained_buildability_kind(self):
        plan = _buildability_plan("constrained_buildability")
        result = _result(
            "COMPLETED",
            metrics={"status": "success", "usage": {"total_tokens": 44}, "latency_ms": 9, "attempts": 1, "retries": 0},
            plan=plan,
            steps=[StepRun(item.id, item.tool, item.args, item.depends_on, status="COMPLETED") for item in plan.steps],
        )
        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [], "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: result})(),
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 2, "evidence_registry_completeness": {"passed": True}},
                cases=[{"id": "constrained", "request": "筛选洪山区坡度不超过15度、距道路1000米内、排除水体的建设候选区域", "expected_status": "COMPLETED", "kind": "constrained_buildability"}],
            )
        self.assertTrue(report["passed"])
        self.assertEqual(report["cases"][0]["result_type"], "constrained_buildability_result")
        self.assertIn("get_zonal_constrained_buildability_analysis", report["cases"][0]["actual_tools"])

    def test_explicit_case_contract_checks_tools_and_result_type(self):
        plan = TaskPlan(
            "组合分析",
            [
                PlanStep("first", "tool_a", {}, []),
                PlanStep("second", "tool_b", {}, ["first"]),
            ],
            {"type": "composed_result"},
        )
        result = _result(
            "COMPLETED",
            metrics={"status": "success", "usage": {"total_tokens": 12}, "latency_ms": 4, "attempts": 1, "retries": 0},
            plan=plan,
            steps=[StepRun(item.id, item.tool, item.args, item.depends_on, status="COMPLETED") for item in plan.steps],
        )
        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [], "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: result})(),
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 4, "evidence_registry_completeness": {"passed": True}},
                cases=[{
                    "id": "explicit-composed",
                    "request": "组合分析",
                    "expected_status": "COMPLETED",
                    "expected_tools": ["tool_a", "tool_b"],
                    "expected_result_type": "composed_result",
                }],
            )
        self.assertTrue(report["passed"])
        self.assertTrue(report["cases"][0]["plan_quality"]["passed"])

    def test_region_comparison_case_requires_service(self):
        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [], "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: None})(),
                service_factory=None,
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 2, "evidence_registry_completeness": {"passed": True}},
                cases=[{"id": "comparison", "request": {"admin_names": ["洪山区", "江夏区"], "threshold": 15}, "expected_status": "COMPLETED", "kind": "region_comparison"}],
            )
        self.assertFalse(report["passed"])
        self.assertEqual(report["cases"][0]["status"], "SKIPPED")
        self.assertEqual(report["cases"][0]["error_class"], "service_unavailable")

    def test_region_comparison_evidence_aggregates_rows(self):
        result = {
            "admin_names": ["洪山区", "江夏区"],
            "slope_limit_degrees": 15,
            "results": [
                {
                    "admin_name": "洪山区",
                    "status": "COMPLETED",
                    "candidate_pixel_count": 100,
                    "candidate_ratio": 0.25,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 20}, "latency_ms": 5, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
                {
                    "admin_name": "江夏区",
                    "status": "COMPLETED",
                    "candidate_pixel_count": 60,
                    "candidate_ratio": 0.2,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 22}, "latency_ms": 7, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
            ],
        }
        evidence = _comparison_evidence(result, {"id": "comparison"}, 1)
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["metrics"]["token_usage"]["total_tokens"], 42)
        self.assertEqual(evidence["metrics"]["latency"]["latency_ms"], 6.0)
        self.assertEqual(len(evidence["rows"]), 2)
        self.assertEqual(evidence["result_type"], "buildability_comparison")

    def test_region_comparison_case_via_service(self):
        class FakeService:
            def compare_buildability_regions(self, admin_names, threshold, planner, backend):
                return {
                    "admin_names": admin_names,
                    "slope_limit_degrees": threshold,
                    "results": [
                        {
                            "admin_name": name,
                            "status": "COMPLETED",
                            "candidate_pixel_count": 100,
                            "candidate_ratio": 0.25,
                            "planner_metrics": {"status": "success", "usage": {"total_tokens": 10}, "latency_ms": 4, "attempts": 1, "retries": 0},
                            "actual_tools": ["get_zonal_buildability_analysis"],
                            "failed_steps": [],
                        }
                        for name in admin_names
                    ],
                }

        evidence = _run_comparison_case(
            FakeService(),
            {"id": "comparison", "request": {"admin_names": ["洪山区", "江夏区"], "threshold": 15}, "expected_status": "COMPLETED", "kind": "region_comparison"},
            {},
            backend="memory",
            attempts_per_case=2,
        )
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["status"], "COMPLETED")
        self.assertEqual(len(evidence["rows"]), 2)

    def test_admin_prefix_strips_screening_verb(self):
        parsed = parse_spatial_request("筛选洪山区坡度不超过15度的建设候选区域")
        self.assertEqual(parsed.admin_name, "洪山区")
        self.assertIn("buildability", parsed.tasks)
        self.assertEqual(parsed.constraints.get("slope_max"), 15.0)

    def test_admin_prefix_strips_screening_verb_with_water(self):
        parsed = parse_spatial_request(
            "筛选洪山区坡度不超过15度、距道路1000米内、排除水体的建设候选区域"
        )
        self.assertEqual(parsed.admin_name, "洪山区")
        self.assertIn("water", parsed.tasks)
        self.assertEqual(parsed.constraints.get("road_distance_max"), 1000.0)
        self.assertTrue(parsed.constraints.get("exclude_water"))

    def test_admin_parsing_keeps_plain_overview(self):
        parsed = parse_spatial_request("分析洪山区空间概况")
        self.assertEqual(parsed.admin_name, "洪山区")

    def test_comparison_matrix_evidence_asserts_monotonic_ratio(self):
        by_region = {
            "洪山区": [
                {
                    "admin_name": "洪山区",
                    "slope_limit_degrees": 10,
                    "status": "COMPLETED",
                    "candidate_pixel_count": 100,
                    "candidate_ratio": 0.1,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 10}, "latency_ms": 4, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
                {
                    "admin_name": "洪山区",
                    "slope_limit_degrees": 20,
                    "status": "COMPLETED",
                    "candidate_pixel_count": 150,
                    "candidate_ratio": 0.15,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 11}, "latency_ms": 5, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
            ],
            "江夏区": [
                {
                    "admin_name": "江夏区",
                    "slope_limit_degrees": 10,
                    "status": "COMPLETED",
                    "candidate_pixel_count": 60,
                    "candidate_ratio": 0.05,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 9}, "latency_ms": 3, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
                {
                    "admin_name": "江夏区",
                    "slope_limit_degrees": 20,
                    "status": "COMPLETED",
                    "candidate_pixel_count": 90,
                    "candidate_ratio": 0.08,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 12}, "latency_ms": 6, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_buildability_analysis"],
                    "failed_steps": [],
                },
            ],
        }
        evidence = _matrix_evidence(by_region, {"id": "matrix"}, 1)
        self.assertTrue(evidence["passed"])
        self.assertTrue(evidence["monotonic_ratio"])
        self.assertEqual(evidence["metrics"]["token_usage"]["total_tokens"], 42)
        self.assertEqual(len(evidence["regions"]), 2)

    def test_comparison_matrix_evidence_fails_on_non_monotonic(self):
        by_region = {
            "洪山区": [
                {
                    "admin_name": "洪山区",
                    "slope_limit_degrees": 10,
                    "status": "COMPLETED",
                    "candidate_ratio": 0.2,
                },
                {
                    "admin_name": "洪山区",
                    "slope_limit_degrees": 20,
                    "status": "COMPLETED",
                    "candidate_ratio": 0.1,
                },
            ],
        }
        evidence = _matrix_evidence(by_region, {"id": "matrix"}, 1)
        self.assertFalse(evidence["passed"])
        self.assertFalse(evidence["monotonic_ratio"])
        self.assertEqual(evidence["error_class"], "monotonicity")

    def test_comparison_matrix_case_via_service(self):
        class FakeService:
            def compare_buildability(self, admin_name, thresholds, planner, backend):
                return {
                    "admin_name": admin_name,
                    "thresholds": list(thresholds),
                    "results": [
                        {
                            "admin_name": admin_name,
                            "slope_limit_degrees": threshold,
                            "status": "COMPLETED",
                            "candidate_pixel_count": 100 + int(threshold),
                            "candidate_ratio": 0.1 + threshold / 1000,
                            "planner_metrics": {"status": "success", "usage": {"total_tokens": 5}, "latency_ms": 2, "attempts": 1, "retries": 0},
                            "actual_tools": ["get_zonal_buildability_analysis"],
                            "failed_steps": [],
                        }
                        for threshold in thresholds
                    ],
                }

        evidence = _run_comparison_matrix_case(
            FakeService(),
            {"id": "matrix", "request": {"admin_names": ["洪山区", "江夏区"], "thresholds": [10, 20]}, "expected_status": "COMPLETED", "kind": "comparison_matrix"},
            backend="memory",
            attempts_per_case=2,
        )
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["status"], "COMPLETED")
        self.assertTrue(evidence["monotonic_ratio"])
        self.assertEqual(len(evidence["regions"]), 2)

    def test_constrained_matrix_evidence_asserts_monotonic_eligible(self):
        by_region = {
            "洪山区": [
                {
                    "admin_name": "洪山区",
                    "road_distance_m": 200.0,
                    "status": "COMPLETED",
                    "candidate_features": 200,
                    "eligible_features": 100,
                    "water_excluded_features": 14,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 10}, "latency_ms": 4, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_constrained_buildability_analysis"],
                    "failed_steps": [],
                },
                {
                    "admin_name": "洪山区",
                    "road_distance_m": 500.0,
                    "status": "COMPLETED",
                    "candidate_features": 200,
                    "eligible_features": 150,
                    "water_excluded_features": 14,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 11}, "latency_ms": 5, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_constrained_buildability_analysis"],
                    "failed_steps": [],
                },
            ],
            "江夏区": [
                {
                    "admin_name": "江夏区",
                    "road_distance_m": 200.0,
                    "status": "COMPLETED",
                    "candidate_features": 300,
                    "eligible_features": 80,
                    "water_excluded_features": 6,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 9}, "latency_ms": 3, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_constrained_buildability_analysis"],
                    "failed_steps": [],
                },
                {
                    "admin_name": "江夏区",
                    "road_distance_m": 500.0,
                    "status": "COMPLETED",
                    "candidate_features": 300,
                    "eligible_features": 90,
                    "water_excluded_features": 6,
                    "planner_metrics": {"status": "success", "usage": {"total_tokens": 12}, "latency_ms": 6, "attempts": 1, "retries": 0},
                    "actual_tools": ["get_zonal_constrained_buildability_analysis"],
                    "failed_steps": [],
                },
            ],
        }
        evidence = _constrained_matrix_evidence(by_region, {"id": "constrained-matrix"}, 1)
        self.assertTrue(evidence["passed"])
        self.assertTrue(evidence["monotonic_eligible_features"])
        self.assertEqual(evidence["metrics"]["token_usage"]["total_tokens"], 42)
        self.assertEqual(len(evidence["regions"]), 2)
        self.assertEqual(evidence["result_type"], "constrained_buildability_comparison")

    def test_constrained_matrix_evidence_fails_on_non_monotonic(self):
        by_region = {
            "洪山区": [
                {
                    "admin_name": "洪山区",
                    "road_distance_m": 200.0,
                    "status": "COMPLETED",
                    "eligible_features": 150,
                },
                {
                    "admin_name": "洪山区",
                    "road_distance_m": 500.0,
                    "status": "COMPLETED",
                    "eligible_features": 100,
                },
            ],
        }
        evidence = _constrained_matrix_evidence(by_region, {"id": "constrained-matrix"}, 1)
        self.assertFalse(evidence["passed"])
        self.assertFalse(evidence["monotonic_eligible_features"])
        self.assertEqual(evidence["error_class"], "monotonicity")

    def test_constrained_matrix_case_via_service(self):
        class FakeService:
            def compare_constrained_buildability(self, admin_name, road_distances, slope_limit_degrees, planner, backend):
                return {
                    "admin_name": admin_name,
                    "slope_limit_degrees": slope_limit_degrees,
                    "road_distances": list(road_distances),
                    "results": [
                        {
                            "admin_name": admin_name,
                            "road_distance_m": distance,
                            "status": "COMPLETED",
                            "candidate_features": 200,
                            "eligible_features": 100 + int(distance) // 10,
                            "water_excluded_features": 14,
                            "planner_metrics": {"status": "success", "usage": {"total_tokens": 5}, "latency_ms": 2, "attempts": 1, "retries": 0},
                            "actual_tools": ["get_zonal_constrained_buildability_analysis"],
                            "failed_steps": [],
                        }
                        for distance in road_distances
                    ],
                }

        evidence = _run_constrained_matrix_case(
            FakeService(),
            {"id": "constrained-matrix", "request": {"admin_names": ["洪山区", "江夏区"], "road_distances": [200, 500], "slope_limit_degrees": 15}, "expected_status": "COMPLETED", "kind": "constrained_matrix"},
            backend="memory",
            attempts_per_case=2,
        )
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["status"], "COMPLETED")
        self.assertTrue(evidence["monotonic_eligible_features"])
        self.assertEqual(len(evidence["regions"]), 2)

    def test_constrained_matrix_case_requires_service(self):
        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [], "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: None})(),
                service_factory=None,
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 2, "evidence_registry_completeness": {"passed": True}},
                cases=[{"id": "constrained-matrix", "request": {"admin_names": ["洪山区", "江夏区"], "road_distances": [200, 500]}, "expected_status": "COMPLETED", "kind": "constrained_matrix"}],
            )
        self.assertFalse(report["passed"])
        self.assertEqual(report["cases"][0]["status"], "SKIPPED")
        self.assertEqual(report["cases"][0]["error_class"], "service_unavailable")


if __name__ == "__main__":
    unittest.main()
