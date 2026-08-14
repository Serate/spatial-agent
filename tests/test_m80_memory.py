import json
import os
import tempfile
import unittest

from agent.memory import FactMemory, _extract_facts, memory_enabled
from agent.models import AgentRunResult, PlanStep, RunStatus, StepRun, TaskPlan
from agent.service import AgentService
from agent.sqlite_store import SQLiteConversationStore
from agent.runtime import AgentRuntime, InMemoryConversationStore, InMemoryStateStore
from agent.tools import ToolRegistry


def completed_result(run_id="run-1", session_id="conv-1", admin="洪山区", ratio=0.12):
    plan = TaskPlan(
        "筛选建设候选",
        [PlanStep("screening", "get_zonal_buildability_analysis", {"admin_name": admin}, [])],
        {"type": "buildability_result"},
    )
    steps = [
        StepRun(
            "screening",
            "get_zonal_buildability_analysis",
            {"admin_name": admin},
            status="COMPLETED",
            result={
                "admin_name": admin,
                "statistics": {
                    "candidate_pixel_count": 1000,
                    "candidate_ratio": ratio,
                    "valid_pixel_count": 8000,
                    "mean": 120.5,
                },
            },
        )
    ]
    return AgentRunResult(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        request="筛选" + admin + "建设候选",
        session_id=session_id,
        plan=plan,
        steps=steps,
        answer="{}建设候选筛选完成：候选比例 {:.0%}。".format(admin, ratio),
    )


class PlannerStub:
    def plan(self, request, context=None):
        return TaskPlan(
            "stub",
            [PlanStep("health", "get_dataset_health_report", {"dataset": "all"}, [])],
            {"type": "dataset_health_result"},
        )


class ToolStubAdapter:
    def invoke(self, name, arguments):
        return {"dataset": "all", "status": "ready", "capabilities": [], "datasets": []}


def stub_registry():
    definitions = {
        "get_dataset_health_report": {
            "name": "get_dataset_health_report",
            "input_schema": {"type": "object", "additionalProperties": True},
        }
    }
    return ToolRegistry(definitions, ToolStubAdapter())


class M80MemoryUnitTests(unittest.TestCase):
    def test_extract_facts_allowlists_scalar_statistics(self):
        result = completed_result()
        facts = _extract_facts(result)
        self.assertEqual(facts["candidate_pixel_count"], 1000)
        self.assertEqual(facts["candidate_ratio"], 0.12)
        self.assertEqual(facts["mean"], 120.5)
        self.assertEqual(facts["admin_name"], "洪山区")
        self.assertNotIn("error", facts)

    def test_remember_only_for_completed_runs(self):
        memory = FactMemory()
        fact = memory.remember(completed_result())
        self.assertIsNotNone(fact)
        self.assertEqual(fact["result_type"], "buildability_result")
        self.assertEqual(fact["admin_names"], ["洪山区"])
        failed = AgentRunResult(
            run_id="r-fail",
            status=RunStatus.FAILED,
            request="x",
            session_id="conv-1",
        )
        self.assertIsNone(memory.remember(failed))

    def test_recall_is_session_scoped_and_newest_first(self):
        memory = FactMemory()
        memory.remember(completed_result(run_id="r1", session_id="conv-1"))
        memory.remember(completed_result(run_id="r2", session_id="conv-1"))
        memory.remember(completed_result(run_id="r3", session_id="conv-2"))
        own = memory.recall(session_id="conv-1")
        self.assertEqual([fact["run_id"] for fact in own], ["r2", "r1"])
        other = memory.recall(session_id="conv-2")
        self.assertEqual([fact["run_id"] for fact in other], ["r3"])
        # Global recall sees everything, but planner context stays session-scoped.
        all_facts = memory.recall_global()
        self.assertEqual(len(all_facts), 3)

    def test_recall_filters_by_query(self):
        memory = FactMemory()
        memory.remember(completed_result(run_id="r1", session_id="conv-1", admin="洪山区"))
        memory.remember(completed_result(run_id="r2", session_id="conv-1", admin="江夏区"))
        hits = memory.recall(session_id="conv-1", query="江夏")
        self.assertEqual([fact["run_id"] for fact in hits], ["r2"])

    def test_context_section_is_bounded_and_credential_free(self):
        memory = FactMemory()
        memory.remember(completed_result())
        section = memory.context_section(session_id="conv-1")
        self.assertTrue(section["available"])
        self.assertEqual(section["fact_count"], 1)
        first = section["facts"][0]
        self.assertEqual(first["result_type"], "buildability_result")
        self.assertNotIn("facts", first)  # only bounded fields injected
        empty = memory.context_section(session_id="conv-99")
        self.assertFalse(empty["available"])

    def test_memory_disabled_returns_nothing(self):
        os.environ["SPATIAL_AGENT_MEMORY_ENABLED"] = "0"
        try:
            self.assertFalse(memory_enabled())
            memory = FactMemory()
            self.assertIsNone(memory.remember(completed_result()))
            self.assertEqual(memory.recall(session_id="conv-1"), [])
        finally:
            os.environ.pop("SPATIAL_AGENT_MEMORY_ENABLED", None)


