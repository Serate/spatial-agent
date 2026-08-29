import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.capability_catalog import (
    capability_catalog,
    capability_context_summary,
    capability_suggestions,
)
from domains.gis.adapters.data_quality import dataset_health_report
from domains.gis.adapters.dataset_catalog import DatasetCatalog
from agent.service import AgentService
from agent.runtime_capabilities import runtime_capability_snapshot
from result_contract import build_result_contract
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

    def test_capability_suggestions_share_catalog_labels(self):
        suggestions = capability_suggestions()
        self.assertEqual(suggestions[0], {"id": "conversation", "label": "通用对话"})
        self.assertTrue(any(item["id"] == "buildability_screening" for item in suggestions))

    def test_capability_context_summary_is_compact_and_tool_schema_aware(self):
        catalog = capability_catalog(environment="memory")
        summary = capability_context_summary(
            catalog=catalog,
            tool_definitions={
                "range_query": {
                    "description": "query",
                    "side_effect": "none",
                    "requires_approval": False,
                    "input_schema": {
                        "required": ["dataset", "conditions", "limit"],
                        "properties": {
                            "dataset": {"type": "string", "enum": ["admin_areas"]},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                        },
                        "additionalProperties": False,
                    },
                    "output_schema": {"required": ["result_ref"]},
                }
            },
            selected_capability_ids=["admin_boundary_query"],
            max_capabilities=2,
        )

        self.assertEqual(summary["schema_version"], "spatial-agent.capability-catalog-context.v1")
        self.assertEqual(summary["environment"], "memory")
        self.assertEqual(summary["capabilities"][0]["id"], "admin_boundary_query")
        self.assertIn("range_query", summary["tool_schemas"])
        self.assertIn("conditions", summary["tool_schemas"]["range_query"]["required"])
        json.dumps(summary, ensure_ascii=False)

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

    def test_geometry_evidence_statuses_are_explicit(self):
        boundary = build_result_contract({
            "result_type": "admin_area_result",
            "geojson_ref": "outputs/geojson/boundary.geojson",
            "_geometry_evidence": {
                "status": "boundary_geometry",
                "reason": "行政区边界",
                "feature_count": 1,
            },
        })
        truncated = build_result_contract({
            "result_type": "buildability_result",
            "_geometry_evidence": {
                "status": "truncated_geometry",
                "reason": "摘要达到大小上限",
                "feature_count": 1,
                "truncated": True,
            },
        })
        self.assertTrue(boundary["geometry"]["available"])
        self.assertEqual(boundary["geometry"]["status"], "boundary_geometry")
        self.assertFalse(truncated["geometry"]["available"])
        self.assertTrue(truncated["geometry"]["truncated"])

    def test_runtime_snapshot_contains_bounded_data_evidence(self):
        snapshot = runtime_capability_snapshot(max_files=1)
        self.assertIn(snapshot["health_status"], {"ready", "degraded", "unavailable"})
        self.assertTrue(snapshot.get("updated_at"))
        self.assertIn("data_evidence", snapshot)
        buildability = next(
            item for item in snapshot["capabilities"]
            if item["id"] == "buildability_screening"
        )
        self.assertIn("datasets", buildability["runtime_evidence"])


if __name__ == "__main__":
    unittest.main()
