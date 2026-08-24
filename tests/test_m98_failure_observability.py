import time
import unittest
from pathlib import Path

from tests.console_source import read_console_source
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.failure_contract import FAILURE_SCHEMA_VERSION, build_failure_evidence
from agent.models import AgentRunResult, RunStatus
from agent.observability import CollectingEmitter
from agent.runtime import AgentRuntime
from agent.service import AgentService
from tests.test_m80_observability import MemoryPlanner, stub_registry


class M98FailureObservabilityTests(unittest.TestCase):
    def test_run_trace_consumes_failure_code_phase_and_retryability(self):
        emitter = CollectingEmitter()
        runtime = AgentRuntime(
            MemoryPlanner(),
            stub_registry(),
            observability=emitter,
        )
        result = AgentRunResult(
            run_id="failure-trace",
            status=RunStatus.FAILED,
            request="失败回放",
            session_id="trace-session",
            error="provider failed",
            error_category="provider",
            error_code="upstream_timeout",
            failure=build_failure_evidence(
                status="FAILED",
                category="provider",
                code="upstream_timeout",
                phase="execution",
                retryable=True,
            ),
        )
        runtime._run_span_ids[result.run_id] = "run-span"
        runtime._emit_run_event(result)

        event = emitter.events[0]
        self.assertEqual(event["attributes"]["error_code"], "upstream_timeout")
        self.assertEqual(event["attributes"]["failure_phase"], "execution")
        self.assertTrue(event["attributes"]["failure_retryable"])
        self.assertNotIn("provider failed", str(event))

    def test_async_worker_exception_persists_failure_evidence(self):
        with TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(Path(directory) / "state.db"))
            with patch.object(service, "run", side_effect=RuntimeError("worker crashed")):
                queued = service.run_async(
                    request="你好", session_id="async-failure", planner="rule"
                )
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    job = service._state_store.get_async_job(queued["run_id"])
                    if job and job["status"] == "FAILED":
                        break
                    time.sleep(0.01)
            detail = service.get_run(queued["run_id"], planner="rule", backend="memory")

        self.assertEqual(detail["status"], "FAILED")
        self.assertEqual(detail["failure"]["schema_version"], FAILURE_SCHEMA_VERSION)
        self.assertEqual(detail["failure"]["phase"], "execution")
        self.assertEqual(detail["result"]["failure"], detail["failure"])

    def test_console_renders_versioned_failure_evidence(self):
        html = read_console_source(Path(__file__).parents[1])
        self.assertIn("function failureEvidenceBadge(failure)", html)
        self.assertIn("failure-evidence", html)
        self.assertIn("failure.schema_version", html)


if __name__ == "__main__":
    unittest.main()
