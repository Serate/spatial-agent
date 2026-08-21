"""M148 HTTP artifact downloads must respect the selected Domain."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from domains.text.domain import TEXT_DOMAIN_PACK
from serve_api import AgentApiHandler


def _request(port, name):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", name)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


class M148ArtifactDomainHttpTests(unittest.TestCase):
    def test_dev_http_hides_cross_domain_run_action_and_geojson_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geojson_root = root / "geojson"
            store = ArtifactStore(root)
            store.write_run({"run_id": "text-run", "domain_id": "text", "status": "COMPLETED"})
            store.write_run({"run_id": "gis-run", "domain_id": "gis", "status": "COMPLETED"})
            store.write_action(
                {
                    "action_execution_id": "text-action",
                    "domain_id": "text",
                    "action_id": "text.summarize",
                    "status": "COMPLETED",
                }
            )
            store.write_action(
                {
                    "action_execution_id": "gis-action",
                    "domain_id": "gis",
                    "action_id": "gis.inspect",
                    "status": "COMPLETED",
                }
            )
            geojson_root.mkdir()
            for name, domain in (("text-run", "text"), ("gis-run", "gis")):
                (geojson_root / (name + ".geojson")).write_text(
                    json.dumps(
                        {
                            "type": "FeatureCollection",
                            "properties": {"domain_id": domain},
                            "features": [],
                        }
                    ),
                    encoding="utf-8",
                )

            handler_store = store
            handler_geojson_root = geojson_root

            class TextHandler(AgentApiHandler):
                service = AgentService(artifact_store=handler_store, domain_pack=TEXT_DOMAIN_PACK)
                artifact_root = root
                geojson_root = handler_geojson_root

            server = ThreadingHTTPServer(("127.0.0.1", 0), TextHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                allowed = [
                    "/artifacts/runs/text-run.json",
                    "/artifacts/actions/action-text-action.json",
                    "/artifacts/geojson/text-run.geojson",
                ]
                denied = [
                    "/artifacts/runs/gis-run.json",
                    "/artifacts/actions/action-gis-action.json",
                    "/artifacts/geojson/gis-run.geojson",
                ]
                allowed_statuses = [_request(server.server_address[1], path)[0] for path in allowed]
                denied_statuses = [_request(server.server_address[1], path)[0] for path in denied]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TextHandler.service.close()

        self.assertEqual(allowed_statuses, [200, 200, 200])
        self.assertEqual(denied_statuses, [404, 404, 404])

    def test_production_safe_artifact_applies_domain_filter(self):
        try:
            import production_api
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("FastAPI is not installed in this environment")
            raise

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root)
            store.write_run({"run_id": "text-run", "domain_id": "text", "status": "COMPLETED"})
            store.write_run({"run_id": "gis-run", "domain_id": "gis", "status": "COMPLETED"})
            original_service = production_api.service
            original_root = production_api.ARTIFACT_ROOT
            try:
                production_api.service = AgentService(artifact_store=store, domain_pack=TEXT_DOMAIN_PACK)
                production_api.ARTIFACT_ROOT = root
                allowed = production_api.run_artifact("text-run.json")
                with self.assertRaises(production_api.HTTPException) as error:
                    production_api.run_artifact("gis-run.json")
            finally:
                production_api.service.close()
                production_api.service = original_service
                production_api.ARTIFACT_ROOT = original_root

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(Path(allowed.path).name, "text-run.json")


if __name__ == "__main__":
    unittest.main()
