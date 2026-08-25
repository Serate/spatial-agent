import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from agent.application.composite_planning import CompositeCapabilityProjector
from agent.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
    RuleCompositePlanner,
    composite_plan_schema,
)
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.http import HTTPApplication


class _Service:
    def __init__(self, capabilities, workflows):
        self._capabilities = capabilities
        self._workflows = workflows

    def capabilities(self, planner="rule", backend="memory"):
        return self._capabilities

    def workflow_contract(self, planner="rule", backend="memory"):
        return {
            "domain_id": self._capabilities["domain_id"],
            "catalog": self._workflows,
            "known_tools": ["tool-a"],
            "known_result_types": ["result-a"],
        }


class _Host:
    def __init__(self, services):
        self._services = services

    def catalog(self):
        return {
            "schema_version": "spatial-agent.domain-runtime-host.v1",
            "domain_ids": sorted(self._services),
            "domains": [
                {
                    "id": domain_id,
                    "label": domain_id.upper(),
                    "description": "bounded domain",
                }
                for domain_id in sorted(self._services)
            ],
        }

    def select(self, domain_id, *, source="explicit"):
        if domain_id not in self._services:
            raise ValueError("unknown domain")
        return domain_id

    def service(self, selection):
        return self._services[selection]


def _service(domain_id, *, available=True):
    return _Service(
        {
            "schema_version": "spatial-agent.capability-catalog-context.v1",
            "domain_id": domain_id,
            "environment": "memory",
            "data_readiness": {"status": "ready" if available else "partial"},
            "capabilities": [
                {
                    "id": domain_id + "_summary",
                    "label": "摘要",
                    "description": "safe description",
                    "datasets": [domain_id + "_data"],
                    "tools": ["tool-a"],
                    "result_types": ["result-a"],
                    "available": available,
                    "availability_mode": "demo" if available else "unavailable",
                    "availability_reason": "ready" if available else "missing",
                    "missing_datasets": [] if available else [domain_id + "_data"],
                    "request_requirements": {"entities": ["region"]},
                    "source_path": "D:/private/should-not-leak",
                    "secret": "should-not-leak",
                }
            ],
            "private_payload": {"token": "should-not-leak"},
        },
        {
            domain_id + "_workflow": {
                "id": domain_id + "_workflow",
                "label": "工作流",
                "description": "safe workflow",
                "allowed_tools": ["tool-a"],
                "result_types": ["result-a"],
                "step_blueprint": [
                    {"id": "step-1", "tool": "tool-a", "args": {"path": "private"}}
                ],
            }
        },
    )


def _plan_payload(outcome="success"):
    if outcome != "success":
        return {
            "outcome": outcome,
            "goal": "",
            "message": "请补充区域和时间范围",
            "components": [],
        }
    return {
        "outcome": "success",
        "goal": "组合空间与指标分析",
        "message": "",
        "components": [
            {
                "component_id": "space",
                "domain_id": "gis",
                "capability_id": "gis_summary",
                "request": "查询空间摘要",
                "depends_on": [],
                "required": True,
            },
            {
                "component_id": "economy",
                "domain_id": "economic",
                "capability_id": "economic_summary",
                "request": "查询经济摘要",
                "depends_on": [],
                "required": True,
            },
        ],
    }


class _LLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, messages, schema, *, schema_name=None):
        self.calls.append((messages, schema, schema_name))
        return self.payload


class _Planner:
    def __init__(self, payload):
        self.payload = payload
        self.context = None

    def plan(self, request, *, context=None):
        self.context = context
        return {
            "schema_version": "spatial-agent.composite-planning-response.v1",
            "status": "PLANNED",
            "planner_source": "fake",
            "goal": "组合分析",
            "message": "",
            "components": self.payload["components"],
            "request": self.payload,
            "validation": {"status": "valid"},
        }


class _Runs:
    def __init__(self):
        self.calls = []

    def submit_async(self, request, **kwargs):
        self.calls.append(("async", request, kwargs))
        return {"run_id": "planned-1", "status": "QUEUED", "reused": False}

    def run(self, request, **kwargs):
        self.calls.append(("sync", request, kwargs))
        return {"run_id": "planned-1", "status": "COMPLETED", "result": {}}


