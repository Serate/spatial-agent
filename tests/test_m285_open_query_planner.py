"""M285-B: planner source and selection evidence stays consistent."""

import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.application.http import HTTPApplication
from agent.composite_planner import CompositePlannerError, ReplayCompositePlanner


CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m285-context",
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.summary",
            "available": True,
            "tools": ["summarize_data"],
            "result_types": ["summary_result"],
        }
    ],
    "clarification": {"state": "not_required"},
}


def planned_payload():
    return {
        "outcome": "success",
        "goal": "形成空间摘要",
        "message": "",
        "components": [
            {
                "component_id": "summary",
                "domain_id": "gis",
                "capability_id": "gis.summary",
                "request": "分析当前区域",
                "depends_on": [],
                "required": True,
                "workflow": {
                    "allowed_tools": ["summarize_data"],
                    "result_types": ["summary_result"],
                    "task_plan": {
                        "goal": "形成空间摘要",
                        "steps": [
                            {
                                "id": "summarize",
                                "tool": "summarize_data",
                                "args": {"query": "当前区域"},
                                "depends_on": [],
                            }
                        ],
                        "output": {"type": "summary_result"},
                        "assumptions": [],
                    },
                },
            }
        ],
    }


class Host:
    def select(self, domain_id, *, source="automatic"):
        if domain_id != "gis":
            raise ValueError("unknown domain")
        return domain_id


class ContextBuilder:
    def __init__(self, context=None):
        self._context = context or CONTEXT

    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        return dict(self._context)


def build_application(payload, context=None):
    return CompositePlanningApplication(
        host=Host(),
        projector=object(),
        planner=ReplayCompositePlanner(payload),
        composite_runs=object(),
        context_builder=ContextBuilder(context),
    )


class M285PlannerSelectionEvidenceTests(unittest.TestCase):
    def test_success_records_requested_and_actual_planner_selection(self):
        result = build_application(planned_payload()).prepare(
            "开放式空间摘要", planner_name="replay", domain_ids=["gis"]
        )

        self.assertEqual(result["status"], "PLANNED")
        selection = result["planner_evidence"]["selection"]
        self.assertEqual(
            selection["schema_version"],
            "spatial-agent.composite-planner-selection.v1",
        )
        self.assertEqual(selection["state"], "selected")
        self.assertEqual(selection["requested_planner"], "replay")
        self.assertEqual(selection["selected_source"], "replay")
        self.assertEqual(
            selection["reason_code"],
            "planner_selected_registered_capabilities",
        )
        self.assertEqual(selection["selected_capability_ids"], ["gis.summary"])
        self.assertEqual(selection["candidate_count"], 1)

    def test_clarification_and_rejection_have_selection_state(self):
        clarification = build_application(
            {"outcome": "needs_clarification", "goal": "", "message": "请补充范围", "components": []}
        ).prepare("开放式问题", planner_name="replay", domain_ids=["gis"])
        rejected = build_application(
            {"outcome": "rejected", "goal": "", "message": "不支持", "components": []}
        ).prepare("开放式问题", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(clarification["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(clarification["planner_evidence"]["selection"]["state"], "clarification")
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertEqual(rejected["planner_evidence"]["selection"]["state"], "rejected")

    def test_provider_failure_is_bounded_and_has_failed_selection(self):
        def failing(_request, _context):
            raise RuntimeError("provider raw response")

        result = build_application(failing).prepare(
            "开放式问题", planner_name="replay", domain_ids=["gis"]
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["error_code"], "replay_planner_failed")
        self.assertEqual(result["planner_evidence"]["selection"]["state"], "failed")
        self.assertEqual(
            result["planner_evidence"]["selection"]["reason_code"],
            "replay_planner_failed",
        )
        self.assertNotIn("provider raw response", str(result))


TASKPLAN_CONTEXT = {
    **CONTEXT,
    "capability_index": [
        {
            "domain_id": "gis",
            "capability_id": "gis.summary",
            "available": True,
            "tools": ["discover_data", "summarize_data"],
            "result_types": ["summary_result"],
        }
    ],
}


def two_step_payload(tool="summarize_data"):
    return {
        "outcome": "success",
        "goal": "形成空间摘要",
        "message": "",
        "components": [
            {
                "component_id": "summary",
                "domain_id": "gis",
                "capability_id": "gis.summary",
                "request": "分析当前区域",
                "depends_on": [],
                "required": True,
                "workflow": {
                    "allowed_tools": ["discover_data", "summarize_data"],
                    "result_types": ["summary_result"],
                    "task_plan": {
                        "goal": "形成空间摘要",
                        "steps": [
                            {
                                "id": "discover",
                                "tool": "discover_data",
                                "args": {"query": "当前区域"},
                                "depends_on": [],
                            },
                            {
                                "id": "summarize",
                                "tool": tool,
                                "args": {
                                    "source": {
                                        "$from": "discover",
                                        "path": "records",
                                    }
                                },
                                "depends_on": ["discover"],
                            },
                        ],
                        "output": {"type": "summary_result"},
                        "assumptions": [],
                    },
                },
            }
        ],
    }


class M285TaskPlanBridgeTests(unittest.TestCase):
    def test_replay_materializes_two_step_taskplan_and_dag(self):
        result = build_application(
            two_step_payload(), context=TASKPLAN_CONTEXT
        ).prepare("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "PLANNED")
        bridge = result["task_plan_bridge"]
        self.assertEqual(bridge["state"], "accepted")
        self.assertEqual(bridge["materialized_count"], 1)
        component = bridge["components"][0]
        self.assertEqual(
            [step["id"] for step in component["plan"]["steps"]],
            ["discover", "summarize"],
        )
        self.assertEqual(component["dag"]["edges"], [{"from": "discover", "to": "summarize"}])
        self.assertEqual(
            result["planner_evidence"]["task_plan_bridge"], bridge
        )

    def test_replay_unknown_tool_fails_before_execution(self):
        result = build_application(
            two_step_payload(tool="invented_tool"), context=TASKPLAN_CONTEXT
        ).prepare("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["error_code"], "taskplan_tool_not_allowlisted")
        self.assertNotIn("invented_tool", str(result.get("planner_evidence")))

    def test_http_async_submission_preserves_accepted_bridge_evidence(self):
        class Runs:
            def __init__(self):
                self.evidence = None

            def submit_async_with_planning(
                self,
                request,
                *,
                session_id,
                idempotency_key,
                export_artifact,
                planner_evidence,
            ):
                self.evidence = planner_evidence
                return {"status": "QUEUED", "run_id": "m285-run"}

        runs = Runs()
        app = CompositePlanningApplication(
            host=Host(),
            projector=object(),
            planner=ReplayCompositePlanner(two_step_payload()),
            composite_runs=runs,
            context_builder=ContextBuilder(TASKPLAN_CONTEXT),
        )
        response = HTTPApplication(object(), composite_planning=app).execute(
            "composite_plan",
            {
                "request": "开放式空间摘要",
                "planner": "replay",
                "domain_ids": ["gis"],
                "execute": True,
                "async": True,
            },
        )

        self.assertEqual(response["status"], "QUEUED")
        self.assertEqual(response["task_plan_bridge"]["state"], "accepted")
        self.assertEqual(runs.evidence["task_plan_bridge"]["state"], "accepted")


if __name__ == "__main__":
    unittest.main()
