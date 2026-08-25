import time
import unittest
from threading import Event

from agent.evidence_registry import build_evidence_registry
from agent.models import AgentRunResult, RunStatus
from evaluation.live_baseline import run_live_baseline


def _replay():
    return {
        "failed": 0,
        "passed": 1,
        "evidence_registry_completeness": {"passed": True},
    }


class M270LiveHarnessTests(unittest.TestCase):
    def test_success_keeps_live_baseline_contract_and_emits_safe_events(self):
        events = []
        result = AgentRunResult(
            run_id="run",
            status=RunStatus.COMPLETED,
            request="安全测试请求",
            answer="中文结果",
        )
        result.evidence_registry = build_evidence_registry({"result": result.to_dict()})

        report = run_live_baseline(
            runtime_factory=lambda planner, backend: type(
                "Runtime", (), {"run": lambda self, request, session_id: result}
            )(),
            replay_evaluator=lambda fixture: _replay(),
            snapshot_provider=lambda max_files: {},
            cases=[
                {
                    "id": "fake-success",
                    "request": "请求中不应进入 progress event 的密钥 sk-test-secret",
                    "expected_status": "COMPLETED",
                }
            ],
            deadline_seconds=1,
            heartbeat_seconds=0.01,
            progress_callback=events.append,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual([event["event"] for event in events], ["started", "completed"])
        for event in events:
            self.assertEqual(
                set(event), {"event", "case_id", "phase", "status", "elapsed_ms"}
            )
            encoded = repr(event)
            self.assertNotIn("sk-test-secret", encoded)
            self.assertNotIn("安全测试请求", encoded)

    def test_blocking_provider_returns_timeout_within_deadline(self):
        events = []
        blocked = Event()

        def runtime_factory(planner, backend):
            return type(
                "Runtime",
                (),
                {"run": lambda self, request, session_id: blocked.wait()},
            )()

        started = time.monotonic()
        report = run_live_baseline(
            runtime_factory=runtime_factory,
            replay_evaluator=lambda fixture: _replay(),
            snapshot_provider=lambda max_files: {},
            cases=[
                {
                    "id": "fake-blocked",
                    "request": "不会输出的 prompt sk-blocked-secret",
                    "expected_status": "COMPLETED",
                }
            ],
            deadline_seconds=0.06,
            heartbeat_seconds=0.01,
            progress_callback=events.append,
        )
        elapsed = time.monotonic() - started

        case = report["cases"][0]
        self.assertFalse(report["passed"])
        self.assertEqual(case["error_class"], "timeout")
        self.assertTrue(case["deadline_exceeded"])
        self.assertLess(elapsed, 0.5)
        self.assertIn("heartbeat", [event["event"] for event in events])
        self.assertEqual(events[-1]["event"], "timeout")

    def test_invalid_deadline_and_heartbeat_are_rejected(self):
        with self.assertRaises(ValueError):
            run_live_baseline(deadline_seconds=0, snapshot_provider=lambda max_files: {})
        with self.assertRaises(ValueError):
            run_live_baseline(heartbeat_seconds=0, snapshot_provider=lambda max_files: {})


if __name__ == "__main__":
    unittest.main()
