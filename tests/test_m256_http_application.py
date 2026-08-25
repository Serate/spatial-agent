import unittest

from agent.application.http import HTTPApplication


class _Service:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(("run", kwargs))
        return kwargs

    def run_async(self, **kwargs):
        self.calls.append(("run_async", kwargs))
        return kwargs

    def clear_session(self, session_id):
        self.calls.append(("clear", session_id))
        return {"session_id": session_id, "cleared_runs": 1}

    def workflow_contract(self, **kwargs):
        self.calls.append(("workflow_contract", kwargs))
        return {"catalog": {}, "known_tools": [], "known_result_types": []}

    def capabilities(self, **kwargs):
        self.calls.append(("capabilities", kwargs))
        return {"domain_id": "test", "capabilities": []}

    def list_runs(self, **kwargs):
        self.calls.append(("list_runs", kwargs))
        return {"runs": []}

    def get_run(self, run_id, **kwargs):
        self.calls.append(("get_run", run_id, kwargs))
        return {"run_id": run_id}

    def metrics(self):
        self.calls.append(("metrics", {}))
        return {"ok": True}


class _Routing:
    def __init__(self):
        self.calls = []

    def run(self, payload):
        self.calls.append(("run", payload))
        return {"status": "QUEUED"}


class _Composite:
    def __init__(self):
        self.calls = []

    def run(self, payload, *, session_id):
        self.calls.append((payload, session_id))
        return {"status": "COMPLETED", "session_id": session_id}


class M256HTTPApplicationTests(unittest.TestCase):
    def test_run_and_async_share_one_payload_projection(self):
        service = _Service()
        application = HTTPApplication(service)
        payload = {
            "request": "查询指标",
            "session_id": "m256",
            "planner": "rule",
            "backend": "local",
            "export_artifact": True,
            "idempotency_key": "m256-key",
        }

        run = application.execute("run", payload)
        queued = application.execute("run_async", payload)

        self.assertEqual(run["backend"], "local")
        self.assertTrue(run["export_artifact"])
        self.assertEqual(queued["idempotency_key"], "m256-key")
        self.assertEqual([item[0] for item in service.calls], ["run", "run_async"])

    def test_session_cleanup_and_routing_are_application_commands(self):
        service = _Service()
        routing = _Routing()
        cleared = []
        application = HTTPApplication(
            service,
            routing=routing,
            on_session_clear=lambda session_id: cleared.append(session_id),
        )

        result = application.execute("session_clear", {}, run_id="session-1")
        auto = application.execute("run_auto", {"request": "自动选择领域"})

        self.assertEqual(result["cleared_runs"], 1)
        self.assertEqual(cleared, ["session-1"])
        self.assertEqual(auto["status"], "QUEUED")
        self.assertEqual(routing.calls[0][0], "run")

    def test_unknown_command_fails_before_service_call(self):
        service = _Service()
        application = HTTPApplication(service)

        with self.assertRaisesRegex(ValueError, "unknown action"):
            application.execute("not-a-route", {})
        self.assertEqual(service.calls, [])

    def test_read_dispatch_keeps_resource_and_query_projection_in_one_seam(self):
        service = _Service()
        application = HTTPApplication(service)

        capabilities = application.read(
            "capabilities", {"planner": "llm", "backend": "local"}
        )
        runs = application.read("runs", {"limit": 7})
        run = application.read(
            "run", {"planner": "rule", "backend": "memory"}, resource_id="run-7"
        )
        metrics = application.read("metrics")

        self.assertEqual(capabilities["domain_id"], "test")
        self.assertEqual(runs, {"runs": []})
        self.assertEqual(run["run_id"], "run-7")
        self.assertTrue(metrics["ok"])
        self.assertEqual(
            [item[0] for item in service.calls],
            ["capabilities", "list_runs", "get_run", "metrics"],
        )

    def test_read_requires_resource_identifiers(self):
        application = HTTPApplication(_Service())

        with self.assertRaisesRegex(ValueError, "run_id"):
            application.read("run")

    def test_composite_run_is_a_shared_application_command(self):
        composite = _Composite()
        application = HTTPApplication(_Service(), composite=composite)
        result = application.execute(
            "composite_run",
            {"session_id": "composite-session", "components": []},
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(composite.calls[0][1], "composite-session")


if __name__ == "__main__":
    unittest.main()
