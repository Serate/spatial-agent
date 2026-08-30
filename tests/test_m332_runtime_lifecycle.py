"""Compact M332 lifecycle and terminal-fence contracts."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.integration.model_evidence import project_model_evidence
from agent.models import PlanStep, RunStatus, TaskPlan
from agent.run_events import new_run_event
from agent.runtime import AgentRuntime
from agent.runtime_core.react_runtime import RuntimeReactExecution
from agent.service_state import ServiceState
from agent.tools import ToolRegistry


class _OneStepPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="完成一个受控步骤",
            steps=[PlanStep("only", "m332_echo", {}, [])],
        )


class _OneStepAdapter:
    def invoke(self, name, arguments):
        self.last_call = (name, arguments)
        return {"value": "ok"}


class M332RuntimeLifecycleTests(unittest.TestCase):
    def test_later_react_timeout_does_not_hide_successful_model_evidence(self):
        snapshots = iter(
            (
                {
                    "provider": "openai-compatible",
                    "model": "deepseek-v4-flash",
                    "execution_mode": "live_model",
                    "status": "success",
                    "attempts": 1,
                },
                {
                    "provider": "openai-compatible",
                    "model": "deepseek-v4-flash",
                    "execution_mode": "live_model",
                    "status": "error",
                    "error_type": "timeout",
                    "attempts": 1,
                },
            )
        )
        runtime = SimpleNamespace(_planner_metrics=lambda: next(snapshots))
        result = SimpleNamespace(planner_metrics=None)
        bridge = RuntimeReactExecution(runtime)

        bridge._record_planner_metrics(result)
        bridge._record_planner_metrics(result)

        self.assertEqual(result.planner_metrics["status"], "success")
        evidence = project_model_evidence(result.planner_metrics, {})
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["execution_mode"], "live_model")
        self.assertEqual(evidence["status"], "success")

    def test_completed_run_has_budget_and_terminal_lifecycle_event(self):
        adapter = _OneStepAdapter()
        registry = ToolRegistry(
            {
                "m332_echo": {
                    "name": "m332_echo",
                    "input_schema": {
                        "type": "object",
                        "additionalProperties": False,
                    },
                }
            },
            adapter,
        )
        runtime = AgentRuntime(_OneStepPlanner(), registry, max_retries=0)

        result = runtime.run("执行一个步骤")

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.budget_evidence["schema_version"], "spatial-agent.run-budget.v1")
        events = runtime._state_store.list_run_events(result.run_id, limit=100)
        self.assertIn("run_started", [item["kind"] for item in events])
        self.assertEqual(events[-1]["kind"], "run_completed")
        self.assertTrue(events[-1]["terminal"])

    def test_reaper_timeout_is_a_terminal_fence_for_late_events(self):
        state = ServiceState(runtime_factory=lambda _planner, _backend, **_kwargs: None)
        run_id = "m332-terminal-fence"
        state.submit_memory_job(
            "m332-terminal-key",
            {
                "run_id": run_id,
                "payload": {"request": "长任务", "session_id": "m332"},
                "status": "RUNNING",
                "created_at": 1.0,
                "started_at": 1.0,
                "last_event": "started",
            },
        )

        state.expire_job(run_id)
        snapshot = state.memory_terminal_run(run_id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.status, RunStatus.TIMED_OUT)

        late = state.append_run_event(
            new_run_event(
                run_id=run_id,
                phase="evidence",
                kind="run_completed",
                status="COMPLETED",
                message="迟到的成功",
                terminal=True,
            )
        )
        events = state.list_run_events(run_id, limit=100)
        self.assertEqual(late["kind"], "run_timed_out")
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["terminal"])


if __name__ == "__main__":
    unittest.main()
