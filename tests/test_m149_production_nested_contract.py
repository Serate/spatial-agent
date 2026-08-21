"""M149-B: production/dev HTTP nested result contract acceptance.

This test owns only the entry-point acceptance boundary.  It deliberately
does not import or change the shared result/schema migration code.  The
PowerShell production acceptance script is exercised in offline mode so
negative payloads prove that the production gate rejects drift even when
FastAPI or GIS dependencies are absent.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from serve_api import AgentApiHandler


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "scripts" / "production_acceptance.ps1"


def _powershell():
    return shutil.which("pwsh") or shutil.which("powershell")


def _post(port: int, path: str, payload: dict):
    connection = HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _get(port: int, path: str):
    connection = HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _nested_projection(payload: dict) -> dict:
    result = payload["result"]
    workspace = result["workspace"]
    views = result["views"]
    return {
        "result_schema": result["schema_version"],
        "result_type": result["type"],
        "workspace_schema": workspace["schema_version"],
        "workspace_result_type": workspace["result_type"],
        "workspace_panels": sorted(workspace["panels"]),
        "view_specs": sorted(
            (
                item["id"],
                item["renderer"],
                item["schema_version"],
            )
            for item in workspace["view_specs"]
        ),
        "views_schema": views["schema_version"],
        "view_panels": sorted(
            (name, panel["kind"])
            for name, panel in views["panels"].items()
        ),
    }


class M149ProductionNestedContractTests(unittest.TestCase):
    def _run_offline_acceptance(self, payload: dict):
        shell = _powershell()
        if not shell:
            self.skipTest(
                "PowerShell is unavailable; production nested contract acceptance skipped"
            )
        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            return subprocess.run(
                [
                    shell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ACCEPTANCE),
                    "-ContractPayloadPath",
                    str(payload_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )

    def _baseline(self, directory: str):
        service = AgentService(artifact_store=ArtifactStore(directory))
        try:
            payload = service.run("查询DEM栅格元数据", export_artifact=True)
            artifact = json.loads(
                Path(payload["artifact_ref"]).read_text(encoding="utf-8")
            )
            return payload, artifact
        finally:
            service.close()

    def test_production_gate_accepts_current_and_rejects_nested_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, artifact = self._baseline(directory)

        accepted = self._run_offline_acceptance(payload)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout)["status"], "ok")

        artifact_accepted = self._run_offline_acceptance(artifact)
        self.assertEqual(artifact_accepted.returncode, 0, artifact_accepted.stderr)

        async_payload = copy.deepcopy(payload)
        async_payload["result_evidence"] = {
            "schema_version": "spatial-agent.async-result-evidence.v1",
            "state": "success",
            "status": "COMPLETED",
            "workspace": copy.deepcopy(payload["result"]["workspace"]),
            "views": copy.deepcopy(payload["result"]["views"]),
            "artifact": {"available": True, "ref": "run.json"},
        }
        async_accepted = self._run_offline_acceptance(async_payload)
        self.assertEqual(async_accepted.returncode, 0, async_accepted.stderr)

        async_invalid = copy.deepcopy(async_payload)
        async_invalid["result_evidence"]["views"]["schema_version"] = (
            "spatial-agent.views.v999"
        )
        async_rejected = self._run_offline_acceptance(async_invalid)
        self.assertNotEqual(async_rejected.returncode, 0)

        cases = []

        changed = copy.deepcopy(payload)
        changed["result"]["schema_version"] = "spatial-agent.result-envelope.v999"
        cases.append(("unknown result version", changed))

        changed = copy.deepcopy(payload)
        changed["result"].pop("type")
        cases.append(("missing result type", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["workspace"]["schema_version"] = "spatial-agent.workspace.v999"
        cases.append(("unknown workspace version", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["workspace"].pop("panels")
        cases.append(("missing workspace panels", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["views"]["schema_version"] = "spatial-agent.views.v999"
        cases.append(("unknown views version", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["views"].pop("panels")
        cases.append(("missing views panels", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["workspace"]["view_specs"][0]["schema_version"] = (
            "spatial-agent.view.v999"
        )
        cases.append(("unknown view version", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["workspace"]["view_specs"][0].pop("renderer")
        cases.append(("missing view renderer", changed))

        changed = copy.deepcopy(payload)
        panel = changed["result"]["views"]["panels"]["raster"]
        panel["schema_version"] = "spatial-agent.panel.v999"
        cases.append(("unknown panel version", changed))

        changed = copy.deepcopy(payload)
        changed["result"]["views"]["panels"]["raster"].pop("kind")
        cases.append(("missing panel kind", changed))

        for name, invalid in cases:
            with self.subTest(name=name):
                rejected = self._run_offline_acceptance(invalid)
                self.assertNotEqual(
                    rejected.returncode,
                    0,
                    "production gate accepted " + name,
                )

    def test_dev_http_run_and_artifact_keep_the_same_nested_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ArtifactStore(root)

            class TestHandler(AgentApiHandler):
                service = AgentService(artifact_store=store)
                artifact_root = root
                geojson_root = root / "geojson"

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, http_payload = _post(
                    server.server_address[1],
                    "/runs",
                    {
                        "request": "查询DEM栅格元数据",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(http_payload["status"], "COMPLETED")
                artifact_name = Path(http_payload["artifact_ref"]).name
                artifact_status, http_artifact = _get(
                    server.server_address[1],
                    "/artifacts/runs/" + artifact_name,
                )
                self.assertEqual(artifact_status, 200)
                self.assertEqual(
                    _nested_projection(http_payload),
                    _nested_projection(http_artifact),
                )
                self.assertEqual(
                    http_payload["result"]["views"],
                    http_artifact["result"]["views"],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TestHandler.service.close()

    def test_fastapi_route_matches_dev_nested_projection_when_available(self):
        try:
            import production_api
        except (ImportError, ModuleNotFoundError) as exc:
            self.skipTest(
                "FastAPI production entry unavailable; nested HTTP test skipped: "
                + str(exc)
            )

        with tempfile.TemporaryDirectory() as directory:
            replacement = AgentService(artifact_store=ArtifactStore(directory))
            original = production_api.service
            production_api.service = replacement
            try:
                route_payload = production_api.run(
                    {
                        "request": "查询DEM栅格元数据",
                        "planner": "rule",
                        "backend": "memory",
                    }
                )
                expected = replacement.run(
                    "查询DEM栅格元数据",
                    planner="rule",
                    backend="memory",
                )
            finally:
                production_api.service = original
                replacement.close()

        self.assertEqual(route_payload["status"], "COMPLETED")
        self.assertEqual(
            _nested_projection(route_payload), _nested_projection(expected)
        )


if __name__ == "__main__":
    unittest.main()
