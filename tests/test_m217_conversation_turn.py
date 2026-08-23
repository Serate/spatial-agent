"""M217: bounded conversation-turn identity across the main recovery seams."""

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.artifact_manifest import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    normalize_artifact_manifest,
)
from agent.service import AgentService
from agent.service_async import (
    build_async_result_evidence,
    normalize_async_result_evidence,
)
from result_contract import build_result_contract
from run_demo import build_runtime
from serve_api import AgentApiHandler


class M217ConversationTurnTests(unittest.TestCase):
    def test_pending_is_consumed_only_by_a_clarification_reply(self):
        runtime = build_runtime("rule", "memory")

        first = runtime.run("查询行政区边界", session_id="m217-turn")
        reply = runtime.run("洪山区", session_id="m217-turn")

        self.assertEqual(first.status.value, "NEEDS_CLARIFICATION")
        self.assertEqual(reply.status.value, "COMPLETED")
        turn = reply.to_dict()["conversation_turn"]
        self.assertEqual(turn["mode"], "clarification_reply")
        self.assertTrue(turn["pending_consumed"])
        self.assertIn("查询行政区边界", reply.resolved_request)

        runtime.run("查询行政区边界", session_id="m217-independent")
        independent = runtime.run(
            "查询道路和水体分布", session_id="m217-independent"
        )
        independent_turn = independent.to_dict()["conversation_turn"]
        self.assertEqual(independent_turn["mode"], "new_request")
        self.assertTrue(independent_turn["pending_available"])
        self.assertFalse(independent_turn["pending_consumed"])
        self.assertNotIn("查询行政区边界", independent.resolved_request)

    def test_turn_projection_survives_service_sqlite_artifact_and_async(self):
        with tempfile.TemporaryDirectory(prefix="m217-turn-") as directory:
            root = Path(directory)
            artifact_store = ArtifactStore(str(root / "runs"))
            service = AgentService(
                artifact_store=artifact_store,
                state_db_path=str(root / "state.db"),
            )
            try:
                payload = service.run(
                    "查询洪山区行政区边界",
                    session_id="m217-persisted",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                run_id = payload["run_id"]
                expected = payload["result"]["conversation_turn"]
                restored = service.get_run(run_id)
            finally:
                service.close()

            recovered_service = AgentService(
                artifact_store=artifact_store,
                state_db_path=str(root / "state.db"),
            )
            try:
                restarted = recovered_service.get_run(run_id)
            finally:
                recovered_service.close()

            artifact = artifact_store.read_run(run_id, domain_id="gis")
            manifest = artifact_store.read_manifest(run_id, domain_id="gis")
            normalized_manifest = normalize_artifact_manifest(manifest)
            class TestHandler(AgentApiHandler):
                service = AgentService(
                    artifact_store=artifact_store,
                    state_db_path=str(root / "state.db"),
                )
                artifact_root = root / "runs"
                geojson_root = root / "geojson"

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=5
                )
                connection.request(
                    "GET",
                    "/artifacts/runs/"
                    + Path(payload["artifact_ref"]).name
                    + "/manifest",
                )
                response = connection.getresponse()
                http_manifest = json.loads(response.read().decode("utf-8"))
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TestHandler.service.close()
            artifact_contract = build_result_contract(artifact)
            async_projection = normalize_async_result_evidence(
                build_async_result_evidence(
                    payload["result"],
                    status=payload["status"],
                    artifact_ref=payload.get("artifact_ref"),
                ),
                status=payload["status"],
                artifact_ref=payload.get("artifact_ref"),
            )

        self.assertEqual(expected["mode"], "new_request")
        self.assertEqual(restored["result"]["conversation_turn"], expected)
        self.assertEqual(restarted["result"]["conversation_turn"], expected)
        self.assertEqual(artifact["conversation_turn"], expected)
        self.assertEqual(artifact_contract["conversation_turn"], expected)
        self.assertEqual(async_projection["conversation_turn"], expected)
        self.assertEqual(manifest["schema_version"], ARTIFACT_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(normalized_manifest["artifact"]["ref"], Path(payload["artifact_ref"]).name)
        self.assertTrue(any(item["id"] == "result" for item in manifest["entries"]))
        self.assertFalse(any("\\" in str(item) or ":\\" in str(item) for item in manifest.values()))
        self.assertEqual(response.status, 200)
        self.assertEqual(http_manifest["schema_version"], ARTIFACT_MANIFEST_SCHEMA_VERSION)
        self.assertNotIn("request", http_manifest)

    def test_real_async_job_persists_the_same_turn_projection(self):
        with tempfile.TemporaryDirectory(prefix="m217-async-turn-") as directory:
            root = Path(directory)
            store = ArtifactStore(str(root / "runs"))
            service = AgentService(
                artifact_store=store,
                state_db_path=str(root / "state.db"),
            )
            try:
                submitted = service.run_async(
                    request="查询洪山区行政区边界",
                    session_id="m217-async",
                    planner="rule",
                    backend="memory",
                    export_artifact=True,
                )
                final = None
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    final = service.get_run(submitted["run_id"])
                    if final.get("status") not in {"PLANNING", "EXECUTING", "CREATED"}:
                        break
                    time.sleep(0.02)
                observation = service.get_async_observability(submitted["run_id"])
            finally:
                service.close()

            self.assertIsNotNone(final)
            self.assertEqual(final["status"], "COMPLETED")
            expected = final["result"]["conversation_turn"]
            self.assertEqual(
                observation["result_evidence"]["conversation_turn"], expected
            )
            artifact = store.read_run(submitted["run_id"], domain_id="gis")
            self.assertEqual(artifact["async_result_evidence"]["conversation_turn"], expected)


if __name__ == "__main__":
    unittest.main()
