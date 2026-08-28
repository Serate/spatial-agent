import unittest
import json
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from agent.runtime_factory import build_runtime
from domains.text.domain import TEXT_DOMAIN_PACK
from domains.text.runtime import build_text_runtime


class RecordedTextPlannerClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, messages, schema):
        self.calls.append((messages, schema))
        return {
            "goal": "summarize supplied text",
            "steps": [
                {
                    "id": "summary",
                    "tool": "summarize_text",
                    "args": {"text": "跨领域 Runtime 需要统一工具入口。"},
                    "depends_on": [],
                }
            ],
            "output": {
                "type": "text_summary_result",
                "title": "文本摘要",
                "summary": True,
            },
        }


class M133CrossDomainRuntimeTests(unittest.TestCase):
    def test_generic_factory_uses_text_domain_tool_provider(self):
        runtime = build_runtime("rule", "memory", domain_pack=TEXT_DOMAIN_PACK)

        capabilities = runtime.runtime_capabilities(max_files=1)
        result = runtime.run("请摘要这段文本")

        self.assertEqual(capabilities["domain_id"], "text")
        self.assertEqual(capabilities["tool_provider"]["id"], "text-native")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.steps[0].tool, "summarize_text")
        self.assertEqual(result.plan.output["type"], "text_summary_result")

    def test_text_runtime_factory_honors_openai_planner_selection(self):
        client = RecordedTextPlannerClient()
        with patch("agent.runtime_factory.load_openai_config", return_value={}), patch(
            "agent.runtime_factory.OpenAIPlannerClient", return_value=client
        ):
            runtime = build_text_runtime("openai", "memory")
            result = runtime.run("请摘要这段文本")

        # OpenAI mode now has two explicit model seams: planning and
        # user-facing answer generation.  The recorded client is shared by
        # this compact fixture, so both calls are visible here.
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "text_summary_result")
        prompt = client.calls[0][0][0]["content"]
        self.assertIn("summarize_text", prompt)
        self.assertNotIn("洪山区", prompt)

    def test_service_can_select_text_domain_without_custom_factory(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                payload = service.run(
                    "请摘要这段文本",
                    backend="memory",
                    session_id="m133-text-service",
                    export_artifact=True,
                )
            finally:
                service.close()

            artifact = json.loads(
                Path(payload["artifact_ref"]).read_text(encoding="utf-8")
            )

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["result"]["planning"]["domain_id"], "text")
        self.assertEqual(artifact["result"]["type"], "text_summary_result")

    def test_http_service_can_select_text_domain_pack(self):
        from serve_api import AgentApiHandler

        class TextHandler(AgentApiHandler):
            service = AgentService(domain_pack=TEXT_DOMAIN_PACK)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=10
            )
            connection.request(
                "POST",
                "/runs",
                body=json.dumps(
                    {
                        "request": "请摘要这段文本",
                        "planner": "rule",
                        "backend": "memory",
                        "session_id": "m133-text-http",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TextHandler.service.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["result"]["planning"]["domain_id"], "text")
        self.assertEqual(payload["result"]["type"], "text_summary_result")

    def test_domain_pack_selection_survives_async_restart_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            first = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(directory),
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                submitted = first.run_async(
                    request="请摘要这段文本",
                    backend="memory",
                    export_artifact=True,
                    session_id="m133-text",
                )
                for _ in range(200):
                    current = first.get_run(submitted["run_id"])
                    if current["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                completed = first.get_run(submitted["run_id"])
            finally:
                first.close()

            second = AgentService(
                state_db_path=database,
                artifact_store=ArtifactStore(directory),
                domain_pack=TEXT_DOMAIN_PACK,
            )
            try:
                restored = second.get_run(submitted["run_id"])
            finally:
                second.close()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(restored["status"], "COMPLETED")
        self.assertEqual(restored["result"]["planning"]["domain_id"], "text")
        self.assertEqual(restored["result"]["type"], "text_summary_result")


if __name__ == "__main__":
    unittest.main()
