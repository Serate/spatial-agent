import os
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from agent.artifact_store import ArtifactStore
from agent.domain_registry import (
    DOMAIN_REGISTRY_SCHEMA_VERSION,
    DomainSelectionError,
    domain_registry,
    resolve_domain_id,
    resolve_domain_pack,
)
from agent.runtime_factory import build_runtime
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore
from serve_api import AgentApiHandler


class M134DomainRegistryTests(unittest.TestCase):
    def test_catalog_is_bounded_and_lists_only_registered_domains(self):
        catalog = domain_registry().catalog()

        self.assertEqual(catalog["schema_version"], DOMAIN_REGISTRY_SCHEMA_VERSION)
        self.assertEqual(catalog["domain_ids"], ["gis", "text"])
        self.assertEqual(
            [item["id"] for item in catalog["domains"]],
            ["gis", "text"],
        )
        self.assertNotIn("module", str(catalog))

    def test_environment_and_explicit_selection_resolve_registered_pack(self):
        self.assertEqual(resolve_domain_id("text"), "text")
        self.assertEqual(resolve_domain_pack("text").domain_id, "text")

        with patch.dict(os.environ, {"SPATIAL_AGENT_DOMAIN": "text"}, clear=False):
            self.assertEqual(resolve_domain_id(), "text")
            self.assertEqual(resolve_domain_pack().domain_id, "text")

        runtime = build_runtime("rule", "memory", domain_id="text")
        self.assertEqual(runtime.runtime_capabilities()["domain_id"], "text")

    def test_unknown_or_invalid_domain_is_rejected_without_importing_arbitrary_module(self):
        for value in ("unknown", "domains.text.domain.TextDomainPack", "../text"):
            with self.subTest(value=value):
                with self.assertRaises(DomainSelectionError) as caught:
                    resolve_domain_pack(value)
                self.assertEqual(caught.exception.code, "unknown_domain")

    def test_sqlite_history_is_filtered_by_selected_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "agent.db")
            gis = AgentService(state_db_path=database, domain_id="gis")
            try:
                gis_result = gis.run("查询DEM栅格元数据", run_id="gis-owned")
            finally:
                gis.close()

            text = AgentService(state_db_path=database, domain_id="text")
            try:
                self.assertEqual(text.list_runs()["runs"], [])
                with self.assertRaisesRegex(ValueError, "run not found|another domain"):
                    text.get_run("gis-owned")
            finally:
                text.close()

            gis_again = AgentService(state_db_path=database, domain_id="gis")
            try:
                restored = gis_again.get_run("gis-owned")
            finally:
                gis_again.close()

        self.assertEqual(restored["domain_id"], "gis")
        self.assertEqual(gis_result["domain_id"], "gis")

    def test_artifact_history_is_filtered_by_selected_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(directory)
            database = os.path.join(directory, "agent.db")
            text = AgentService(
                artifact_store=store,
                state_db_path=database,
                domain_id="text",
            )
            try:
                result = text.run(
                    "请摘要这段文本并保留执行证据。",
                    session_id="m134-text-artifact",
                    export_artifact=True,
                )
            finally:
                text.close()

            gis = AgentService(
                artifact_store=store,
                state_db_path=database,
                domain_id="gis",
            )
            try:
                self.assertEqual(gis.list_runs()["runs"], [])
                with self.assertRaisesRegex(ValueError, "another domain"):
                    gis.get_run(result["run_id"])
            finally:
                gis.close()

    def test_domain_filtered_recovery_does_not_claim_other_domain_job(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "agent.db")
            store = SQLiteStateStore(database)
            store.create_async_job(
                "text-job-key",
                "text-job",
                {
                    "request": "请摘要这段文本。",
                    "session_id": "text-session",
                    "planner": "rule",
                    "backend": "memory",
                    "domain_id": "text",
                },
            )

            gis = AgentService(state_db_path=database, domain_id="gis")
            try:
                job = SQLiteStateStore(database).get_async_job("text-job")
            finally:
                gis.close()

        self.assertEqual(job["status"], "QUEUED")
        self.assertIsNone(job["owner_pid"])

    def test_dev_http_exposes_the_same_bounded_domain_catalog(self):
        class Handler(AgentApiHandler):
            service = AgentService(domain_id="text")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            connection.request("GET", "/domains")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            Handler.service.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["domain_ids"], ["gis", "text"])
        self.assertNotIn("module", str(payload))


if __name__ == "__main__":
    unittest.main()
