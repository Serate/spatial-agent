import json
import os
import unittest

from agent.memory import FactMemory
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.observability import (
    CollectingEmitter,
    ObservabilityEmitter,
    observability_enabled,
)
from agent.runtime import AgentRuntime, InMemoryConversationStore, InMemoryStateStore
from agent.tools import ToolRegistry


class MemoryPlanner:
    def plan(self, request, context=None):
        return TaskPlan(
            "stub",
            [
                PlanStep("first", "make_value", {}, []),
                PlanStep("second", "use_value", {}, ["first"]),
            ],
            {"type": "buildability_result"},
        )


class ToolAdapter:
    def invoke(self, name, arguments):
        if name == "make_value":
            return {"value": 1}
        if name == "use_value":
            return {"ok": True}
        raise AssertionError("unexpected tool: " + name)


def stub_registry():
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
        }
        for name in ("make_value", "use_value")
    }
    return ToolRegistry(definitions, ToolAdapter())


class M80ObservabilityUnitTests(unittest.TestCase):
    def test_enabled_by_default_and_switchable(self):
        os.environ.pop("SPATIAL_AGENT_OBSERVABILITY", None)
        self.assertTrue(observability_enabled())
        os.environ["SPATIAL_AGENT_OBSERVABILITY"] = "0"
        try:
            self.assertFalse(observability_enabled())
        finally:
            os.environ.pop("SPATIAL_AGENT_OBSERVABILITY", None)

    def test_run_event_is_credential_free_json(self):
        emitter = CollectingEmitter()
        emitter.emit_run(
            run_id="run-abc",
            session_id="conv-1",
            name="RuleBasedPlanner:buildability_result",
            status="COMPLETED",
            duration_ms=12.5,
            attributes={
                "session_id": "conv-1",
                "result_type": "buildability_result",
                "error_category": None,
                "replan_count": 1,
                "secret_key": "should-not-appear",
            },
        )
        self.assertEqual(len(emitter.events), 1)
        event = emitter.events[0]
        self.assertEqual(event["schema_version"], "spatial-agent.observability.v1")
        self.assertEqual(event["event"], "run")
        self.assertEqual(event["trace_id"], "run-abc")
        self.assertEqual(event["name"], "RuleBasedPlanner:buildability_result")
        self.assertEqual(event["status"], "COMPLETED")
        self.assertEqual(event["duration_ms"], 12.5)
        self.assertIn("session_id", event)
        self.assertNotIn("secret_key", event.get("attributes", {}))
        self.assertNotIn("error_category", event.get("attributes", {}))

    def test_step_event_has_parent_span(self):
        emitter = CollectingEmitter()
        emitter.emit_run(
            run_id="run-1", session_id=None, name="planner:type", status="COMPLETED", duration_ms=1.0
        )
        emitter.emit_step(
            run_id="run-1",
            parent_span_id="parent-123",
            name="make_value",
            status="COMPLETED",
            duration_ms=3.0,
            attributes={"attempts": 1, "error_category": None, "password": "secret"},
        )
        step = [event for event in emitter.events if event["event"] == "step"][0]
        self.assertEqual(step["parent_span_id"], "parent-123")
        self.assertEqual(step["name"], "make_value")
        self.assertEqual(step["attributes"]["attempts"], 1)
        self.assertNotIn("password", step["attributes"])

    def test_disabled_emits_nothing(self):
        emitter = CollectingEmitter(enabled=False)
        emitter.emit_run(
            run_id="r", session_id=None, name="x", status="COMPLETED", duration_ms=None
        )
        self.assertEqual(emitter.events, [])
        self.assertEqual(emitter.event_count, 0)


class M80ObservabilityRuntimeTests(unittest.TestCase):
    def test_runtime_emits_run_and_step_events(self):
        emitter = CollectingEmitter()
        runtime = AgentRuntime(
            MemoryPlanner(),
            stub_registry(),
            state_store=InMemoryStateStore(),
            conversation_store=InMemoryConversationStore(),
            memory=FactMemory(),
            observability=emitter,
        )
        result = runtime.run("analyze", session_id="conv-obs")
        self.assertEqual(result.status, RunStatus.COMPLETED)
        kinds = [event["event"] for event in emitter.events]
        self.assertIn("run", kinds)
        self.assertIn("step", kinds)
        run_events = [event for event in emitter.events if event["event"] == "run"]
        self.assertEqual(len(run_events), 1)
        self.assertEqual(run_events[0]["trace_id"], result.run_id)
        # Step events share the run's trace id and reference its span as parent.
        step_events = [event for event in emitter.events if event["event"] == "step"]
        self.assertEqual(len(step_events), 2)
        run_span = run_events[0]["span_id"]
        for step in step_events:
            self.assertEqual(step["trace_id"], result.run_id)
            self.assertEqual(step["parent_span_id"], run_span)


if __name__ == "__main__":
    unittest.main()
