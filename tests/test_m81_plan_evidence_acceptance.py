import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.service import AgentService
from evaluation.model_evaluation import evaluate_model_fixture_file
from serve_api import AgentApiHandler


ROOT = Path(__file__).parents[1]
COMPLEX_REQUEST = (
    "请对洪山区进行综合空间分析：查询行政区边界，统计DEM高程与坡度，"
    "分析土地利用分布，汇总道路和水体，并筛选坡度不超过20度、"
    "距离道路不超过1000米且排除水体的建设候选区域。"
)


class M81PlanEvidenceAcceptanceTests(unittest.TestCase):
    def test_preview_envelope_matches_direct_service_and_http_entry(self):
        request_payload = {
            "request": COMPLEX_REQUEST,
            "session_id": "preview-cross-entry",
            "planner": "rule",
            "backend": "memory",
        }
        direct = AgentService().preview(**request_payload)

        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            http = _post_json(server.server_address[1], request_payload, "/runs/preview")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        fields = (
            "status",
            "result_type",
            "plan",
            "dag",
            "context_evidence",
            "plan_evidence",
            "execution",
            "spatial_context",
        )
        self.assertEqual({field: direct.get(field) for field in fields}, {field: http.get(field) for field in fields})
        self.assertNotIn("run_id", direct)
        self.assertNotIn("artifact_ref", http)

        production_source = (ROOT / "production_api.py").read_text(encoding="utf-8")
        self.assertIn('@app.post("/runs/preview")', production_source)
        self.assertIn("service.preview(**preview_kwargs(payload))", production_source)

    def test_spatial_analysis_model_fixture_matches_exact_blueprint(self):
        report = evaluate_model_fixture_file(ROOT / "tests" / "fixtures" / "m81_spatial_analysis_model.json")

        self.assertTrue(report["passed"])
        self.assertEqual(report["status"], "COMPLETED")
        quality = report["plan_quality"]
        self.assertTrue(quality["workflow_template_match"]["passed"])
        self.assertIn("spatial_analysis", quality["workflow_template_match"]["exact_template_ids"])
        self.assertEqual(len(report["actual_tools"]), 9)
        self.assertEqual(report["safety"]["token_usage"]["total_tokens"], 2990)

    def test_service_preview_returns_complex_dag_without_execution_artifacts(self):
        payload = AgentService().preview(
            COMPLEX_REQUEST,
            session_id="preview-complex",
            planner="rule",
            backend="memory",
        )

        self.assertEqual(payload["status"], "PLANNED")
        self.assertEqual(payload["result_type"], "spatial_analysis_result")
        self.assertEqual(len(payload["plan"]["steps"]), 9)
        self.assertEqual(payload["dag"]["node_count"], 9)
        self.assertEqual(payload["dag"]["edge_count"], 8)
        self.assertNotIn("run_id", payload)
        self.assertNotIn("artifact_ref", payload)
        self.assertNotIn("steps", payload)
        self.assertEqual(
            payload["execution"],
            {"planned_only": True, "tool_execution": False, "artifact_export": False},
        )

    def test_http_result_and_artifact_share_template_planning_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            local_artifact_root = Path(directory) / "runs"
            local_geojson_root = Path(directory) / "geojson"

            class TestHandler(AgentApiHandler):
                service = AgentService(artifact_store=ArtifactStore(str(local_artifact_root)))
                artifact_root = local_artifact_root
                geojson_root = local_geojson_root

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                run = _post_json(
                    server.server_address[1],
                    {
                        "request": "查询洪山区行政区边界",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                    "/runs",
                )
                artifact_name = Path(run["artifact_ref"]).name
                artifact = _get_json(
                    server.server_address[1],
                    "/artifacts/runs/" + artifact_name,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                TestHandler.service._async_executor.shutdown(wait=True)

        evidence = run["plan_evidence"]
        planning = run["result"]["planning"]
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(planning["source"], evidence["source"])
        self.assertEqual(planning["planner_kind"], evidence["planner_kind"])
        self.assertTrue(planning["template_context_available"])
        self.assertIn("admin_boundary_query", planning["matched_template_ids"])
        self.assertIn("admin_boundary_query", planning["exact_template_ids"])
        self.assertEqual(
            artifact["plan_evidence"]["exact_template_ids"],
            planning["exact_template_ids"],
        )

    def test_complex_request_has_consistent_contract_across_service_http_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            local_artifact_root = Path(directory) / "runs"
            direct_service = AgentService(artifact_store=ArtifactStore(str(local_artifact_root)))
            direct = direct_service.run(
                COMPLEX_REQUEST,
                session_id="direct-complex",
                planner="rule",
                backend="memory",
                export_artifact=True,
            )

            class TestHandler(AgentApiHandler):
                service = AgentService(artifact_store=ArtifactStore(str(local_artifact_root)))
                artifact_root = local_artifact_root

            server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                http_run = _post_json(
                    server.server_address[1],
                    {
                        "request": COMPLEX_REQUEST,
                        "session_id": "http-complex",
                        "planner": "rule",
                        "backend": "memory",
                        "export_artifact": True,
                    },
                    "/runs",
                )
                http_detail = _get_json(
                    server.server_address[1],
                    "/runs/" + http_run["run_id"] + "?planner=rule&backend=memory",
                )
                history = _get_json(
                    server.server_address[1],
                    "/sessions/http-complex/runs",
                )
                artifact_name = Path(http_run["artifact_ref"]).name
                artifact = _get_json(
                    server.server_address[1],
                    "/artifacts/runs/" + artifact_name,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                direct_service._async_executor.shutdown(wait=True)
                TestHandler.service._async_executor.shutdown(wait=True)

        self.assertEqual(_normalized_contract(direct), _normalized_contract(http_run))
        self.assertEqual(_normalized_contract(http_run), _normalized_contract(http_detail))
        self.assertIn("spatial_analysis", http_run["plan_evidence"]["exact_template_ids"])
        self.assertIn("spatial_analysis", http_run["result"]["planning"]["exact_template_ids"])
        self.assertEqual(artifact["plan_evidence"], http_run["plan_evidence"])
        self.assertEqual(history["runs"][0]["lineage"]["run_id"], http_run["run_id"])

    def test_console_uses_result_planning_evidence(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("const planEvidence=envelope.planning||data.plan_evidence||{}", source)
        self.assertIn("计划来源", source)
        self.assertIn("exact_template_ids", source)
        self.assertIn("/runs/preview", source)
        self.assertIn("renderPlanDag", source)
        self.assertIn("planPreview", source)

    def test_http_preview_route_returns_planned_only_payload(self):
        class TestHandler(AgentApiHandler):
            service = AgentService()

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = _post_json(
                server.server_address[1],
                {
                    "request": "查询洪山区行政区边界",
                    "session_id": "preview-http",
                    "planner": "rule",
                    "backend": "memory",
                },
                "/runs/preview",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(payload["status"], "PLANNED")
        self.assertEqual(payload["result_type"], "admin_area_result")
        self.assertNotIn("run_id", payload)
        self.assertNotIn("artifact_ref", payload)
        self.assertFalse(payload["execution"]["tool_execution"])


def _get_json(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(payload)
        return payload
    finally:
        connection.close()


def _post_json(port, payload, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise AssertionError(payload)
        return payload
    finally:
        connection.close()


def _normalized_contract(payload):
    return {
        "status": payload["status"],
        "result_type": payload["result"]["type"],
        "result_title": payload["result"]["title"],
        "planning_source": payload["result"]["planning"]["source"],
        "exact_templates": payload["result"]["planning"]["exact_template_ids"],
        "matched_templates": payload["result"]["planning"]["matched_template_ids"],
        "step_tools": [step["tool"] for step in payload["steps"]],
        "step_statuses": [step["status"] for step in payload["steps"]],
        "trace_step_count": len(payload["trace_summary"]),
        "artifact_available": payload["result"]["lineage"]["artifact"]["available"],
        "answer_has_summary": "已完成 9 个工具步骤" in payload.get("answer", ""),
    }


if __name__ == "__main__":
    unittest.main()
