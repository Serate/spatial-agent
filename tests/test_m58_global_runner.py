import unittest
import time
from pathlib import Path

from evaluation.global_runner import run_global_cases
from evaluation.runner import load_cases
from agent.service import AgentService


class M58GlobalRunnerTests(unittest.TestCase):
    def test_global_runner_executes_supported_cases_and_marks_optional_cases(self):
        root = Path(__file__).parents[1]
        report = run_global_cases(
            load_cases(str(root / "evaluation" / "cases" / "global-acceptance.json")),
            backend="memory",
        )
        self.assertEqual(report["total"], 10)
        self.assertGreaterEqual(report["executed"], 7)
        self.assertGreaterEqual(report["skipped"], 2)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["evaluation_context"]["environment"], "memory")
        self.assertTrue(any(item.get("status") == "SKIPPED" for item in report["results"]))
        executed = [item for item in report["results"] if not item.get("skipped")]
        self.assertTrue(all(item.get("capability_contract_match", True) for item in executed))
        buildability = next(item for item in executed if item.get("case_id") == "threshold-comparison")
        self.assertFalse(buildability["capability_environment_supported"])
        self.assertEqual(buildability["execution_claim"], "contract_only_or_environment_mismatch")

    def test_async_snapshot_is_readable_after_service_recreation(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "production.db")
            first = AgentService(state_db_path=path)
            queued = first.run_async(
                request="查询DEM栅格元数据",
                session_id="restart-async",
                planner="rule",
                backend="memory",
            )
            snapshot = None
            for _ in range(60):
                try:
                    snapshot = first.get_run(queued["run_id"])
                except ValueError:
                    pass
                if snapshot and snapshot["status"] not in {"PLANNING", "EXECUTING"}:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(snapshot)
            restored = AgentService(state_db_path=path).get_run(queued["run_id"])
            self.assertEqual(restored["status"], "COMPLETED")
            self.assertEqual(restored["run_id"], queued["run_id"])
            self.assertEqual(restored["result"]["geometry"]["status"], "unknown")
            self.assertTrue(restored["result"]["data"]["evidence_steps"])


if __name__ == "__main__":
    unittest.main()
