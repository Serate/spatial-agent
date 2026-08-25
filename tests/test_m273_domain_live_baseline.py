import unittest

from agent.evidence_registry import build_evidence_registry
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from evaluation.live_baseline import run_live_baseline
from scripts.live_baseline import _case_requires_gis


class M273DomainLiveBaselineTests(unittest.TestCase):
    def test_local_gate_is_domain_aware(self):
        self.assertTrue(_case_requires_gis({"id": "legacy-gis"}))
        self.assertTrue(_case_requires_gis({"domain_id": "gis"}))
        self.assertFalse(_case_requires_gis({"domain_id": "economic"}))

    def test_case_domain_is_forwarded_to_generic_runtime_factory(self):
        plan = TaskPlan(
            "economic trend",
            [
                PlanStep("query", "economic_indicator_query", {}, []),
                PlanStep("evidence", "economic_source_evidence", {}, ["query"]),
            ],
            {"type": "economic_timeseries_result"},
        )
        result = AgentRunResult(
            run_id="run",
            status=RunStatus.COMPLETED,
            request="经济趋势",
            plan=plan,
            steps=[
                StepRun(item.id, item.tool, item.args, item.depends_on, status="COMPLETED")
                for item in plan.steps
            ],
            answer="经济趋势结果",
        )
        result.evidence_registry = build_evidence_registry({"result": result.to_dict()})
        calls = []

        def runtime_factory(planner, backend, **kwargs):
            calls.append((planner, backend, kwargs.get("domain_id")))
            return type("Runtime", (), {"run": lambda self, request, session_id: result})()

        report = run_live_baseline(
            runtime_factory=runtime_factory,
            snapshot_provider=lambda max_files: {},
            replay_evaluator=lambda fixture: {
                "failed": 0,
                "passed": 1,
                "evidence_registry_completeness": {"passed": True},
            },
            cases=[
                {
                    "id": "economic",
                    "request": "经济趋势",
                    "domain_id": "economic",
                    "expected_status": "COMPLETED",
                    "expected_tools": [
                        "economic_indicator_query",
                        "economic_source_evidence",
                    ],
                    "expected_result_type": "economic_timeseries_result",
                }
            ],
        )

        self.assertTrue(report["passed"])
        self.assertEqual(calls, [("openai", "local", "economic")])
        self.assertEqual(report["cases"][0]["domain_id"], "economic")


if __name__ == "__main__":
    unittest.main()
