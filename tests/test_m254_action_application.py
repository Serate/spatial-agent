import tempfile
import unittest

from agent.application.actions import ActionApplication
from agent.artifact_store import ArtifactStore


class _Observability:
    def __init__(self):
        self.events = []

    def emit_action(self, **event):
        self.events.append(event)


class _State:
    def __init__(self):
        self.observability = _Observability()


class _Runtime:
    domain_id = "demo"

    def __init__(self):
        self.calls = 0

    def capability_catalog(self):
        return {"domain_id": "demo"}

    def domain_actions(self):
        return {
            "actions": [
                {"id": "demo.echo", "result_type": "action_result"},
            ]
        }

    def result_registry(self):
        return None

    def execute_domain_action(self, action_id, payload, *, context=None):
        self.calls += 1
        return {"result_type": "action_result", "value": payload["value"]}


class M254ActionApplicationTests(unittest.TestCase):
    def test_idempotency_reuses_durable_action_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = _Runtime()
            app = ActionApplication(
                artifact_store=ArtifactStore(directory),
                state=_State(),
                runtime_provider=lambda planner, backend: runtime,
                runtime_context_provider=lambda planner, backend: {"domain_id": "demo"},
                domain_id_provider=lambda planner, backend: "demo",
                resolved_domain_id=lambda: "demo",
                action_context_provider=lambda: None,
                get_run_provider=lambda run_id, planner, backend: {},
                memory_result_provider=lambda run_id: None,
            )

            first = app.execute(
                "demo.echo", {"value": "ok"}, backend="memory", idempotency_key="echo-1"
            )
            replay = app.execute(
                "demo.echo", {"value": "ok"}, backend="memory", idempotency_key="echo-1"
            )

            self.assertFalse(first["idempotency_reused"])
            self.assertTrue(replay["idempotency_reused"])
            self.assertEqual(first["action_execution_id"], replay["action_execution_id"])
            self.assertEqual(runtime.calls, 1)

    def test_idempotency_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = _Runtime()
            app = ActionApplication(
                artifact_store=ArtifactStore(directory),
                state=_State(),
                runtime_provider=lambda planner, backend: runtime,
                runtime_context_provider=lambda planner, backend: {"domain_id": "demo"},
                domain_id_provider=lambda planner, backend: "demo",
                resolved_domain_id=lambda: "demo",
                action_context_provider=lambda: None,
                get_run_provider=lambda run_id, planner, backend: {},
                memory_result_provider=lambda run_id: None,
            )
            app.execute("demo.echo", {"value": "one"}, idempotency_key="echo-1")

            with self.assertRaisesRegex(ValueError, "idempotency_key conflicts"):
                app.execute("demo.echo", {"value": "two"}, idempotency_key="echo-1")


if __name__ == "__main__":
    unittest.main()
