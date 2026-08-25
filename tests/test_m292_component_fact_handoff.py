"""M292 compact contract: component facts and resumable clarification."""

import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.composite_planner import ReplayCompositePlanner
from agent.runtime_core.clarification_continuation import (
    ClarificationContinuationError,
    consume_component_continuation,
)


def _payload():
    return {
        "outcome": "success",
        "goal": "查询经济指标",
        "message": "",
        "components": [
            {
                "component_id": "economic-main",
                "domain_id": "economic",
                "capability_id": "economic_indicator_latest",
                "request": "查询指定经济指标",
                "depends_on": [],
                "required": True,
                "workflow": {
                    "template_id": "economic_indicator_latest",
                    "template_version": "1.0.0",
                    "allowed_tools": ["economic_indicator_query"],
                    "result_types": ["economic_metrics_result"],
                    "task_plan": {
                        "goal": "查询经济指标",
                        "steps": [
                            {
                                "id": "query",
                                "tool": "economic_indicator_query",
                                "args": {
                                    "dataset": "wuhan_hongshan_economic_indicators",
                                    "operation": "latest",
                                    "indicator": "gdp_total",
                                    "regions": ["洪山区"],
                                },
                                "depends_on": [],
                            }
                        ],
                        "output": {"type": "economic_metrics_result"},
                        "assumptions": [],
                    },
                },
            }
        ],
    }


class _Host:
    def select(self, domain_id, *, source="automatic"):
        del source
        if domain_id != "economic":
            raise ValueError("unknown domain")
        return domain_id


class _PreviewService:
    def __init__(self):
        self.handoff = None

    def preview(self, request, **kwargs):
        del request
        self.handoff = kwargs.get("component_fact_handoff")
        return {
            "status": "PLANNED",
            "plan": {
                "goal": "查询经济指标",
                "steps": [
                    {
                        "id": "query",
                        "tool": "economic_indicator_query",
                        "args": {"indicator": "gdp_total", "regions": ["洪山区"]},
                        "depends_on": [],
                    }
                ],
                "output": {"type": "economic_metrics_result"},
                "assumptions": [],
            },
        }


class _PreviewHost(_Host):
    def __init__(self, service):
        self._service = service

    def service(self, selection):
        del selection
        return self._service


class _ContextBuilder:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None, fact_overrides=None):
        del request, planner, backend, domain_ids
        override = (fact_overrides or {}).get("economic", {})
        facts = {
            "schema_version": "spatial-agent.request-facts.v1",
            "entities": dict(override.get("entities") or {}),
            "datasets": ["wuhan_hongshan_economic_indicators"],
            "constraints": dict(override.get("constraints") or {}),
            "tasks": ["latest"],
            "evidence": ["answer"],
        }
        return {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m292-request",
            "domain_contexts": [{"domain_id": "economic", "facts": facts, "workflow": {"constraints": {}}}],
            "capability_index": [
                {
                    "domain_id": "economic",
                    "capability_id": "economic_indicator_latest",
                    "available": True,
                    "plan_mode": "task_plan",
                    "workflow_ids": ["economic_indicator_latest"],
                    "tools": ["economic_indicator_query"],
                    "result_types": ["economic_metrics_result"],
                    "request_requirements": {
                        "clarification_fields": [
                            {"id": "indicator", "label": "经济指标", "kind": "constraint", "keys": ["indicator"]},
                            {"id": "regions", "label": "分析区域", "kind": "entity", "key": "regions"},
                        ]
                    },
                }
            ],
            "workflow_index": [
                {"domain_id": "economic", "workflow_id": "economic_indicator_latest", "allowed_tools": ["economic_indicator_query"], "result_types": ["economic_metrics_result"]}
            ],
            "clarification": {"state": "not_required"},
        }


class M292ComponentFactHandoffTests(unittest.TestCase):
    def _application(self):
        return CompositePlanningApplication(
            host=_Host(),
            projector=object(),
            planner=ReplayCompositePlanner(_payload()),
            composite_runs=object(),
            context_builder=_ContextBuilder(),
        )

    def test_clarification_then_resume_rebuilds_and_validates_plan(self):
        application = self._application()
        first = application.prepare("查询经济指标", planner_name="replay", domain_ids=["economic"])
        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        handoff = first["component_fact_handoff"]
        self.assertEqual(handoff["state"], "required")
        token = first["continuation"]["token"]

        resumed = application.prepare(
            "查询经济指标",
            planner_name="replay",
            domain_ids=["economic"],
            continuation_token=token,
            fact_supplement={"indicator": "gdp_total", "regions": "洪山区"},
        )
        self.assertEqual(resumed["status"], "PLANNED")
        self.assertEqual(resumed["planner_evidence"]["continuation"]["component_id"], "economic-main")
        self.assertEqual(resumed["task_plan_bridge"]["state"], "accepted")
        self.assertEqual(resumed["task_plan_bridge"]["components"][0]["fact_handoff"]["state"], "ready")

    def test_tampered_or_unknown_supplement_is_rejected(self):
        application = self._application()
        first = application.prepare("查询经济指标", planner_name="replay", domain_ids=["economic"])
        token = first["continuation"]["token"]
        with self.assertRaises(ClarificationContinuationError) as error:
            consume_component_continuation(token + "x", {"indicator": "gdp_total", "regions": "洪山区"})
        self.assertEqual(error.exception.code, "continuation_token_tampered")
        with self.assertRaises(ClarificationContinuationError) as error:
            consume_component_continuation(token, {"invented": "value"})
        self.assertEqual(error.exception.code, "continuation_field_unknown")

    def test_ready_handoff_reaches_domain_preview_without_token_projection(self):
        service = _PreviewService()
        payload = _payload()
        payload["components"] = [
            {key: value for key, value in payload["components"][0].items() if key != "workflow"}
        ]
        application = CompositePlanningApplication(
            host=_PreviewHost(service),
            projector=object(),
            planner=ReplayCompositePlanner(payload),
            composite_runs=object(),
            context_builder=_ContextBuilder(),
        )
        first = application.prepare("查询经济指标", planner_name="replay", domain_ids=["economic"])
        resumed = application.prepare(
            "查询经济指标",
            planner_name="replay",
            domain_ids=["economic"],
            continuation_token=first["continuation"]["token"],
            fact_supplement={"indicator": "gdp_total", "regions": "洪山区"},
        )
        self.assertEqual(resumed["status"], "PLANNED")
        self.assertEqual(resumed["task_plan_bridge"]["components"][0]["source"], "domain_preview")
        self.assertEqual(service.handoff["state"], "ready")
        self.assertNotIn("token", service.handoff)


if __name__ == "__main__":
    unittest.main()
