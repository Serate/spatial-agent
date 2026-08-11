import unittest
from unittest.mock import patch

from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from evaluation.live_baseline import (
    _local_error_class,
    _safe_capability_snapshot,
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


class M76LiveBaselineTests(unittest.TestCase):
    def test_safe_snapshot_drops_machine_paths_and_private_provenance(self):
        snapshot = _safe_capability_snapshot(
            {
                "environment": "local",
                "health_status": "ready",
                "data_readiness": "ready",
                "config_path": "D:/private/config.json",
                "data_provenance": {"dem": {"path": "D:/private/dem.tif"}},
                "analysis_ready": {"status": "ready", "version": "analysis-ready-v1", "grid_alignment": "aligned"},
                "capabilities": [
                    {
                        "id": "spatial_overview",
                        "available": True,
                        "capability_status": "ready",
                        "dataset_gate": "ready",
                        "missing_datasets": [],
                    }
                ],
                "data_evidence": {"dem": {"status": "ready", "file_count": 2, "checked_files": 2}},
                "runtime": {"local_gis_backend": True, "geopandas": True, "rasterio": True},
            }
        )
        encoded = str(snapshot)
        self.assertNotIn("config_path", encoded)
        self.assertNotIn("private", encoded)
        self.assertEqual(snapshot["analysis_ready"]["grid_alignment"], "aligned")

    def test_local_error_class_separates_plan_gate_and_backend_failures(self):
        self.assertEqual(_local_error_class(_result("NEEDS_CLARIFICATION")), "clarification")
        self.assertEqual(_local_error_class(_result("FAILED")), "plan_validation")
        plan = TaskPlan("goal", [PlanStep("step", "tool", {}, [])], {"type": "x"})
        gate = StepRun("step", "tool", {}, status="FAILED", error="dataset unavailable")
        backend = StepRun("step", "tool", {}, status="FAILED", error="raster read failed")
        self.assertEqual(_local_error_class(_result("FAILED", plan=plan, steps=[gate])), "tool_gate")
        self.assertEqual(_local_error_class(_result("FAILED", plan=plan, steps=[backend])), "backend_execution")

    def test_baseline_aggregates_safe_metrics_and_replay(self):
        plan = TaskPlan(
            "空间总览",
            [
                PlanStep("health", "get_dataset_health_report", {"dataset": "all", "max_files": 10}, []),
                PlanStep("schema", "get_dataset_schema", {"dataset": "admin_areas"}, ["health"]),
                PlanStep("query", "range_query", {"dataset": "admin_areas", "conditions": [], "limit": 100}, ["schema"]),
                PlanStep("dem", "get_zonal_raster_statistics", {"dataset": "dem", "admin_name": "洪山区", "max_files": 10}, ["query"]),
                PlanStep("slope", "get_zonal_slope_statistics", {"admin_name": "洪山区", "max_files": 10}, ["dem"]),
                PlanStep("land", "get_zonal_land_use_distribution", {"admin_name": "洪山区", "max_files": 10}, ["dem"]),
                PlanStep("roads", "get_zonal_vector_summary", {"dataset": "roads", "admin_name": "洪山区", "max_files": 10}, ["query"]),
                PlanStep("water", "get_zonal_vector_summary", {"dataset": "water", "admin_name": "洪山区", "max_files": 10}, ["query"]),
            ],
            {"type": "spatial_overview_result"},
        )
        result = _result(
            "COMPLETED",
            metrics={"status": "success", "usage": {"total_tokens": 42}, "latency_ms": 12, "attempts": 1, "retries": 0},
            plan=plan,
            steps=[StepRun(item.id, item.tool, item.args, item.depends_on, status="COMPLETED") for item in plan.steps],
        )

        with patch("evaluation.live_baseline.runtime_capability_snapshot", return_value={
            "environment": "local", "health_status": "ready", "data_readiness": "ready",
            "capabilities": [{"id": "spatial_overview", "available": True, "capability_status": "ready", "dataset_gate": "ready", "missing_datasets": []}],
            "data_evidence": {}, "runtime": {},
        }):
            report = run_live_baseline(
                runtime_factory=lambda planner, backend: type("Runtime", (), {"run": lambda self, request, session_id: result})(),
                replay_evaluator=lambda fixture: {"failed": 0, "passed": 2},
                cases=[{"id": "overview", "request": "分析洪山区空间概况", "expected_status": "COMPLETED", "kind": "spatial_overview"}],
            )

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["token_usage"], 42)
        self.assertEqual(report["summary"]["error_classes"], {"none": 1})
        self.assertNotIn("error", report["cases"][0])


if __name__ == "__main__":
    unittest.main()
