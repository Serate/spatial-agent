"""M172: catalog-driven capability discovery stays Domain-neutral."""

from __future__ import annotations

import unittest
import json
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.capability_discovery import discover_from_catalog
from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.contract_harness import compare_results, normalize_result
from run_demo import build_runtime
from serve_api import AgentApiHandler
from domains.gis.domain import GIS_DOMAIN_PACK
from domains.text.domain import TEXT_DOMAIN_PACK


class M172CapabilityDiscoveryTests(unittest.TestCase):
    def test_catalog_selects_one_candidate_and_keeps_match_evidence(self):
        catalog = (
            {
                "id": "alpha",
                "priority": 10,
                "request_hints": {"phrases": ["alpha task"]},
            },
            {
                "id": "beta",
                "priority": 20,
                "request_hints": {"phrases": ["beta task"]},
            },
        )

        discovery = discover_from_catalog("run alpha task", {}, catalog)

        self.assertEqual(discovery.selected.capability_id, "alpha")
        self.assertEqual(discovery.source, "catalog")
        self.assertIn("alpha task", discovery.as_context_dict()["candidates"][0]["matched_hints"])

    def test_catalog_returns_ambiguous_or_unavailable_without_implicit_first_choice(self):
        catalog = (
            {"id": "alpha", "request_hints": {"phrases": ["shared task"]}},
            {"id": "beta", "request_hints": {"phrases": ["shared task"]}},
        )

        ambiguous = discover_from_catalog("shared task", {}, catalog)
        unavailable = discover_from_catalog("unrelated request", {}, catalog)

        self.assertEqual(ambiguous.selection_state, "ambiguous")
        self.assertIsNone(ambiguous.selected)
        self.assertEqual(unavailable.selection_state, "unavailable")
        self.assertEqual(unavailable.as_context_dict()["candidate_ids"], [])

    def test_gis_catalog_fallback_reaches_existing_planner_without_new_runtime_branch(self):
        facts = GIS_DOMAIN_PACK.extract_request_facts("查询DEM文件属性")
        discovery = GIS_DOMAIN_PACK.discover("查询DEM文件属性", facts)

        self.assertEqual(discovery.source, "catalog")
        self.assertEqual(discovery.selected.capability_id, "raster_metadata")

        result = build_runtime("rule", "memory").run("查询DEM文件属性")
        self.assertEqual(result.status.value, "COMPLETED")
        self.assertEqual(result.plan.output["type"], "raster_metadata_result")
        self.assertEqual(result.steps[0].tool, "get_raster_metadata")
        self.assertEqual(result.plan_evidence["workflow_selection"]["state"], "selected")

    def test_text_domain_uses_the_same_catalog_matcher(self):
        request = "请概括这段文本"
        facts = TEXT_DOMAIN_PACK.extract_request_facts(request)
        discovery = TEXT_DOMAIN_PACK.discover(request, facts)

        self.assertEqual(discovery.source, "catalog")
        self.assertEqual(discovery.selected.capability_id, "text_summary")
        self.assertEqual(discovery.as_context_dict()["selection_state"], "selected")

    def test_catalog_fallback_keeps_http_and_artifact_result_contract(self):
        with tempfile.TemporaryDirectory(prefix="m172-catalog-http-") as directory:
            artifact_root = Path(directory) / "runs"
            direct_service = AgentService(
                artifact_store=ArtifactStore(artifact_root)
            )
            direct = direct_service.run(
                "查询DEM文件属性",
                session_id="m172-direct",
                planner="rule",
                backend="memory",
                export_artifact=True,
            )
            shared_artifact_root = artifact_root

            class Handler(AgentApiHandler):
                service = AgentService(artifact_store=ArtifactStore(shared_artifact_root))
                artifact_root = shared_artifact_root

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_address[1])
                connection.request(
                    "POST",
                    "/runs",
                    json.dumps(
                        {
                            "request": "查询DEM文件属性",
                            "session_id": "m172-http",
                            "planner": "rule",
                            "backend": "memory",
                            "export_artifact": True,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    {"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                http = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                direct_service.close()
                Handler.service.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(compare_results([direct, http]), [])
        self.assertEqual(http["result"]["type"], "raster_metadata_result")
        self.assertEqual(http["plan_evidence"]["selected_capability_id"], "raster_metadata")
        self.assertTrue(http["result"]["lineage"]["artifact"]["available"])
        self.assertTrue(normalize_result(direct).equivalent_to(normalize_result(http)))


if __name__ == "__main__":
    unittest.main()
