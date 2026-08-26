import json
import unittest

from agent.composite_request_context import CompositeRequestContextBuilder
from agent.composite_planner import CompositePlannerError, normalize_composite_plan
from agent.application.composite_planning import CompositePlanningApplication
from agent.application.composite_runs import CompositeRunApplication
from agent.runtime_core.planner_envelope import PLANNER_ENVELOPE_SCHEMA_VERSION


class _Service:
    def __init__(self, domain_id, facts, *, available=True, guidance=None):
        self.domain_id = domain_id
        self.facts = facts
        self.available = available
        self.guidance = guidance or {
            "domain_id": domain_id,
            "fact_fields": ["entities", "tasks", "constraints"],
            "task_hints": [{"id": "summary", "label": "摘要", "phrases": ["概况"]}],
            "constraint_hints": [],
            "evidence_hints": [{"id": "answer", "label": "答案"}],
            "clarification_policy": ["缺少必要事实时先澄清"],
            "discovery_policy": ["只选择已登记能力"],
            "private_payload": {"token": "must-not-leak"},
        }

    def extract_request_facts(self, request):
        del request
        return self.facts

    def request_understanding_guidance(self):
        return self.guidance

    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "schema_version": "spatial-agent.capability-discovery.v1",
            "selected_capability_id": self.domain_id + ".summary",
            "candidate_ids": [self.domain_id + ".summary"],
            "selection_state": "selected",
        }

    def select_workflow(self, discovery, request_facts, *, workflow=None):
        del request_facts, workflow
        return {
            "selected_capability_id": discovery.get("selected_capability_id"),
            "candidate_ids": discovery.get("candidate_ids", []),
        }


class _Host:
    def __init__(self, services):
        self.services = services

    def catalog(self):
        return {
            "domain_ids": list(self.services),
            "domains": [{"domain_id": key, "capabilities": []} for key in self.services],
        }

    def select(self, domain_id, *, source="automatic"):
        del source
        return domain_id

    def service(self, selection):
        return self.services[selection]


class _Projector:
    def __init__(self, catalog):
        self.catalog = catalog

    def project(self, **kwargs):
        del kwargs
        return self.catalog


def _facts(*, region=True):
    return {
        "schema_version": "spatial-agent.request-facts.v1",
        "entities": {"region": "武汉"} if region else {},
        "tasks": ["summary"],
        "datasets": ["regional_data"],
        "constraints": {},
        "evidence": ["parser"],
    }


def _fixture(*, region=True, available=True, domain_regions=None):
    domain_regions = domain_regions or {}
    services = {
        domain: _Service(
            domain,
            _facts(region=domain_regions.get(domain, region)),
            available=available,
        )
        for domain in ("gis", "economic")
    }
    capabilities = {
        domain: {
            "id": domain + ".summary",
            "label": "摘要",
            "description": "通用摘要能力",
            "datasets": ["regional_data"],
            "tools": ["summary_tool"],
            "result_types": ["metrics"],
            "available": available,
            "missing_datasets": [] if available else ["regional_data"],
            "request_requirements": {
                "clarification_fields": [
                    {"id": "region", "label": "分析区域", "key": "region", "kind": "entity"}
                ]
            },
        }
        for domain in services
    }
    catalog = {
        "domain_ids": list(services),
        "domains": [
            {
                "domain_id": domain,
                "capabilities": [capabilities[domain]],
                "data_readiness": {"status": "ready" if available else "unavailable"},
            }
            for domain in services
        ],
        "workflow_index": [],
    }
    return _Host(services), _Projector(catalog)


