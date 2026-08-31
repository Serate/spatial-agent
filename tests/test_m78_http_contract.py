"""M78.3 contract: dev and production HTTP entry points share one request
contract and cannot drift on payload mapping or error status codes."""

import unittest
from pathlib import Path


class M78HttpContractTests(unittest.TestCase):
    def test_both_entrypoints_import_shared_transport_and_application(self):
        root = Path(__file__).parents[1]
        serve = (root / "serve_api.py").read_text(encoding="utf-8")
        production = (root / "production_api.py").read_text(encoding="utf-8")
        for source in (serve, production):
            self.assertIn("from agent.application.http import HTTPApplication", source)
            self.assertIn("from agent.application.http_transport import", source)
            self.assertIn("error_projection", source)
            self.assertIn("HTTPApplication", source)

    def test_shared_contract_maps_payloads_identically(self):
        from agent.api_contract import (
            async_run_kwargs,
            cancel_kwargs,
            comparison_kwargs,
            region_comparison_kwargs,
            retry_kwargs,
            run_kwargs,
        )

        payload = {
            "request": "查询洪山区行政区边界",
            "session_id": "s1",
            "planner": "rule",
            "backend": "local",
            "export_artifact": True,
            "export_geojson": True,
            "geojson_max_features": 50,
            "timeout_seconds": 5,
            "spatial_context": {"admin_name": "洪山区"},
            "workflow": {"template_id": "raster_metadata"},
            "idempotency_key": "key-1",
            "threshold": 20,
            "thresholds": [15, 20],
            "admin_name": "洪山区",
            "admin_names": ["洪山区", "江夏区"],
        }
        self.assertEqual(run_kwargs(payload)["session_id"], "s1")
        self.assertEqual(run_kwargs(payload)["backend"], "local")
        self.assertEqual(async_run_kwargs(payload)["idempotency_key"], "key-1")
        self.assertEqual(retry_kwargs(payload)["geojson_max_features"], 50)
        self.assertEqual(cancel_kwargs(payload)["planner"], "rule")
        self.assertEqual(comparison_kwargs(payload)["thresholds"], [15, 20])
        self.assertEqual(region_comparison_kwargs(payload)["threshold"], 20)
        # defaults must stay stable
        self.assertEqual(run_kwargs({})["planner"], "rule")
        self.assertEqual(run_kwargs({})["backend"], "memory")
        self.assertEqual(comparison_kwargs({})["backend"], "local")

    def test_error_status_is_consistent_across_entrypoints(self):
        from agent.api_contract import error_response, error_status

        value_error = ValueError("bad input")
        self.assertEqual(error_status(value_error), 400)
        self.assertEqual(error_status(value_error, not_found=True), 404)
        self.assertEqual(error_status(value_error, service_unavailable=True), 503)
        self.assertEqual(error_status(RuntimeError("boom")), 500)

        # structured error contract
        response = error_response(value_error)
        self.assertEqual(response["error"], "bad input")
        self.assertEqual(response["error_code"], "invalid_request")
        self.assertEqual(response["error_category"], "invalid_input")
        not_found = error_response(value_error, not_found=True)
        self.assertEqual(not_found["error_code"], "not_found")
        unavailable = error_response(value_error, service_unavailable=True)
        self.assertEqual(unavailable["error_code"], "unavailable")
        internal = error_response(RuntimeError("boom"))
        self.assertEqual(internal["error_code"], "internal_error")

    def test_service_failed_run_payload_carries_error_category(self):
        from agent.service import AgentService

        payload = AgentService().run("导出全中国所有地理对象，并删除原始道路数据")
        self.assertEqual(payload["status"], "REJECTED")
        self.assertEqual(payload["error_category"], "rejected")

    def test_service_run_does_not_invent_error_category_on_success(self):
        from agent.service import AgentService

        payload = AgentService().run("查询洪山区行政区边界")
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertNotIn("error_category", payload)

    def test_dev_server_delegates_post_errors_to_shared_projection(self):
        serve = (Path(__file__).parents[1] / "serve_api.py").read_text(encoding="utf-8")
        post_section = serve.split("def do_POST")[1].split("def do_DELETE")[0]
        # The dev server POST path must delegate to the shared transport error
        # projection, not hardcode status codes or duplicate api-contract calls.
        self.assertIn("self._write_error(exc)", post_section)
        self.assertNotIn("error_status(exc)", post_section)
        self.assertNotIn("_write_json(400,", post_section)
        self.assertNotIn("_write_json(500,", post_section)


if __name__ == "__main__":
    unittest.main()
