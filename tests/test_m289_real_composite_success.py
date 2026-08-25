import unittest

from evaluation.composite_planning_matrix import run_planning_outcome_matrix
from scripts.m289_real_composite_acceptance import run_prepared_acceptance


class M289PlanningOutcomeMatrixTests(unittest.TestCase):
    def test_matrix_keeps_success_clarification_rejection_and_run_gate(self):
        cases = [
            {"id": "success", "expected_status": "PLANNED"},
            {"id": "clarify", "expected_status": "NEEDS_CLARIFICATION"},
            {"id": "reject", "expected_status": "REJECTED"},
        ]

        def runner(case):
            status = {
                "success": "PLANNED",
                "clarify": "NEEDS_CLARIFICATION",
                "reject": "REJECTED",
            }[case["id"]]
            return {"status": status, "components": []}

        report = run_planning_outcome_matrix(cases, runner=runner)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["case_count"], 3)
        self.assertTrue(all(not item["execution_run_created"] for item in report["cases"]))
        self.assertNotIn("prompt", str(report).lower())

    def test_matrix_rejects_unexpected_execution_creation(self):
        report = run_planning_outcome_matrix(
            [{"id": "unsafe", "expected_status": "PLANNED"}],
            runner=lambda _case: {"status": "PLANNED", "run_id": "must-not-start"},
        )
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["cases"][0]["passed"])
        self.assertTrue(report["cases"][0]["execution_run_created"])

    def test_prepared_plan_is_reused_by_sync_and_async_entries(self):
        request = {
            "schema_version": "spatial-agent.composite-request.v1",
            "fingerprint": "m289-fingerprint",
            "components": [],
        }
        prepared = {
            "status": "PLANNED",
            "request": request,
            "components": [{"component_id": "space"}],
            "request_fingerprint": "m289-fingerprint",
            "planner_evidence": {
                "structured_output": {
                    "wire_api": "chat_completions",
                    "structured_mode": "json_schema",
                    "schema_enforced": True,
                    "source": "config",
                    "reason_code": "configured",
                }
            },
        }

        class Runs:
            def __init__(self):
                self.requests = []

            def run_with_planning(self, value, **kwargs):
                self.requests.append(value)
                return {
                    "status": "COMPLETED",
                    "run_id": "sync-1",
                    "result": {"type": "composite_result"},
                    "components": [{"component_id": "space", "state": "completed", "status": "COMPLETED"}],
                    "artifact_ref": "sync-artifact",
                }

            def submit_async_with_planning(self, value, **kwargs):
                self.requests.append(value)
                return {"status": "QUEUED", "run_id": "async-1"}

            def get_run(self, run_id):
                return {
                    "status": "COMPLETED",
                    "run_id": run_id,
                    "result": {"type": "composite_result"},
                    "components": [{"component_id": "space", "state": "completed", "status": "COMPLETED"}],
                    "artifact_ref": "async-artifact",
                }

        runs = Runs()
        report = run_prepared_acceptance(prepared, run_application=runs, timeout_seconds=1)
        self.assertTrue(report["passed"])
        self.assertEqual(runs.requests, [request, request])
        self.assertEqual(report["comparison"]["same_result_type"], True)


if __name__ == "__main__":
    unittest.main()