class _Planning:
    def prepare(self, request, **kwargs):
        return {
            "schema_version": "spatial-agent.composite-planning-response.v1",
            "status": "PLANNED",
            "planner_source": "fake",
            "message": "",
            "components": [],
            "request": {"type": "composite_request"},
            "validation": {"status": "valid"},
        }


class M279CompositeCapabilityProjectionTests(unittest.TestCase):
    def test_projection_combines_domains_and_filters_private_fields(self):
        projector = CompositeCapabilityProjector(
            _Host({"economic": _service("economic"), "gis": _service("gis")})
        )

        projection = projector.project(domain_ids=["gis", "economic"])
        encoded = json.dumps(projection, ensure_ascii=False)

        self.assertEqual(projection["schema_version"], "spatial-agent.composite-planner-context.v1")
        self.assertEqual(projection["domain_ids"], ["economic", "gis"])
        self.assertEqual(
            {item["domain_id"] for item in projection["capability_index"]},
            {"economic", "gis"},
        )
        self.assertNotIn("source_path", encoded)
        self.assertNotIn("should-not-leak", encoded)
        self.assertNotIn("args", encoded)

    def test_projection_preserves_readiness_and_bounds_capabilities(self):
        projector = CompositeCapabilityProjector(
            _Host({"gis": _service("gis", available=False)})
        )

        projection = projector.project(domain_ids=["gis"], max_capabilities=1)
        domain = projection["domains"][0]
        capability = domain["capabilities"][0]

        self.assertEqual(domain["data_readiness"]["status"], "partial")
        self.assertFalse(capability["available"])
        self.assertEqual(capability["missing_datasets"], ["gis_data"])
        self.assertLessEqual(
            len(json.dumps(projection, ensure_ascii=False).encode("utf-8")),
            24000,
        )

    def test_unknown_domain_is_rejected_before_service_access(self):
        projector = CompositeCapabilityProjector(_Host({"gis": _service("gis")}))

        with self.assertRaisesRegex(ValueError, "unknown domain"):
            projector.project(domain_ids=["not-registered"])


