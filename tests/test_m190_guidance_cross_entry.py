"""M190-B: discovery guidance remains stable across recovery entries."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.contract_harness import compare_results
from serve_api import AgentApiHandler


REQUEST = "查询一个尚未注册的空间对象"


def _post(port: int, payload: dict) -> dict:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            "/runs",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        value = json.loads(response.read().decode("utf-8"))
        if response.status >= 400:
            raise AssertionError(value)
        return value
    finally:
        connection.close()


def _guidance(payload: dict) -> tuple:
    result = payload.get("result") or {}
    planning = result.get("planning") or {}
    selection = planning.get("workflow_selection") or {}
    interaction = result.get("selection_interaction") or {}
    return (
        selection.get("state"),
        tuple(item.get("id") for item in selection.get("suggested_capability_details", [])),
        tuple(interaction.get("allowed_actions", [])),
    )


class M190GuidanceCrossEntryTests(unittest.TestCase):
    def test_service_http_and_artifact_share_open_guidance(self):
        with tempfile.TemporaryDirectory(prefix="m190-guidance-http-") as directory:
            root = Path(directory)
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=ArtifactStore(root / "artifacts"),
            )
            self.addCleanup(service.close)
            direct = service.run(
                REQUEST,
                session_id="m190-direct",
                planner="rule",
                backend="memory",
                export_artifact=True,
            )

            handler_service = service

            class Handler(AgentApiHandler):
                service = handler_service
                artifact_root = root / "artifacts"

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                http = _post(
                    server.server_address[1],
                    {
                        "request": REQUEST,
                        "session_id": "m190-http",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            direct_artifact = json.loads(
                Path(direct["artifact_ref"]).read_text(encoding="utf-8")
            )
            http_artifact = json.loads(
                Path(http["artifact_ref"]).read_text(encoding="utf-8")
            )

        self.assertEqual(direct["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(http["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(_guidance(direct), _guidance(http))
        self.assertEqual(_guidance(direct), _guidance(direct_artifact))
        self.assertEqual(_guidance(http), _guidance(http_artifact))
        self.assertEqual(compare_results([direct, http]), [])

    def test_async_and_restart_keep_open_guidance(self):
        with tempfile.TemporaryDirectory(prefix="m190-guidance-restart-") as directory:
            root = Path(directory)
            state_db_path = str(root / "state.db")
            artifact_root = root / "artifacts"
            service = AgentService(
                state_db_path=state_db_path,
                artifact_store=ArtifactStore(artifact_root),
            )
            submitted = service.run_async(
                request=REQUEST,
                session_id="m190-async",
                planner="rule",
                backend="memory",
                export_artifact=True,
                idempotency_key="m190-guidance-async",
            )
            final = None
            for _ in range(200):
                final = service.get_run(submitted["run_id"])
                if final.get("status") not in {"PLANNING", "EXECUTING"}:
                    break
                time.sleep(0.01)
            self.assertEqual(final["status"], "NEEDS_CLARIFICATION")
            service.close()

            restarted = AgentService(
                state_db_path=state_db_path,
                artifact_store=ArtifactStore(artifact_root),
            )
            self.addCleanup(restarted.close)
            recovered = restarted.get_run(submitted["run_id"])

        self.assertEqual(_guidance(final), _guidance(recovered))
        self.assertIn(
            "select_capability",
            (recovered["result"].get("selection_interaction") or {}).get(
                "allowed_actions", []
            ),
        )


if __name__ == "__main__":
    unittest.main()
