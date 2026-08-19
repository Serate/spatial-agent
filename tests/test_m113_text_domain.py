import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.errors import ToolError
from agent.service import AgentService
from evaluation.contract_harness import compare_results
from domains.text.runtime import build_text_runtime
from serve_api import AgentApiHandler


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


class M113TextDomainTests(unittest.TestCase):
    def test_service_capabilities_are_owned_by_selected_domain(self):
        service = AgentService(runtime_factory=_text_runtime_factory)
        try:
            catalog = service.capabilities()
        finally:
            service.close()

        self.assertEqual(catalog["domain_id"], "text")
        self.assertEqual([item["id"] for item in catalog["capabilities"]], ["text_summary"])
        self.assertNotIn("buildability_screening", catalog["capabilities"])

    def test_runtime_capabilities_keep_domain_and_provider_evidence(self):
        runtime = build_text_runtime()

        snapshot = runtime.runtime_capabilities(max_files=1)

        self.assertEqual(snapshot["domain_id"], "text")
        self.assertEqual(snapshot["runtime"]["backend"], "memory")
        self.assertEqual(snapshot["tool_provider"]["id"], "text-native")
        self.assertEqual(snapshot["health_status"], "ready")
        self.assertEqual(snapshot["data_readiness"], "not_applicable")

        service = AgentService(runtime_factory=_text_runtime_factory)
        try:
            service_snapshot = service.runtime_capabilities(max_files=1)
        finally:
            service.close()
        self.assertEqual(service_snapshot["domain_id"], "text")
        self.assertEqual(service_snapshot["tool_provider"]["id"], "text-native")

    def test_http_capabilities_use_selected_domain_runtime(self):
        class TextHandler(AgentApiHandler):
            service = AgentService(runtime_factory=_text_runtime_factory)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )
        thread.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            connection.request("GET", "/capabilities?backend=memory")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TextHandler.service.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["domain_id"], "text")
        self.assertEqual(payload["capabilities"][0]["id"], "text_summary")

    def test_http_runtime_capabilities_use_domain_evidence(self):
        class TextHandler(AgentApiHandler):
            service = AgentService(runtime_factory=_text_runtime_factory)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            connection.request("GET", "/capabilities/runtime?max_files=1")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TextHandler.service.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["domain_id"], "text")
        self.assertEqual(payload["health_status"], "ready")
        self.assertEqual(payload["data_readiness"], "not_applicable")

    def test_non_gis_tool_runs_through_registry_and_runtime(self):
        runtime = build_text_runtime()

        result = runtime.run("这是一段需要被摘要的文本。")

        self.assertEqual(runtime._allowed_permissions, {"text_data:read"})
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "text_summary_result")
        self.assertEqual(result.steps[0].tool, "summarize_text")
        self.assertEqual(result.steps[0].status, "COMPLETED")
        self.assertEqual(result.steps[0].result["word_count"], 1)
        self.assertIn("文本摘要：", result.answer)
        self.assertEqual(
            result.context_evidence["section_names"].count("capability_catalog"),
            1,
        )
        self.assertEqual(
            result.plan_evidence["selected_capability_id"], "text_summary"
        )

    def test_text_tool_schema_rejects_unknown_input(self):
        runtime = build_text_runtime()

        with self.assertRaises(ToolError):
            runtime._registry.invoke(
                "summarize_text",
                {"text": "摘要", "unexpected": True},
            )

    def test_service_and_artifact_share_non_gis_result_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory,
            )
            try:
                payload = service.run(
                    "请摘要这段文本并保留可审计的执行证据。",
                    export_artifact=True,
                )
            finally:
                service.close()

            artifact_path = Path(payload["artifact_ref"])
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["result"]["type"], "text_summary_result")
        self.assertEqual(payload["result"]["title"], "文本摘要")
        self.assertTrue(payload["result"]["workspace"]["registered_type"])
        self.assertIn("generic", payload["result"]["workspace"]["panels"])
        self.assertEqual(payload["result"]["planning"]["domain_id"], "text")
        self.assertEqual(compare_results([payload, artifact]), [])
        self.assertEqual(
            artifact["result"]["data"]["evidence_steps"][0]["tool"],
            "summarize_text",
        )


if __name__ == "__main__":
    unittest.main()