class M279CompositePlannerContractTests(unittest.TestCase):
    def test_rule_and_llm_planners_share_one_normalized_request_contract(self):
        payload = _plan_payload()
        request = "请组合分析空间与经济指标"
        context = {"schema_version": "spatial-agent.composite-planner-context.v1"}

        rule = RuleCompositePlanner(lambda _request, _context: payload)
        rule_result = rule.plan(request, context=context)

        client = _LLMClient(payload)
        llm = LLMCompositePlanner(client)
        llm_result = llm.plan(request, context=context)

        self.assertEqual(rule_result["status"], "PLANNED")
        self.assertEqual(llm_result["status"], "PLANNED")
        self.assertEqual(
            rule_result["request"]["fingerprint"],
            llm_result["request"]["fingerprint"],
        )
        self.assertEqual(rule_result["components"][0]["capability_id"], "gis_summary")
        self.assertNotIn("capability_id", rule_result["request"]["components"][0])
        self.assertEqual(client.calls[0][1], composite_plan_schema())

    def test_clarification_is_structured_and_invalid_plan_is_rejected(self):
        clarification = RuleCompositePlanner(
            lambda _request, _context: _plan_payload("needs_clarification")
        ).plan("分析最近发展", context={})
        self.assertEqual(clarification["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(clarification["components"], [])

        invalid = _plan_payload()
        invalid["components"][0]["unexpected"] = "reject"
        with self.assertRaises(CompositePlannerError) as error:
            RuleCompositePlanner(lambda _request, _context: invalid).plan(
                "组合分析", context={}
            )
        self.assertEqual(error.exception.code, "plan_component_field_invalid")

    def test_provider_error_is_bounded(self):
        class FailingClient:
            def complete_json(self, messages, schema, *, schema_name=None):
                raise RuntimeError("provider secret response")

        with self.assertRaises(CompositePlannerError) as error:
            LLMCompositePlanner(FailingClient()).plan("组合分析", context={})
        self.assertEqual(error.exception.code, "planner_provider_failed")
        self.assertNotIn("provider secret", str(error.exception))

    def test_application_can_prepare_without_execution_and_submit_canonical_request(self):
        host = _Host({"gis": _service("gis")})
        projector = CompositeCapabilityProjector(host)
        candidate = _plan_payload()
        # Keep this application test focused on orchestration; the planner
        # contract test above owns candidate normalization details.
        candidate["components"] = [
            {
                "component_id": "space",
                "domain_id": "gis",
                "capability_id": "gis_summary",
                "request": "查询空间摘要",
                "depends_on": [],
                "required": True,
            }
        ]
        canonical = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合空间分析",
            "components": [
                {
                    "component_id": "space",
                    "domain_id": "gis",
                    "request": "查询空间摘要",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }
        planner = _Planner({**canonical, "components": candidate["components"]})
        runs = _Runs()
        application = CompositePlanningApplication(
            host=host,
            projector=projector,
            planner=planner,
            composite_runs=runs,
        )

        preview = application.prepare("组合空间分析", domain_ids=["gis"])
        submitted = application.submit(
            "组合空间分析",
            domain_ids=["gis"],
            session_id="m279-session",
            idempotency_key="m279-idem",
        )

        self.assertEqual(preview["status"], "PLANNED")
        self.assertIsNotNone(planner.context)
        self.assertEqual(submitted["status"], "QUEUED")
        self.assertEqual(submitted["run_id"], "planned-1")
        self.assertEqual(len(runs.calls), 1)
        self.assertEqual(runs.calls[0][0], "async")
        self.assertEqual(
            runs.calls[0][1]["schema_version"],
            "spatial-agent.composite-request.v1",
        )

    def test_application_returns_structured_clarification_without_creating_run(self):
        host = _Host({"gis": _service("gis")})
        runs = _Runs()

        class ClarifyingPlanner:
            def plan(self, request, *, context=None):
                return {
                    "status": "NEEDS_CLARIFICATION",
                    "planner_source": "fake",
                    "message": "请补充区域",
                    "components": [],
                    "request": None,
                    "validation": {"status": "not_run"},
                }

        application = CompositePlanningApplication(
            host=host,
            projector=CompositeCapabilityProjector(host),
            planner=ClarifyingPlanner(),
            composite_runs=runs,
        )
        result = application.submit("分析最近发展", domain_ids=["gis"])

        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(result["message"], "请补充区域")
        self.assertFalse(runs.calls)

    def test_http_application_exposes_one_composite_plan_command(self):
        host = _Host({"gis": _service("gis")})
        candidate = _plan_payload()
        candidate["components"] = [candidate["components"][0]]
        canonical = {
            "schema_version": "spatial-agent.composite-request.v1",
            "request": "组合空间分析",
            "components": [
                {
                    "component_id": "space",
                    "domain_id": "gis",
                    "request": "查询空间摘要",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }
        planner = _Planner({**canonical, "components": candidate["components"]})
        planning = CompositePlanningApplication(
            host=host,
            projector=CompositeCapabilityProjector(host),
            planner=planner,
            composite_runs=_Runs(),
        )
        response = HTTPApplication(object(), composite_planning=planning).execute(
            "composite_plan",
            {"request": "组合空间分析", "domain_ids": ["gis"]},
        )

        self.assertEqual(response["status"], "PLANNED")
        self.assertEqual(response["request"]["schema_version"], "spatial-agent.composite-request.v1")

    def test_fastapi_and_stdlib_routes_delegate_to_same_plan_command(self):
        import production_api
        import serve_api

        planning = _Planning()
        old_production = production_api.composite_planning_application
        old_serve = serve_api.composite_planning_application
        production_api.composite_planning_application = planning
        serve_api.composite_planning_application = planning

        class Handler(serve_api.AgentApiHandler):
            pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        try:
            connection.request(
                "POST",
                "/composite-plans",
                body=json.dumps({"request": "组合分析"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            stdlib_status = response.status
            stdlib_body = json.loads(response.read().decode("utf-8"))
            fastapi_body = production_api.composite_plan({"request": "组合分析"})
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            production_api.composite_planning_application = old_production
            serve_api.composite_planning_application = old_serve

        self.assertEqual(stdlib_status, 200)
        self.assertEqual(stdlib_body["status"], "PLANNED")
        self.assertEqual(fastapi_body["status"], "PLANNED")


if __name__ == "__main__":
    unittest.main()
