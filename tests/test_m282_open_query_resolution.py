import json
import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.application.http import HTTPApplication
from agent.application.composite_request_context import (
    CompositeRequestContextBuilder,
    CompositeRequestContextError,
)
from agent.application.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
    RuleCompositePlanner,
)


class _Service:
    def __init__(self, facts, discovery, *, discovery_error=False):
        self._facts = facts
        self._discovery = discovery
        self._discovery_error = discovery_error

    def extract_request_facts(self, request):
        return self._facts

    def discover(self, request, request_facts):
        if self._discovery_error:
            raise RuntimeError("private discovery failure")
        return self._discovery

    def select_workflow(self, discovery, request_facts, *, workflow=None):
        return {
            "source": "domain",
            "selected_capability_id": discovery.get("selected_capability_id"),
            "candidate_ids": discovery.get("candidate_ids", []),
            "candidate_count": len(discovery.get("candidate_ids", [])),
        }


class _Host:
    def __init__(self, services):
        self.services = services

    def catalog(self):
        return {
            "domain_ids": sorted(self.services),
            "domains": [{"id": domain_id} for domain_id in sorted(self.services)],
        }

    def select(self, domain_id, *, source="automatic"):
        if domain_id not in self.services:
            raise ValueError("unknown domain")
        return domain_id

    def service(self, selection):
        return self.services[selection]


class _Projector:
    def __init__(self, catalog):
        self.catalog = catalog

    def project(self, *, planner="rule", backend="memory", domain_ids=None):
        return self.catalog


def _facts(region="洪山区"):
    return {
        "schema_version": "spatial-agent.request-facts.v1",
        "entities": {"admin_name": region} if region else {},
        "datasets": ["roads"],
        "tasks": ["summary"],
        "constraints": {},
        "evidence": ["parser"],
        "source_path": "D:/private/not-public",
    }


def _capability(capability_id, *, requires_region=False, available=True):
    requirements = {
        "clarification_fields": (
            [{"id": "region", "label": "分析区域", "kind": "entity", "key": "admin_name"}]
            if requires_region
            else []
        )
    }
    return {
        "id": capability_id,
        "label": capability_id,
        "description": "bounded capability",
        "datasets": ["roads"],
        "result_types": ["metrics"],
        "available": available,
        "availability_reason": "ready" if available else "missing data",
        "request_requirements": requirements,
        "source_path": "D:/private/not-public",
    }


def _fixture(*, discovery_error=False, region="洪山区", requires_region=False):
    domain_ids = ["economic", "gis"]
    capabilities = {
        "economic": [_capability("economic.summary", requires_region=requires_region)],
        "gis": [_capability("gis.summary")],
    }
    services = {
        domain_id: _Service(
            _facts(region),
            {
                "schema_version": "discovery.v1",
                "selected_capability_id": capabilities[domain_id][0]["id"],
                "candidate_ids": [capabilities[domain_id][0]["id"]],
                "selection_state": "selected",
                "private_payload": {"token": "not-public"},
            },
            discovery_error=discovery_error,
        )
        for domain_id in domain_ids
    }
    catalog = {
        "schema_version": "catalog.v1",
        "domain_ids": domain_ids,
        "domains": [
            {
                "domain_id": domain_id,
                "capabilities": capabilities[domain_id],
                "data_readiness": {"status": "ready"},
            }
            for domain_id in domain_ids
        ],
    }
    return _Host(services), _Projector(catalog)


class M282ContextContractTests(unittest.TestCase):
    def test_aggregates_domain_facts_and_has_stable_fingerprint(self):
        host, projector = _fixture()
        builder = CompositeRequestContextBuilder(host=host, catalog_projector=projector)

        first = builder.build("分析洪山区经济和空间情况", domain_ids=["gis", "economic"])
        second = builder.build("分析洪山区经济和空间情况", domain_ids=["gis", "economic"])

        self.assertEqual(first["schema_version"], "spatial-agent.composite-request-context.v2")
        self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
        self.assertEqual({item["domain_id"] for item in first["domain_contexts"]}, {"gis", "economic"})
        self.assertEqual(len(first["capability_index"]), 2)
        self.assertEqual(first["clarification"]["state"], "not_required")

    def test_missing_domain_fact_is_structured_clarification(self):
        host, projector = _fixture(region=None, requires_region=True)
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析最近发展", domain_ids=["economic"]
        )

        self.assertEqual(context["clarification"]["state"], "required")
        self.assertEqual(context["clarification"]["reason_code"], "request_facts_missing")
        self.assertEqual(context["clarification"]["missing_by_domain"][0]["domain_id"], "economic")

    def test_discovery_failure_is_not_silent_success(self):
        host, projector = _fixture(discovery_error=True)
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析洪山区", domain_ids=["gis"]
        )

        self.assertEqual(context["domain_contexts"][0]["discovery"]["state"], "unavailable")
        self.assertEqual(context["clarification"]["state"], "unavailable")
        self.assertEqual(context["clarification"]["reason_code"], "discovery_unavailable")

    def test_ambiguous_candidates_do_not_union_unrelated_requirements(self):
        host, projector = _fixture()
        catalog = projector.catalog
        economic = next(item for item in catalog["domains"] if item["domain_id"] == "economic")
        economic["capabilities"].append(
            _capability("economic.no_region", requires_region=False)
        )
        host.services["economic"] = _Service(
            _facts(region=None),
            {
                "candidate_ids": ["economic.summary", "economic.no_region"],
                "selection_state": "ambiguous",
            },
        )

        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析最近发展", domain_ids=["economic"]
        )

        self.assertEqual(context["clarification"]["state"], "not_required")
        self.assertEqual(context["clarification"]["reason_code"], "facts_and_candidates_available")

    def test_private_fields_are_filtered_and_budget_is_enforced(self):
        host, projector = _fixture()
        builder = CompositeRequestContextBuilder(host=host, catalog_projector=projector)
        context = builder.build("分析洪山区", domain_ids=["gis"])
        encoded = json.dumps(context, ensure_ascii=False)

        self.assertNotIn("not-public", encoded)
        with self.assertRaises(CompositeRequestContextError) as error:
            CompositeRequestContextBuilder(
                host=host, catalog_projector=projector, max_bytes=200
            ).build("分析洪山区", domain_ids=["gis"])
        self.assertEqual(error.exception.code, "context_budget_exceeded")