class M300OpenAgentSuccessContractTests(unittest.TestCase):
    def test_understanding_is_available_to_planner_and_private_fields_are_removed(self):
        host, projector = _fixture()
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析武汉概况", domain_ids=["gis"]
        )
        envelope = context["planner_envelope"]
        understanding = envelope["request_facts"]["domains"][0]["understanding"]

        self.assertEqual(envelope["schema_version"], PLANNER_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(understanding["domain_id"], "gis")
        self.assertEqual(understanding["fact_fields"], ["entities", "tasks", "constraints"])
        self.assertNotIn("must-not-leak", json.dumps(context, ensure_ascii=False))

    def test_incomplete_facts_are_structured_without_guessing(self):
        host, projector = _fixture(region=False)
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析概况", domain_ids=["economic"]
        )

        self.assertEqual(context["clarification"]["state"], "required")
        self.assertEqual(context["clarification"]["reason_code"], "request_facts_missing")
        self.assertEqual(context["clarification"]["missing_by_domain"][0]["domain_id"], "economic")

    def test_multi_domain_context_keeps_each_domain_under_one_envelope(self):
        host, projector = _fixture()
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析武汉概况", domain_ids=["gis", "economic"]
        )
        domains = context["planner_envelope"]["request_facts"]["domains"]

        self.assertEqual({item["domain_id"] for item in domains}, {"gis", "economic"})
        self.assertEqual(context["evidence"]["sources"][1], "request_understanding")

    def test_unavailable_capability_is_not_presented_as_ready(self):
        host, projector = _fixture(available=False)
        context = CompositeRequestContextBuilder(host=host, catalog_projector=projector).build(
            "分析概况", domain_ids=["gis"]
        )

        self.assertEqual(context["clarification"]["state"], "unavailable")
        self.assertEqual(context["clarification"]["reason_code"], "data_unavailable")
        self.assertFalse(context["discovery"]["candidates"][0]["execution_ready"])

    def test_planner_rejects_explicitly_unready_candidate_before_materialization(self):
        payload = {
            "outcome": "success",
            "goal": "安全摘要",
            "message": "",
            "components": [
                {
                    "component_id": "summary",
                    "domain_id": "gis",
                    "capability_id": "gis.summary",
                    "request": "分析概况",
                    "depends_on": [],
                    "required": True,
                }
            ],
        }
        context = {
            "capability_index": [
                {
                    "domain_id": "gis",
                    "capability_id": "gis.summary",
                    "available": True,
                    "execution_ready": False,
                    "execution_reason_code": "data_readiness_unknown",
                }
            ]
        }

        with self.assertRaises(CompositePlannerError) as error:
            normalize_composite_plan(
                payload,
                request="分析概况",
                context=context,
                planner_source="replay",
            )
        self.assertEqual(error.exception.code, "data_readiness_unknown")

    def test_answer_generation_is_reserved_for_llm_planned_runs(self):
        class _Answer:
            def __init__(self):
                self.calls = 0

            def generate(self, result):
                del result
                self.calls += 1
                return type(
                    "Generated",
                    (),
                    {
                        "answer": {
                            "headline": "分析完成",
                            "summary": "已根据结果生成简洁摘要。",
                            "key_findings": [],
                            "limitations": [],
                        },
                        "evidence": {"status": "success", "available": True},
                    },
                )()

        generator = _Answer()
        application = CompositeRunApplication.__new__(CompositeRunApplication)
        application._answer_generator = generator
        base = {"answer": "模板摘要"}

        replay = application._compose_composite_answer(
            base,
            planning_evidence={"planner_source": "replay"},
        )
        live = application._compose_composite_answer(
            base,
            planning_evidence={"planner_source": "llm"},
        )

        self.assertEqual(replay, base)
        self.assertEqual(generator.calls, 1)
        self.assertEqual(live["answer_structured"]["headline"], "分析完成")

    def test_provider_failure_is_retryable_not_fact_clarification(self):
        class _ProviderFailurePlanner:
            def plan(self, request, *, context=None):
                del request, context
                raise CompositePlannerError(
                    "provider unavailable",
                    code="planner_provider_failed",
                )

        host, projector = _fixture()
        application = CompositePlanningApplication(
            host=host,
            projector=projector,
            planner=_ProviderFailurePlanner(),
            composite_runs=object(),
        )
        result = application.prepare(
            "分析武汉概况",
            planner_name="openai",
            backend="local",
            domain_ids=["gis"],
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error_code"], "planner_provider_failed")
        self.assertEqual(result["next_actions"], ["稍后重试"])
        self.assertEqual(result["failure"]["category"], "provider")
        self.assertTrue(result["failure"]["retryable"])
        self.assertNotIn("补充信息", result["message"])
        self.assertIsNone(result["request"])


if __name__ == "__main__":
    unittest.main()