class M80MemorySqliteTests(unittest.TestCase):
    def test_sqlite_roundtrip_and_session_filtering(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "memory.db")
            store = SQLiteConversationStore(path)
            memory = FactMemory(sqlite_conversation_store=store)
            memory.remember(completed_result(run_id="r1", session_id="conv-1"))
            memory.remember(completed_result(run_id="r2", session_id="conv-1", admin="江夏区"))
            memory.remember(completed_result(run_id="r3", session_id="conv-2"))
            self.assertEqual(len(store.list_memory_facts(session_id="conv-1")), 2)
            self.assertEqual(len(store.list_memory_facts(session_id="conv-2")), 1)
            self.assertEqual(len(store.list_memory_facts(session_id=None)), 3)
            memory.clear_session("conv-1")
            self.assertEqual(len(store.list_memory_facts(session_id="conv-1")), 0)
            self.assertEqual(len(store.list_memory_facts(session_id=None)), 1)


class M80MemoryRuntimeTests(unittest.TestCase):
    def test_runtime_remembers_completed_run_and_injects_context(self):
        memory = FactMemory()
        runtime = AgentRuntime(
            PlannerStub(),
            stub_registry(),
            state_store=InMemoryStateStore(),
            conversation_store=InMemoryConversationStore(),
            memory=memory,
        )
        result = runtime.run("查询洪山区", session_id="conv-1")
        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(len(memory.recall(session_id="conv-1")), 1)
        # Second run in same session injects the remembered fact into context.
        second = runtime.run("继续分析", session_id="conv-1")
        context = second.context_evidence
        self.assertTrue(context["available"])
        self.assertIn("memory", context["section_names"])


class M80MemoryServiceTests(unittest.TestCase):
    def test_service_runs_remember_and_list_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(os.path.join(directory, "state.db")))
            try:
                first = service.run(
                    request="你好",
                    session_id="conversation-mem",
                    planner="rule",
                    backend="memory",
                )
                self.assertEqual(first["status"], "COMPLETED")
                self.assertTrue(first.get("memory_evidence", {}).get("enabled"))
                memory = service.list_memory(session_id="conversation-mem")
                self.assertGreaterEqual(memory["fact_count"], 1)
                self.assertFalse(memory["global_scope"])
                # Global scope is explicit and separate from session recall.
                global_memory = service.list_memory(global_scope=True, limit=50)
                self.assertGreaterEqual(global_memory["fact_count"], 1)
            finally:
                service.close()

    def test_list_memory_requires_session_unless_global(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(state_db_path=str(os.path.join(directory, "state.db")))
            try:
                with self.assertRaises(ValueError):
                    service.list_memory(session_id="")
            finally:
                service.close()


class M80MemoryHttpTests(unittest.TestCase):
    def test_http_memory_endpoint(self):
        import threading
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from serve_api import AgentApiHandler

        class TestHandler(AgentApiHandler):
            service = AgentService(state_db_path=None)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("POST", "/runs", body=json.dumps({
                    "request": "你好",
                    "session_id": "conversation-http-mem",
                    "planner": "rule",
                    "backend": "memory",
                }), headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode("utf-8"))
                self.assertIn("memory_evidence", payload)

                connection.request("GET", "/memory?session_id=conversation-http-mem")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                memory = json.loads(response.read().decode("utf-8"))
                self.assertTrue(memory["memory_enabled"])
                self.assertGreaterEqual(memory["fact_count"], 1)
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TestHandler.service.close()


if __name__ == "__main__":
    unittest.main()
