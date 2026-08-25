import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.composite_planner import LLMCompositePlanner, ReplayCompositePlanner
from agent.planner_repair import (
    PlannerRepairError,
    build_planner_repair_request,
    build_repair_lineage,
    safe_repair_request,
)


CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "m287-context",
    "capability_index": [
        {"domain_id": "gis", "capability_id": "gis.summary", "available": True}
    ],
    "clarification": {"state": "not_required"},
}


class _Host:
    def select(self, domain_id, *, source="automatic"):
        if domain_id != "gis":
            raise ValueError("unknown domain")
        return domain_id


class _ContextBuilder:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        return dict(CONTEXT)


class _AcceptedTaskPlanBridge:
    def bridge(self, components, **kwargs):
        del kwargs
        projected = [
            {"component_id": item["component_id"], "state": "accepted"}
            for item in components
        ]
        return {
            "state": "accepted",
            "materialized_count": len(projected),
            "components": projected,
        }


def _planned_payload():
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
            }
        ],
    }


def _invalid_component_payload():
    payload = _planned_payload()
    payload["components"][0]["unexpected"] = "not accepted"
    return payload


def _unknown_capability_payload():
    payload = _planned_payload()
    payload["components"][0]["capability_id"] = "gis.unknown"
    return payload


class _RepairPlanner:
    def __init__(self, response=None, *, fail=False):
        self.response = response
        self.fail = fail
        self.calls = 0
        self.context = None

    def plan(self, request, *, context=None):
        self.calls += 1
        self.context = context
        if self.fail:
            raise RuntimeError("repair provider failure")
        if callable(getattr(self.response, "plan", None)):
            return self.response.plan(request, context=context)
        return self.response


class _Client:
    def __init__(self):
        self.messages = None

    def complete_json(self, messages, schema):
        self.messages = messages
        return _planned_payload()


def _application(
    planner, *, repair_planner=None, repair_planner_factory=None, composite_runs=None
):
    return CompositePlanningApplication(
        host=_Host(),
        projector=object(),
        planner=ReplayCompositePlanner(planner),
        repair_planner=repair_planner,
        repair_planner_factory=repair_planner_factory,
        composite_runs=composite_runs or object(),
        context_builder=_ContextBuilder(),
        taskplan_bridge=_AcceptedTaskPlanBridge(),
    )


class M287PlannerRepairTests(unittest.TestCase):
    def test_repair_contract_allows_one_structural_attempt_only(self):
        request = build_planner_repair_request(
            "plan_component_field_invalid",
            request_fingerprint="m287-context",
            context_schema_version=CONTEXT["schema_version"],
        )
        self.assertEqual(request["attempt"], 1)
        self.assertEqual(request["max_attempts"], 1)
        self.assertEqual(safe_repair_request(request), request)
        self.assertEqual(
            build_repair_lineage(
                reason_code=request["reason_code"],
                status="repaired",
                attempted=True,
                count=1,
                request_fingerprint="m287-context",
            )["schema_version"],
            "spatial-agent.planner-repair-lineage.v1",
        )
        with self.assertRaises(PlannerRepairError):
            build_planner_repair_request("capability_not_registered")
        with self.assertRaises(PlannerRepairError):
            build_planner_repair_request("plan_component_field_invalid", max_attempts=2)

    def test_structural_failure_can_repair_once_and_preserves_fingerprint(self):
        repair = _RepairPlanner(_planned_payload())
        repair.response = ReplayCompositePlanner(_planned_payload())
        factory_calls = []

        def repair_factory(planner_name, backend):
            factory_calls.append((planner_name, backend))
            return repair

        result = _application(
            _invalid_component_payload(), repair_planner_factory=repair_factory
        ).prepare("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(factory_calls, [("replay", "memory")])
        self.assertEqual(repair.calls, 1)
        self.assertEqual(
            repair.context["planner_repair"]["reason_code"],
            "plan_component_field_invalid",
        )
        self.assertEqual(
            result["repair_lineage"]["status"],
            "repaired",
        )
        self.assertEqual(result["repair_lineage"]["count"], 1)
        self.assertEqual(
            result["repair_lineage"]["request_fingerprint"],
            "m287-context",
        )

    def test_non_repairable_capability_failure_skips_provider(self):
        repair = _RepairPlanner(_planned_payload())
        result = _application(
            _unknown_capability_payload(), repair_planner=repair
        ).prepare("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["error_code"], "capability_not_registered")
        self.assertEqual(repair.calls, 0)
        self.assertEqual(result["repair_lineage"]["status"], "skipped")
        self.assertFalse(result["repair_lineage"]["attempted"])

    def test_failed_repair_is_bounded_and_does_not_create_run(self):
        repair = _RepairPlanner(fail=True)
        result = _application(
            _invalid_component_payload(), repair_planner=repair
        ).prepare("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(repair.calls, 1)
        self.assertEqual(result["repair_lineage"]["status"], "failed")
        self.assertEqual(result["repair_lineage"]["count"], 1)
        self.assertIsNone(result["request"])

    def test_llm_repair_prompt_is_bounded_and_does_not_expose_raw_output(self):
        client = _Client()
        planner = LLMCompositePlanner(client)
        result = planner.plan(
            "开放式空间摘要",
            context={
                **CONTEXT,
                "planner_repair": build_planner_repair_request(
                    "plan_component_field_invalid",
                    request_fingerprint="m287-context",
                    context_schema_version=CONTEXT["schema_version"],
                ),
            },
        )

        self.assertEqual(result["status"], "PLANNED")
        self.assertIn("one bounded schema repair attempt", client.messages[0]["content"])
        self.assertNotIn("raw provider response", client.messages[1]["content"])

    def test_async_submission_carries_repair_lineage_in_safe_evidence(self):
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
                return {"status": "QUEUED", "run_id": "m287-run"}

        repair = _RepairPlanner(ReplayCompositePlanner(_planned_payload()))
        runs = Runs()
        result = _application(
            _invalid_component_payload(),
            repair_planner=repair,
            composite_runs=runs,
        ).submit("开放式空间摘要", planner_name="replay", domain_ids=["gis"])

        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(runs.evidence["repair_lineage"]["status"], "repaired")
        self.assertEqual(runs.evidence["repair_lineage"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
