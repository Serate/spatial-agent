"""M293 compact contract: grouped facts and composite continuation."""

import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.application.http import HTTPApplication
from agent.application.composite_planner import ReplayCompositePlanner
from agent.runtime_core.clarification_continuation import (
    ClarificationContinuationError,
    consume_composite_continuation,
)


def _workflow(tool, result_type, goal):
    return {
        "allowed_tools": [tool],
        "result_types": [result_type],
        "task_plan": {
            "goal": goal,
            "steps": [
                {
                    "id": "query",
                    "tool": tool,
                    "args": {"scope": "selected"},
                    "depends_on": [],
                }
            ],
            "output": {"type": result_type},
            "assumptions": [],
        },
    }


def _payload():
    return {
        "outcome": "success",
        "goal": "完成多领域摘要",
        "message": "",
        "components": [
            {
                "component_id": "economic-main",
                "domain_id": "economic",
                "capability_id": "economic.latest",
                "request": "查询经济指标",
                "depends_on": [],
                "required": True,
                "workflow": _workflow(
                    "economic_indicator_query", "economic_metrics_result", "查询经济指标"
                ),
            },
            {
                "component_id": "gis-main",
                "domain_id": "gis",
                "capability_id": "gis.boundary",
                "request": "查询空间范围",
                "depends_on": [],
                "required": True,
                "workflow": _workflow("boundary_query", "vector_result", "查询空间范围"),
            },
        ],
    }


class _Host:
    def select(self, domain_id, *, source="automatic"):
        del source
        if domain_id not in {"economic", "gis"}:
            raise ValueError("unknown domain")
        return domain_id


class _ContextBuilder:
    def build(
        self,
        request,
        *,
        planner="rule",
        backend="memory",
        domain_ids=None,
        fact_overrides=None,
    ):
        del request, planner, backend
        selected = list(domain_ids or ["economic", "gis"])
        overrides = fact_overrides or {}
        economic = overrides.get("economic") or {}
        gis = overrides.get("gis") or {}
        return {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m293-request",
            "domain_ids": selected,
            "domain_contexts": [
                {
                    "domain_id": "economic",
                    "facts": {
                        "entities": dict(economic.get("entities") or {}),
                        "constraints": dict(economic.get("constraints") or {}),
                        "datasets": [],
                        "tasks": [],
                        "evidence": [],
                    },
                    "workflow": {"constraints": {}},
                },
                {
                    "domain_id": "gis",
                    "facts": {
                        "entities": dict(gis.get("entities") or {}),
                        "constraints": dict(gis.get("constraints") or {}),
                        "datasets": [],
                        "tasks": [],
                        "evidence": [],
                    },
                    "workflow": {"constraints": {}},
                },
            ],
            "capability_index": [
                {
                    "domain_id": "economic",
                    "capability_id": "economic.latest",
                    "available": True,
                    "tools": ["economic_indicator_query"],
                    "result_types": ["economic_metrics_result"],
                    "workflow_ids": ["economic.latest"],
                    "request_requirements": {
                        "clarification_fields": [
                            {
                                "id": "indicator",
                                "label": "经济指标",
                                "kind": "constraint",
                                "keys": ["indicator"],
                            },
                            {
                                "id": "regions",
                                "label": "分析区域",
                                "kind": "entity",
                                "key": "regions",
                            },
                        ]
                    },
                },
                {
                    "domain_id": "gis",
                    "capability_id": "gis.boundary",
                    "available": True,
                    "tools": ["boundary_query"],
                    "result_types": ["vector_result"],
                    "workflow_ids": ["gis.boundary"],
                    "request_requirements": {
                        "clarification_fields": [
                            {
                                "id": "admin_name",
                                "label": "行政区名称",
                                "kind": "entity",
                                "key": "admin_name",
                            }
                        ]
                    },
                },
            ],
            "workflow_index": [],
            "clarification": {"state": "not_required"},
        }


class M293MultiComponentContinuationTests(unittest.TestCase):
    def _application(self):
        return CompositePlanningApplication(
            host=_Host(),
            projector=object(),
            planner=ReplayCompositePlanner(_payload()),
            composite_runs=object(),
            context_builder=_ContextBuilder(),
        )

    def test_grouped_handoff_resumes_same_component_set(self):
        application = self._application()
        first = application.prepare(
            "完成多领域摘要", planner_name="replay", domain_ids=["economic", "gis"]
        )
        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        handoff = first["composite_fact_handoff"]
        self.assertEqual(handoff["state"], "required")
        self.assertEqual(handoff["component_ids"], ["economic-main", "gis-main"])
        self.assertEqual(
            {item["id"] for item in handoff["missing_fields"]},
            {"indicator", "regions", "admin_name"},
        )

        resumed = application.prepare(
            "完成多领域摘要",
            planner_name="replay",
            domain_ids=["economic", "gis"],
            continuation_token=first["continuation"]["token"],
            fact_supplement={
                "components": {
                    "economic-main": {"indicator": "gdp_total", "regions": "洪山区"},
                    "gis-main": {"admin_name": "洪山区"},
                }
            },
        )
        self.assertEqual(resumed["status"], "PLANNED")
        self.assertEqual(resumed["task_plan_bridge"]["state"], "accepted")
        self.assertEqual(
            resumed["planner_evidence"]["continuation"]["component_ids"],
            ["economic-main", "gis-main"],
        )
        self.assertEqual(
            resumed["task_plan_bridge"]["fact_handoff"]["state"], "ready"
        )

    def test_partial_grouped_facts_keep_clarification_without_run(self):
        application = self._application()
        first = application.prepare(
            "完成多领域摘要", planner_name="replay", domain_ids=["economic", "gis"]
        )
        partial = application.prepare(
            "完成多领域摘要",
            planner_name="replay",
            domain_ids=["economic", "gis"],
            continuation_token=first["continuation"]["token"],
            fact_supplement={"components": {"economic-main": {"indicator": "gdp_total"}}},
        )
        self.assertEqual(partial["status"], "NEEDS_CLARIFICATION")
        self.assertNotIn("run_id", partial)
        self.assertIn("admin_name", {item["id"] for item in partial["composite_fact_handoff"]["missing_fields"]})

    def test_unknown_component_in_grouped_supplement_is_rejected(self):
        application = self._application()
        first = application.prepare(
            "完成多领域摘要", planner_name="replay", domain_ids=["economic", "gis"]
        )
        with self.assertRaises(ClarificationContinuationError) as error:
            consume_composite_continuation(
                first["continuation"]["token"],
                {"components": {"invented": {"indicator": "gdp_total"}}},
            )
        self.assertEqual(error.exception.code, "continuation_component_unknown")

    def test_http_prepare_round_trip_preserves_grouped_continuation(self):
        application = self._application()
        http = HTTPApplication(object(), composite_planning=application)
        body = {
            "request": "完成多领域摘要",
            "planner": "replay",
            "domain_ids": ["economic", "gis"],
        }
        first = http.execute("composite_plan", body)
        resumed = http.execute(
            "composite_plan",
            {
                **body,
                "continuation_token": first["continuation"]["token"],
                "facts": {
                    "components": {
                        "economic-main": {"indicator": "gdp_total", "regions": "洪山区"},
                        "gis-main": {"admin_name": "洪山区"},
                    }
                },
            },
        )
        self.assertEqual(first["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(resumed["status"], "PLANNED")
        self.assertEqual(
            resumed["planner_evidence"]["continuation"]["component_ids"],
            ["economic-main", "gis-main"],
        )


if __name__ == "__main__":
    unittest.main()