class _FixedContext:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        return {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "context-fingerprint",
            "clarification": {"state": "not_required"},
            "capability_index": [
                {"domain_id": "gis", "capability_id": "gis.summary", "available": True}
            ],
        }


class _UnknownPlanner:
    def plan(self, request, *, context=None):
        return {
            "status": "PLANNED",
            "planner_source": "fake",
            "goal": "unknown capability",
            "components": [
                {
                    "component_id": "step",
                    "domain_id": "gis",
                    "capability_id": "gis.not-registered",
                    "request": request,
                    "depends_on": [],
                    "required": True,
                }
            ],
            "request": {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": request,
                "components": [
                    {
                        "component_id": "step",
                        "domain_id": "gis",
                        "request": request,
                        "depends_on": [],
                        "required": True,
                    }
                ],
            },
        }


class _Runs:
    def __init__(self):
        self.calls = []

    def submit_async(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"status": "QUEUED", "run_id": "should-not-run"}


class M282PlannerGatewayTests(unittest.TestCase):
    def test_rule_and_llm_gateways_consume_the_same_v2_context(self):
        host, projector = _fixture()
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析洪山区", domain_ids=["gis"]
        )
        payload = {
            "outcome": "success",
            "goal": "空间摘要",
            "message": "",
            "components": [
                {
                    "component_id": "summary",
                    "domain_id": "gis",
                    "capability_id": "gis.summary",
                    "request": "分析洪山区",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }
        rule = RuleCompositePlanner(lambda request, _context: payload).plan(
            "分析洪山区", context=context
        )

        class _Client:
            def complete_json(self, messages, schema):
                return payload

        llm = LLMCompositePlanner(_Client()).plan("分析洪山区", context=context)

        self.assertEqual(rule["status"], "PLANNED")
        self.assertEqual(llm["status"], "PLANNED")
        self.assertEqual(rule["request"]["fingerprint"], llm["request"]["fingerprint"])

    def test_llm_gateway_rejects_unknown_context_schema(self):
        class _Client:
            def complete_json(self, messages, schema):
                raise AssertionError("provider must not be called")

        with self.assertRaises(CompositePlannerError) as error:
            LLMCompositePlanner(_Client()).plan(
                "分析",
                context={"schema_version": "private.context.v9"},
            )
        self.assertEqual(error.exception.code, "planner_context_schema_invalid")

    def test_unknown_capability_is_rejected_before_execution(self):
        host, projector = _fixture()
        runs = _Runs()
        app = CompositePlanningApplication(
            host=host,
            projector=projector,
            planner=_UnknownPlanner(),
            composite_runs=runs,
            context_builder=_FixedContext(),
        )

        result = app.submit("分析洪山区", domain_ids=["gis"])

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["error_code"], "capability_not_registered")
        self.assertFalse(runs.calls)

    def test_http_planning_preserves_context_and_clarification_contract(self):
        host, projector = _fixture(region=None, requires_region=True)

        class _ClarifyingPlanner:
            def plan(self, request, *, context=None):
                raise AssertionError("missing facts should stop before planner")

        app = CompositePlanningApplication(
            host=host,
            projector=projector,
            planner=_ClarifyingPlanner(),
            composite_runs=_Runs(),
        )
        direct = app.prepare("分析最近发展", domain_ids=["economic"])
        via_http = HTTPApplication(object(), composite_planning=app).execute(
            "composite_plan",
            {"request": "分析最近发展", "domain_ids": ["economic"]},
        )

        self.assertEqual(direct["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(direct["clarification"]["state"], "required")
        self.assertEqual(
            direct["request_context"]["request_fingerprint"],
            via_http["request_context"]["request_fingerprint"],
        )
        self.assertEqual(direct["planner_evidence"]["context_schema_version"], via_http["planner_evidence"]["context_schema_version"])


if __name__ == "__main__":
    unittest.main()
