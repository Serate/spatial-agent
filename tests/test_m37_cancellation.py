import threading
import time
import unittest

from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.tools import ToolRegistry
from agent.trace_formatter import format_trace


class BlockingPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="cancel a running plan",
            steps=[
                PlanStep("first", "blocking", {}, []),
                PlanStep("second", "after", {}, ["first"]),
            ],
        )


class BlockingAdapter:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def invoke(self, name, arguments):
        if name == "blocking":
            self.started.set()
            self.release.wait(timeout=5)
            return {"ok": True}
        return {"ok": True}


class M37CancellationTests(unittest.TestCase):
    def test_cancel_stops_before_next_step_and_preserves_completed_result(self):
        adapter = BlockingAdapter()
        registry = ToolRegistry(
            {
                name: {
                    "name": name,
                    "input_schema": {"type": "object", "additionalProperties": False},
                }
                for name in ("blocking", "after")
            },
            adapter,
        )
        runtime = AgentRuntime(BlockingPlanner(), registry, max_retries=0)
        holder = {}

        thread = threading.Thread(
            target=lambda: holder.setdefault("result", runtime.run("cancel")),
            daemon=True,
        )
        thread.start()
        self.assertTrue(adapter.started.wait(timeout=2))
        run_id = next(iter(runtime._state_store._runs))
        runtime.cancel(run_id)
        adapter.release.set()
        thread.join(timeout=3)

        result = holder["result"]
        self.assertEqual(result.status.value, "CANCELLED")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[1].status, "BLOCKED")
        self.assertTrue(any("Run cancelled" in line for line in format_trace(result)))

    def test_timeout_stops_at_next_step_boundary(self):
        adapter = BlockingAdapter()
        registry = ToolRegistry(
            {
                name: {
                    "name": name,
                    "input_schema": {"type": "object", "additionalProperties": False},
                }
                for name in ("blocking", "after")
            },
            adapter,
        )
        runtime = AgentRuntime(BlockingPlanner(), registry, max_retries=0)
        holder = {}
        thread = threading.Thread(
            target=lambda: holder.setdefault(
                "result", runtime.run("timeout", timeout_seconds=0.01)
            ),
            daemon=True,
        )
        thread.start()
        self.assertTrue(adapter.started.wait(timeout=2))
        time.sleep(0.03)
        adapter.release.set()
        thread.join(timeout=3)

        result = holder["result"]
        self.assertEqual(result.status.value, "TIMED_OUT")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[1].status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
