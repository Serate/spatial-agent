import json
import unittest

from agent.application.composite_request_context import CompositeRequestContextBuilder
from agent.application.composite_runs import _safe_planning_evidence
from agent.application.composite_view import build_composite_view_projection
from agent.runtime_core.analysis_discovery import (
    ANALYSIS_DISCOVERY_SCHEMA_VERSION,
    AnalysisDiscoveryError,
    AnalysisDiscoveryGateway,
)


def _domain_context(
    domain_id="gis",
    *,
    readiness="ready",
    missing_fields=None,
    workflow_missing_fields=None,
    discovery_state="available",
):
    return {
        "domain_id": domain_id,
        "facts": {"schema_version": "spatial-agent.request-facts.v1"},
        "discovery": {
            "schema_version": "spatial-agent.capability-discovery.v1",
            "state": discovery_state,
            "selection_state": "selected",
            "selected_capability_id": f"{domain_id}.summary",
            "candidate_ids": [f"{domain_id}.summary"],
            "reason_code": "catalog_match",
            "prompt": "must not survive",
        },
        "workflow": {
            "state": "available",
            "source": "domain",
            "workflow_template_id": f"{domain_id}.summary",
            "workflow_template_version": "1.0.0",
            "missing_fields": workflow_missing_fields or [],
        },
        "data_readiness": {"status": readiness, "source_path": "private"},
        "clarification": {"missing_fields": missing_fields or []},
    }


def _candidate(domain_id="gis", *, available=True, plan_mode="task_plan"):
    return {
        "domain_id": domain_id,
        "capability_id": f"{domain_id}.summary",
        "label": "摘要",
        "description": "bounded",
        "selection_key": f"{domain_id}::{domain_id}.summary",
        "available": available,
        "availability_reason": "ready" if available else "required_data_missing",
        "datasets": ["roads"],
        "missing_datasets": [] if available else ["roads"],
        "tools": ["summarize"],
        "result_types": ["metrics"],
        "workflow_ids": [f"{domain_id}.summary"],
        "plan_mode": plan_mode,
        "request_requirements": {"clarification_fields": []},
        "raw_response": {"secret": "no"},
    }


