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


def _complex_result_projection(payload):
    result = payload.get("result") if isinstance(payload, dict) else {}
    result = result if isinstance(result, dict) else {}
    plan = payload.get("plan") if isinstance(payload, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    steps = payload.get("steps") if isinstance(payload, dict) else []
    steps = steps if isinstance(steps, list) else []
    registry = payload.get("evidence_registry") or result.get("evidence_registry")
    registry = registry if isinstance(registry, dict) else {}
    return {
        "status": payload.get("status"),
        "result_type": result.get("type") or payload.get("result_type") or (plan.get("output") or {}).get("type"),
        "tools": [item.get("tool") for item in steps if isinstance(item, dict)],
        "evidence_entry_ids": [
            item.get("id") for item in registry.get("entries", []) if isinstance(item, dict)
        ],
    }


def _request_json(port, method, path, payload=None, *, timeout=5):
    connection = HTTPConnection("127.0.0.1", port, timeout=timeout)
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
    def test_complex_local_gis_result_and_evidence_survive_all_entries(self):
        request = "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、距离道路不超过1000米且排除水体的建设候选区域。"
        expected_tools = [
            "get_dataset_health_report",
            "get_dataset_schema",
            "range_query",
            "get_zonal_raster_statistics",
            "get_zonal_slope_statistics",
            "get_zonal_land_use_distribution",
            "get_zonal_vector_summary",
            "get_zonal_vector_summary",
            "get_zonal_constrained_buildability_analysis",
        ]
        with tempfile.TemporaryDirectory(prefix="m200-complex-cross-entry-") as directory:
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
                    "request": request,
                    "session_id": "m200-complex-http",
                    "planner": "rule",
                    "backend": "local",
                    "export_artifact": True,
                    "export_geojson": True,
                }
                http_result = _request_json(server.server_address[1], "POST", "/runs", payload, timeout=30)
                http_detail = _request_json(
                    server.server_address[1], "GET", "/runs/" + http_result["run_id"], timeout=30
                )
                sync_artifact = store.read_run(http_result["run_id"], domain_id="gis")
                submitted = service.run_async(
                    request=request,
                    session_id="m200-complex-async",
                    planner="rule",
                    backend="local",
                    export_artifact=True,
                    export_geojson=True,
                    idempotency_key="m200-complex-async",
                )
                async_result = _wait_for_terminal(service, submitted["run_id"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.close()

            restarted = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
                domain_pack=GIS_DOMAIN_PACK,
            )
            try:
                recovered = restarted.get_run(submitted["run_id"], planner="rule", backend="local")
                async_artifact = store.read_run(submitted["run_id"], domain_id="gis")
            finally:
                restarted.close()

        for item in (http_result, http_detail, sync_artifact, async_result, recovered, async_artifact):
            self.assertEqual(_complex_result_projection(item)["status"], "COMPLETED")
            self.assertEqual(_complex_result_projection(item)["result_type"], "spatial_analysis_result")
            self.assertEqual(_complex_result_projection(item)["tools"], expected_tools)
        projections = [
            _complex_result_projection(item)
            for item in (http_result, http_detail, sync_artifact, async_result, recovered, async_artifact)
        ]
        self.assertEqual({tuple(item["evidence_entry_ids"]) for item in projections}, {
            ("result", "plan_quality", "execution_timeline", "action_lifecycle", "replanning", "workflow_selection", "planner_selection")
        })

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
