"""M224-B: explicit Domain HTTP routing is consistent across both servers."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.domain_runtime_host import DomainRuntimeHost
from agent.service import AgentService
from serve_api import AgentApiHandler


class M224DomainHttpTests(unittest.TestCase):
    def test_dev_server_routes_runs_recovery_and_artifacts_by_url_domain(self):
        with tempfile.TemporaryDirectory(prefix="m224-domain-http-") as directory:
            root = Path(directory)
            database = str(root / "state.db")
            artifacts = ArtifactStore(root / "runs", legacy_domain_id="gis")

            def factory(domain_id: str) -> AgentService:
                return AgentService(
                    artifact_store=artifacts,
                    state_db_path=database,
                    domain_id=domain_id,
                    legacy_domain_id="gis",
                )

            host = DomainRuntimeHost(service_factory=factory)
            host.start()

            class Handler(AgentApiHandler):
                service = host.service("gis")
                pass

            Handler.host = host
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def request(method: str, path: str, payload=None):
                connection = HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=10
                )
                body = None if payload is None else json.dumps(payload).encode("utf-8")
                headers = {"Content-Type": "application/json"} if body else {}
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                raw = response.read()
                content_type = response.getheader("Content-Type") or ""
                connection.close()
                decoded = (
                    json.loads(raw.decode("utf-8"))
                    if "json" in content_type
                    else raw
                )
                return response.status, decoded

            try:
                gis_status, gis = request("GET", "/domains/gis/capabilities")
                text_status, text = request("GET", "/domains/text/capabilities")
                run_status, run = request(
                    "POST",
                    "/domains/text/runs",
                    {
                        "request": "请摘要：多领域 HTTP 路由必须保留运行身份。",
                        "session_id": "conversation-text-http",
                        "export_artifact": True,
                    },
                )
                own_status, restored = request(
                    "GET", "/domains/text/runs/" + run["run_id"]
                )
                wrong_status, _wrong = request(
                    "GET", "/domains/gis/runs/" + run["run_id"]
                )
                artifact_name = Path(run["artifact_ref"]).name
                artifact_status, _artifact = request(
                    "GET", "/domains/text/artifacts/runs/" + artifact_name
                )
                wrong_artifact_status, _wrong_artifact = request(
                    "GET", "/domains/gis/artifacts/runs/" + artifact_name
                )
                mismatch_status, mismatch = request(
                    "POST",
                    "/domains/text/runs",
                    {"domain_id": "gis", "request": "请摘要这段文本。"},
                )
                unknown_status, unknown = request(
                    "GET", "/domains/unknown/capabilities"
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                host.close()

        self.assertEqual((gis_status, gis["domain_id"]), (200, "gis"))
        self.assertEqual((text_status, text["domain_id"]), (200, "text"))
        self.assertEqual((run_status, run["domain_id"]), (200, "text"))
        self.assertEqual(
            run["result"]["artifacts"]["run"]["access"]["path"],
            "/domains/text/artifacts/runs/" + Path(run["artifact_ref"]).name,
        )
        self.assertEqual((own_status, restored["domain_id"]), (200, "text"))
        self.assertEqual(wrong_status, 404)
        self.assertEqual(artifact_status, 200)
        self.assertEqual(wrong_artifact_status, 404)
        self.assertEqual((mismatch_status, mismatch["error_code"]), (400, "domain_mismatch"))
        self.assertEqual((unknown_status, unknown["error_code"]), (400, "unknown_domain"))

    def test_fastapi_declares_generic_domain_routes_without_gis_shortcuts(self):
        import production_api

        declared = {
            (method, route.path)
            for route in production_api.app.routes
            for method in (getattr(route, "methods", None) or set())
        }
        required = {
            ("GET", "/domains/{domain_id}/capabilities"),
            ("POST", "/domains/{domain_id}/runs"),
            ("POST", "/domains/{domain_id}/runs/async"),
            ("GET", "/domains/{domain_id}/runs/{run_id}"),
            ("POST", "/domains/{domain_id}/runs/{run_id}/interaction"),
            ("POST", "/domains/{domain_id}/actions/{action_id}"),
            ("GET", "/domains/{domain_id}/tools/approvals"),
            ("GET", "/domains/{domain_id}/tools/approvals/{approval_id}"),
            ("POST", "/domains/{domain_id}/tools/approvals/{approval_id}/resolve"),
            ("GET", "/domains/{domain_id}/artifacts/runs/{name}"),
        }

        self.assertTrue(required.issubset(declared))
        self.assertNotIn(("POST", "/domains/{domain_id}/comparisons"), declared)
        self.assertEqual(
            production_api.domain_capabilities("text")["domain_id"], "text"
        )


if __name__ == "__main__":
    unittest.main()
