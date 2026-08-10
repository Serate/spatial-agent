import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.workflow_templates import (
    WorkflowTemplateError,
    normalize_workflow_constraints,
    normalize_workflow_evidence,
    revise_workflow_plan,
    validate_workflow_plan,
    get_workflow_template,
)
from serve_api import AgentApiHandler


def _plan():
    return {
        "template_id": "constrained_buildability",
        "goal": "筛选建设候选区域",
        "constraints": {
            "admin_name": "洪山区",
            "slope_limit_degrees": 20,
        },
        "evidence": ["summary", "geometry", "trace"],
        "steps": [
            {
                "id": "health",
                "tool": "get_dataset_health_report",
                "args": {"dataset": "all", "max_files": 3},
                "depends_on": [],
            },
            {
                "id": "screen",
                "tool": "get_zonal_constrained_buildability_analysis",
                "args": {
                    "admin_name": "洪山区",
                    "slope_limit_degrees": 20,
                    "road_distance_m": 1000,
                    "exclude_water": True,
                },
                "depends_on": ["health"],
            },
        ],
        "output": {"type": "constrained_buildability_result", "summary": True},
    }


class M69WorkflowContractTests(unittest.TestCase):
    def test_builtin_templates_are_versioned_and_editable(self):
        template = get_workflow_template("constrained_buildability")
        self.assertEqual(template["version"], "1.0.0")
        self.assertEqual(template["constraint_specs"][1]["type"], "number")
        self.assertIn("geometry", template["evidence_options"])

    def test_constraints_are_typed_bounded_and_defaulted(self):
        template = get_workflow_template("constrained_buildability")
        normalized = normalize_workflow_constraints(
            template,
            {"admin_name": " 洪山区 ", "slope_limit_degrees": 20},
        )
        self.assertEqual(normalized["admin_name"], "洪山区")
        self.assertEqual(normalized["road_distance_m"], 1000.0)
        self.assertTrue(normalized["exclude_water"])
        with self.assertRaisesRegex(WorkflowTemplateError, "maximum"):
            normalize_workflow_constraints(
                template,
                {"admin_name": "洪山区", "slope_limit_degrees": 91},
            )

    def test_unknown_evidence_and_constraints_are_rejected(self):
        template = get_workflow_template("spatial_overview")
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown constraints"):
            normalize_workflow_constraints(
                template,
                {"admin_name": "洪山区", "not_allowed": True},
            )
        with self.assertRaisesRegex(WorkflowTemplateError, "unknown evidence"):
            normalize_workflow_evidence(template, ["summary", "raw_database"])

    def test_plan_validation_emits_version_constraints_and_evidence(self):
        plan = validate_workflow_plan("constrained_buildability", _plan())
        self.assertEqual(plan["template_version"], "1.0.0")
        self.assertEqual(plan["constraints"]["slope_limit_degrees"], 20.0)
        self.assertEqual(plan["evidence"], ["summary", "geometry", "trace"])

    def test_revision_merges_only_declared_constraint_changes(self):
        revised = revise_workflow_plan(
            "constrained_buildability",
            _plan(),
            constraints={"slope_limit_degrees": 15, "road_distance_m": 500},
            evidence=["summary", "data_health"],
        )
        self.assertEqual(revised["constraints"]["slope_limit_degrees"], 15.0)
        self.assertEqual(revised["constraints"]["road_distance_m"], 500.0)
        self.assertEqual(revised["evidence"], ["summary", "data_health"])

    def test_http_validate_and_revise_endpoints(self):
        class TestHandler(AgentApiHandler):
            service = AgentApiHandler.service

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            validated = _post_json(
                server.server_address[1],
                {
                    "constraints": {"admin_name": "洪山区", "slope_limit_degrees": 20},
                    "evidence": ["summary", "geometry"],
                },
                "/workflows/constrained_buildability/validate",
            )
            revised = _post_json(
                server.server_address[1],
                {
                    "plan": _plan(),
                    "constraints": {"slope_limit_degrees": 15},
                    "evidence": ["summary", "data_health"],
                },
                "/workflows/constrained_buildability/revise",
            )
            invalid = _post_json(
                server.server_address[1],
                {"constraints": {"admin_name": "洪山区", "slope_limit_degrees": 100}},
                "/workflows/constrained_buildability/validate",
                expected_status=400,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(validated["valid"])
        self.assertEqual(validated["constraints"]["slope_limit_degrees"], 20.0)
        self.assertEqual(revised["plan"]["constraints"]["slope_limit_degrees"], 15.0)
        self.assertIn("maximum", invalid["error"])


def _post_json(port, payload, path, expected_status=200):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        if response.status != expected_status:
            raise AssertionError(data)
        return data
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
