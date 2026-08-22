"""M194-C: composed workflow identity survives HTTP, async and restart."""

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
from domains.gis.domain import GIS_DOMAIN_PACK
from serve_api import AgentApiHandler


def _workflow():
    return {
        "components": [
            {
                "component_id": "boundary",
                "template_id": "admin_boundary_query",
                "constraints": {"admin_name": "洪山区"},
            },
            {
                "component_id": "dem",
                "template_id": "raster_metadata",
                "constraints": {"dataset": "dem"},
            },
        ]
    }


def _component_identity(payload):
    selection = payload["plan_evidence"]["workflow_selection"]
    return (
        selection["workflow_component_ids"],
        selection["workflow_component_template_ids"],
    )


def _request_json(port, method, path, payload=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    if response.status >= 400:
        raise AssertionError("HTTP {}: {}".format(response.status, data))
    return data


def _wait_for_terminal(service, run_id):
    for _ in range(200):
        payload = service.get_run(run_id)
        if payload.get("status") not in {"PLANNING", "EXECUTING"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("composed async run did not complete")


class M194CompositionCrossEntryTests(unittest.TestCase):
    def test_http_preview_run_detail_and_artifact_keep_component_identity(self):
        with tempfile.TemporaryDirectory(prefix="m194-http-composition-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=GIS_DOMAIN_PACK,
            )

            class Handler(AgentApiHandler):
                pass

            Handler.service = service
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "request": "组合查询洪山区边界和 DEM 元数据",
                    "session_id": "m194-http-composition",
                    "planner": "rule",
                    "backend": "memory",
                    "workflow": _workflow(),
                    "export_artifact": True,
                }
                preview = _request_json(server.server_address[1], "POST", "/runs/preview", payload)
                payload["preview_fingerprint"] = preview["plan_identity"]["fingerprint"]
                completed = _request_json(server.server_address[1], "POST", "/runs", payload)
                detail = _request_json(server.server_address[1], "GET", "/runs/" + completed["run_id"])
                artifact = store.read_run(completed["run_id"], domain_id="gis")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

        expected = (["boundary", "dem"], ["admin_boundary_query", "raster_metadata"])
        self.assertEqual(_component_identity(preview), expected)
        self.assertEqual(_component_identity(completed), expected)
        self.assertEqual(_component_identity(detail), expected)
        self.assertEqual(_component_identity(artifact), expected)

    def test_async_completion_and_sqlite_restart_keep_component_identity(self):
        with tempfile.TemporaryDirectory(prefix="m194-async-composition-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            first = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                submitted = first.run_async(
                    request="组合查询洪山区边界和 DEM 元数据",
                    session_id="m194-async-composition",
                    planner="rule",
                    backend="memory",
                    workflow=_workflow(),
                    export_artifact=True,
                    idempotency_key="m194-composition-async",
                )
                completed = _wait_for_terminal(first, submitted["run_id"])
            finally:
                first.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                recovered = restarted.get_run(submitted["run_id"], planner="rule", backend="memory")
                artifact = store.read_run(submitted["run_id"], domain_id="gis")
            finally:
                restarted.close()

        expected = (["boundary", "dem"], ["admin_boundary_query", "raster_metadata"])
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(_component_identity(completed), expected)
        self.assertEqual(_component_identity(recovered), expected)
        self.assertEqual(_component_identity(artifact), expected)


if __name__ == "__main__":
    unittest.main()