class M295DiscoveryGatewayTests(unittest.TestCase):
    def test_receipt_is_bounded_stable_and_has_data_contract(self):
        gateway = AnalysisDiscoveryGateway()
        kwargs = {
            "planner": "rule",
            "backend": "local",
            "domain_ids": ["gis"],
            "domain_contexts": [_domain_context()],
            "candidate_index": [_candidate()],
        }
        first = gateway.discover("分析道路分布", **kwargs)
        second = gateway.discover("分析道路分布", **kwargs)

        self.assertEqual(first["schema_version"], ANALYSIS_DISCOVERY_SCHEMA_VERSION)
        self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
        self.assertEqual(first["discovery_fingerprint"], second["discovery_fingerprint"])
        self.assertEqual(first["state"], "ready")
        self.assertEqual(first["data_requirements"][0]["status"], "ready")
        self.assertTrue(first["candidates"][0]["execution_ready"])
        self.assertNotIn("must not survive", json.dumps(first, ensure_ascii=False))

    def test_missing_facts_and_unavailable_data_are_distinct(self):
        gateway = AnalysisDiscoveryGateway()
        missing = gateway.discover(
            "分析经济趋势",
            planner="llm",
            backend="local",
            domain_ids=["economic"],
            domain_contexts=[
                _domain_context(
                    "economic",
                    missing_fields=[{"id": "indicator", "label": "指标", "kind": "constraint"}],
                )
            ],
            candidate_index=[_candidate("economic")],
        )
        unavailable = gateway.discover(
            "分析经济趋势",
            planner="llm",
            backend="local",
            domain_ids=["economic"],
            domain_contexts=[_domain_context("economic", readiness="not_ready")],
            candidate_index=[_candidate("economic", available=False)],
        )
        workflow_missing = gateway.discover(
            "分析经济趋势",
            planner="rule",
            backend="local",
            domain_ids=["economic"],
            domain_contexts=[
                _domain_context("economic", workflow_missing_fields=["indicator"])
            ],
            candidate_index=[_candidate("economic")],
        )

        self.assertEqual(missing["state"], "needs_facts")
        self.assertEqual(missing["reason_code"], "needs_facts")
        self.assertEqual(missing["clarification"]["reason_code"], "request_facts_missing")
        self.assertEqual(unavailable["state"], "data_unavailable")
        self.assertEqual(unavailable["reason_code"], "data_unavailable")
        self.assertEqual(unavailable["candidates"][0]["state"], "data_unavailable")
        self.assertEqual(workflow_missing["state"], "needs_facts")
        self.assertEqual(workflow_missing["missing_facts"][0]["fields"][0]["id"], "indicator")

    def test_context_and_receipt_share_request_identity(self):
        class Service:
            def extract_request_facts(self, request):
                return {
                    "schema_version": "spatial-agent.request-facts.v1",
                    "entities": {"admin_name": "洪山区"},
                    "tasks": ["summary"],
                    "datasets": ["roads"],
                    "constraints": {},
                    "evidence": ["parser"],
                }

            def discover(self, request, facts):
                return {
                    "schema_version": "spatial-agent.capability-discovery.v1",
                    "selected_capability_id": "gis.summary",
                    "candidate_ids": ["gis.summary"],
                    "selection_state": "selected",
                }

            def select_workflow(self, discovery, facts, *, workflow=None):
                return {"source": "domain", "selected_capability_id": "gis.summary"}

        class Host:
            def catalog(self):
                return {"domain_ids": ["gis"], "domains": [{"id": "gis"}]}

            def select(self, domain_id, *, source="automatic"):
                return domain_id

            def service(self, selection):
                return Service()

        class Projector:
            def project(self, **kwargs):
                return {
                    "domain_ids": ["gis"],
                    "domains": [
                        {
                            "domain_id": "gis",
                            "capabilities": [_candidate()],
                            "data_readiness": {"status": "ready"},
                        }
                    ],
                    "catalog_consistency": {"status": "valid"},
                }

        context = CompositeRequestContextBuilder(
            host=Host(), catalog_projector=Projector()
        ).build("分析洪山区道路", planner="rule", backend="local")

        self.assertEqual(
            context["request_fingerprint"],
            context["discovery"]["request_fingerprint"],
        )
        self.assertEqual(
            context["discovery"]["schema_version"],
            ANALYSIS_DISCOVERY_SCHEMA_VERSION,
        )
        self.assertEqual(
            context["evidence"]["discovery_fingerprint"],
            context["discovery"]["discovery_fingerprint"],
        )

    def test_invalid_candidate_fails_closed(self):
        with self.assertRaises(AnalysisDiscoveryError) as error:
            AnalysisDiscoveryGateway().discover(
                "分析",
                planner="rule",
                backend="memory",
                domain_ids=["gis"],
                domain_contexts=[_domain_context()],
                candidate_index=[{"domain_id": "gis"}],
            )
        self.assertEqual(error.exception.code, "discovery_candidate_invalid")

    def test_planning_evidence_and_view_keep_discovery_identity(self):
        receipt = {
            "schema_version": ANALYSIS_DISCOVERY_SCHEMA_VERSION,
            "request_fingerprint": "request-fingerprint",
            "discovery_fingerprint": "discovery-fingerprint",
            "state": "ready",
            "reason_code": "discovery_ready",
            "domain_count": 2,
            "candidate_count": 3,
            "data_requirement_count": 4,
            "candidate_states": {"available": 3},
            "next_actions": ["由 Planner 组合已注册能力并生成计划"],
        }
        evidence = _safe_planning_evidence(
            {
                "planner_source": "rule",
                "schema_status": "valid",
                "discovery": receipt,
            }
        )
        view = build_composite_view_projection(
            {
                "status": "COMPLETED",
                "planner_evidence": evidence,
                "composite": {
                    "state": "completed",
                    "request": {"fingerprint": "request-fingerprint"},
                    "components": [],
                    "evidence": {},
                },
            }
        )

        self.assertEqual(evidence["discovery"]["discovery_fingerprint"], "discovery-fingerprint")
        self.assertEqual(view["planning"]["discovery"]["state"], "ready")
        self.assertEqual(view["planning"]["discovery"]["candidate_count"], 3)


if __name__ == "__main__":
    unittest.main()
