"""M124 Domain-owned action metadata and complete non-GIS replay contracts."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.runtime import build_text_runtime
from evaluation.contract_harness import compare_results
from serve_api import AgentApiHandler


def _text_runtime_factory(planner, backend, **kwargs):
    return build_text_runtime(planner, backend, **kwargs)


def _request(port, method, path, payload=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, data


class M124DomainActionTests(unittest.TestCase):
    def test_console_uses_catalog_and_generic_action_dispatch(self):
        source = (Path(__file__).parents[1] / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("loadActions", source)
        self.assertIn("nativeFetch('/actions'+query)", source)
        self.assertIn("executeDomainAction", source)
        for action_id in (
            "gis.buildability_threshold_comparison",
            "gis.buildability_region_comparison",
            "gis.constrained_buildability_comparison",
        ):
            self.assertIn(action_id, source)
        self.assertNotIn("fetch('/comparisons'", source)
        self.assertNotIn("fetch('/region-comparisons'", source)
        self.assertNotIn("fetch('/constrained-comparisons'", source)

    def test_gis_actions_are_domain_owned_and_bounded(self):
        service = AgentService()
        try:
            actions = service.actions(planner="rule", backend="memory")
            self.assertEqual(actions["schema_version"], "spatial-agent.actions.v1")
            ids = [item["id"] for item in actions["actions"]]
            self.assertEqual(
                ids,
                [
                    "gis.buildability_threshold_comparison",
                    "gis.buildability_region_comparison",
                    "gis.constrained_buildability_comparison",
                ],
            )
            self.assertEqual(
                actions["actions"][0]["input_schema"]["required"],
                ["admin_name", "thresholds"],
            )
            with self.assertRaises(ValueError):
                service.execute_action("gis.not_declared", {}, backend="memory")
        finally:
            service.close()

    def test_text_domain_exposes_no_gis_actions(self):
        service = AgentService(runtime_factory=_text_runtime_factory)
        try:
            actions = service.actions()
            self.assertEqual(actions["domain_id"], "text")
            self.assertEqual(actions["actions"], [])
            catalog = service.capabilities()
        finally:
            service.close()
        self.assertEqual(catalog["actions"]["actions"], [])

    def test_dev_http_exposes_selected_domain_actions(self):
        class TextHandler(AgentApiHandler):
            service = AgentService(runtime_factory=_text_runtime_factory)

        server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, payload = _request(server.server_address[1], "GET", "/actions?backend=memory")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            TextHandler.service.close()
        self.assertEqual(status, 200)
        self.assertEqual(payload["domain_id"], "text")
        self.assertEqual(payload["actions"], [])

    def test_text_replay_is_consistent_across_http_artifact_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                artifact_store=ArtifactStore(directory),
                runtime_factory=_text_runtime_factory,
            )

            class TextHandler(AgentApiHandler):
                pass

            TextHandler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, http_payload = _request(
                    server.server_address[1],
                    "POST",
                    "/runs",
                    {
                        "request": "请摘要这段文本并保留跨入口证据。",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                )
                self.assertEqual(status, 200)
                artifact = json.loads(
                    Path(http_payload["artifact_ref"]).read_text(encoding="utf-8")
                )
                recovered = service.get_run(
                    http_payload["run_id"], planner="rule", backend="memory"
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        self.assertEqual(http_payload["status"], "COMPLETED")
        self.assertEqual(http_payload["result"]["type"], "text_summary_result")
        self.assertEqual(http_payload["result"]["workspace"]["panels"], ["generic"])
        self.assertEqual(http_payload["result"]["views"]["panels"], {})
        self.assertEqual(compare_results([http_payload, artifact, recovered]), [])


if __name__ == "__main__":
    unittest.main()
