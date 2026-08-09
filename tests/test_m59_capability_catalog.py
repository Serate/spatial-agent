import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.capability_catalog import capability_catalog
from agent.data_quality import dataset_health_report
from agent.dataset_catalog import DatasetCatalog
from agent.service import AgentService
from serve_api import AgentApiHandler


class M59CapabilityCatalogTests(unittest.TestCase):
    def test_catalog_describes_shared_workflows_and_dataset_gates(self):
        catalog = capability_catalog(
            environment="memory",
            dataset_capabilities={"admin_areas": ["get_dataset_schema", "range_query"]},
        )
        buildability = next(
            item for item in catalog["capabilities"] if item["id"] == "buildability_screening"
        )
        self.assertEqual(buildability["dataset_gate"], "missing")
        self.assertIn("dem", buildability["missing_datasets"])
        self.assertIn(
            "get_zonal_buildability_analysis",
            next(
                item for item in catalog["capabilities"]
                if item["id"] == "buildability_screening"
            )["tools"],
        )

    def test_catalog_snapshot_is_not_mutable_source(self):
        first = capability_catalog()
        first["capabilities"][0]["label"] = "changed"
        second = capability_catalog()
        self.assertEqual(second["capabilities"][0]["label"], "通用对话")

    def test_catalog_without_health_evidence_marks_dataset_gate_unknown(self):
        item = next(
            item for item in capability_catalog()["capabilities"]
            if item["id"] == "buildability_screening"
        )
        self.assertEqual(item["dataset_gate"], "unknown")

    def test_health_report_exposes_catalog_with_dataset_state(self):
        catalog = DatasetCatalog.from_json("config/datasets.local.example.json")
        report = dataset_health_report(catalog, max_files=1)
        self.assertEqual(report["capability_catalog"]["version"], "1.0")
        self.assertEqual(
            report["capability_catalog"]["environment"], "local"
        )

    def test_http_capabilities_endpoint_is_json(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            connection.request("GET", "/capabilities")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["version"], "1.0")
        self.assertTrue(any(item["id"] == "buildability_screening" for item in payload["capabilities"]))

    def test_production_api_exposes_same_capability_contract(self):
        try:
            from production_api import capabilities as production_capabilities
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("requires production FastAPI dependencies")
            raise

        payload = production_capabilities()
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(
            [item["id"] for item in payload["capabilities"]],
            [item["id"] for item in capability_catalog()["capabilities"]],
        )


if __name__ == "__main__":
    unittest.main()
