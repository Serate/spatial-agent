import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent.application.http import HTTPApplication
from agent.answer_generation import (
    LLMCompositeAnswerGenerator,
    fallback_composite_answer,
)
from agent.application.composite_contract import build_composite_result_contract
from agent.application.composite_view import build_composite_view_projection


def _request():
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "组合空间与指标分析",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "request": "查询空间结果",
                "planner": "rule",
                "backend": "memory",
            },
            {
                "component_id": "metrics",
                "domain_id": "economic",
                "request": "查询指标结果",
                "planner": "rule",
                "backend": "memory",
            },
        ],
    }


def _children():
    return {
        "space": {
            "domain_id": "gis",
            "status": "COMPLETED",
            "result": {
                "type": "vector_result",
                "data_profile": {"primary": "vector", "kinds": ["vector"]},
                "answer": "空间结果已生成。",
                "views": {
                    "panels": {
                        "map": {
                            "kind": "map",
                            "title": "空间结果",
                            "features": [{"type": "Feature", "geometry": None}],
                        }
                    }
                },
            },
        },
        "metrics": {
            "domain_id": "economic",
            "status": "COMPLETED",
            "result": {
                "type": "metrics_result",
                "data_profile": {"primary": "metrics", "kinds": ["metrics"]},
                "answer": "指标结果已生成。",
                "views": {"panels": {"table": {"kind": "table", "rows": [{"value": 1}]}}},
            },
        },
    }


class _Runs:
    def __init__(self, projection):
        self.projection = projection

    def get_view(self, run_id):
        self.projection["run_id"] = run_id
        return self.projection


class _AnswerClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, schema):
        return self.payload

    def metrics(self):
        return {"execution_mode": "live_model", "provider": "test"}


class M281DynamicCompositeViewTests(unittest.TestCase):
    def test_projection_is_profile_driven_and_bounded(self):
        result = build_composite_result_contract(
            _request(), _children(), run_id="composite-m281", answer="已完成空间与指标分析。"
        )
        projection = build_composite_view_projection(result)

        self.assertEqual(projection["schema_version"], "spatial-agent.composite-view.v1")
        self.assertEqual(projection["state"], "completed")
        self.assertEqual(projection["answer"]["headline"], "组合分析已完成")
        self.assertEqual(
            {view["kind"] for view in projection["views"]}, {"composite", "map", "table"}
        )
        self.assertEqual(
            {section["kind"] for section in projection["sections"]}, {"summary", "component"}
        )
        encoded = json.dumps(projection, ensure_ascii=False)
        self.assertNotIn("prompt", encoded.lower())
        self.assertLess(len(encoded.encode("utf-8")), 2_000_000)

    def test_partial_result_has_readable_limitation_and_same_projection_entry(self):
        children = _children()
        children["metrics"]["status"] = "FAILED"
        children["metrics"]["error"] = "指标数据暂不可用"
        request = _request()
        request["components"][1]["required"] = False
        result = build_composite_result_contract(request, children, run_id="partial-m281")
        projection = build_composite_view_projection(result)

        self.assertEqual(projection["state"], "partial")
        self.assertTrue(projection["answer"]["limitations"])
        response = HTTPApplication(object(), composite=_Runs(projection)).read(
            "composite_view", resource_id="run-1"
        )
        self.assertEqual(response["run_id"], "run-1")
        self.assertEqual(response["request_fingerprint"], projection["request_fingerprint"])

    def test_structured_answer_can_override_fallback_without_changing_facts(self):
        result = build_composite_result_contract(_request(), _children(), run_id="answer-m281")
        generated = LLMCompositeAnswerGenerator(
            _AnswerClient(
                {
                    "answer": {
                        "headline": "空间与指标分析已完成",
                        "summary": "两个分析组件均返回了结果。",
                        "key_findings": ["空间结果已生成。", "指标结果已生成。"],
                        "limitations": [],
                    }
                }
            )
        ).generate(result)
        projection = build_composite_view_projection(result, answer=generated.answer)
        fallback = fallback_composite_answer(result, "model_unavailable")

        self.assertEqual(projection["state"], "completed")
        self.assertEqual(projection["request_fingerprint"], result["composite"]["request"]["fingerprint"])
        self.assertEqual(projection["answer"]["headline"], "空间与指标分析已完成")
        self.assertEqual(generated.evidence["status"], "success")
        self.assertEqual(fallback.evidence["status"], "fallback")

    def test_view_is_available_through_stdlib_and_fastapi_entrypoints(self):
        import production_api
        import serve_api

        result = build_composite_result_contract(_request(), _children(), run_id="routes-m281")
        projection = build_composite_view_projection(result)
        original_production = production_api.composite_application
        original_serve = serve_api.composite_application
        serve_api.composite_application = _Runs(projection)
        production_api.composite_application = _Runs(projection)

        class Handler(serve_api.AgentApiHandler):
            pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            connection.request("GET", "/composite-runs/routes-m281/view")
            response = connection.getresponse()
            stdlib_view = json.loads(response.read().decode("utf-8"))
            connection.close()
            fastapi_view = production_api.composite_view("routes-m281")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            production_api.composite_application = original_production
            serve_api.composite_application = original_serve

        self.assertEqual(response.status, 200)
        self.assertEqual(stdlib_view["schema_version"], "spatial-agent.composite-view.v1")
        self.assertEqual(fastapi_view["request_fingerprint"], stdlib_view["request_fingerprint"])
        self.assertEqual(
            [item["view_id"] for item in fastapi_view["views"]],
            [item["view_id"] for item in stdlib_view["views"]],
        )

    def test_frontend_consumes_projection_without_domain_specific_branch(self):
        root = Path(__file__).parents[1]
        registry = (root / "web" / "src" / "console_renderer_registry.js").read_text(
            encoding="utf-8"
        )
        app = (root / "web" / "src" / "console_app.js").read_text(encoding="utf-8")
        self.assertIn("projectionToPanels", registry)
        self.assertIn("spatial-agent.composite-view.v1", registry)
        self.assertIn("compositeViewProjection", app)
        self.assertIn("rendererRegistry.projectionToPanels", app)
        self.assertNotIn("domain_id === 'gis'", app)
        self.assertNotIn('domain_id === "gis"', app)


if __name__ == "__main__":
    unittest.main()
