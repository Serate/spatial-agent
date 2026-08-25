import unittest

from agent.application.composite_planning import CompositePlanningApplication
from agent.composite_contract import normalize_composite_request
from agent.composite_planner import (
    CompositePlannerError,
    LLMCompositePlanner,
)
from evaluation.live_provider_probe import run_composite_planning_probe


class _ReplayClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, schema, *, schema_name=None):
        return self.payload


class _Projection:
    def project(self, **kwargs):
        return {
            "capability_index": [
                {"domain_id": "gis", "capability_id": "gis_summary", "available": True}
            ]
        }


class _Host:
    def select(self, domain_id, *, source="automatic"):
        if domain_id != "gis":
            raise ValueError("unknown domain")
        return domain_id


class _Runs:
    pass


class _ContextBuilder:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        return {
            "schema_version": "spatial-agent.composite-request-context.v2",
            "request_fingerprint": "m280-context",
            "capability_index": [
                {"domain_id": "gis", "capability_id": "gis_summary", "available": True}
            ],
            "clarification": {"state": "not_required"},
        }


class _ApplicationPlanner:
    def plan(self, request, *, context=None):
        canonical = normalize_composite_request(
            {
                "schema_version": "spatial-agent.composite-request.v1",
                "request": request,
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
        )
        return {
            "status": "PLANNED",
            "planner_source": "llm",
            "goal": "空间分析",
            "message": "",
            "components": [{**_component(), "index": 0}],
            "request": canonical,
            "validation": {"status": "valid"},
            "compatibility": {
                "status": "normalized",
                "actions": ["alias:status->outcome", "default:component_required"],
            },
        }


class _ProbeApplication:
    def __init__(self, result=None, error=False):
        self.result = result
        self.error = error

    def prepare(self, request, **kwargs):
        if self.error:
            raise RuntimeError("private provider response")
        return self.result


def _component(**overrides):
    value = {
        "component_id": "space",
        "domain_id": "gis",
        "capability_id": "gis_summary",
        "request": "查询空间摘要",
        "depends_on": [],
        "required": True,
    }
    value.update(overrides)
    return value


class M280ResponseCompatibilityTests(unittest.TestCase):
    def test_documented_wrapper_and_aliases_reach_canonical_plan(self):
        payload = {
            "plan": {
                "status": "planned",
                "objective": "组合空间分析",
                "steps": [
                    {
                        "id": "space",
                        "domain": "gis",
                        "capability": "gis_summary",
                        "task": "查询空间摘要",
                    }
                ],
            }
        }

        result = LLMCompositePlanner(_ReplayClient(payload)).plan(
            "分析空间", context={}
        )

        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["request"]["components"][0]["domain_id"], "gis")
        self.assertEqual(result["compatibility"]["status"], "normalized")
        self.assertIn("unwrap:plan", result["compatibility"]["actions"])

    def test_missing_outcome_has_only_bounded_shape_defaults(self):
        planned = LLMCompositePlanner(
            _ReplayClient({"goal": "空间分析", "components": [_component()]})
        ).plan("分析空间", context={})
        clarified = LLMCompositePlanner(
            _ReplayClient({"message": "请补充区域", "components": []})
        ).plan("分析空间", context={})

        self.assertEqual(planned["status"], "PLANNED")
        self.assertEqual(clarified["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(clarified["request"], None)

    def test_unknown_response_or_component_fields_fail_closed(self):
        with self.assertRaises(CompositePlannerError) as response_error:
            LLMCompositePlanner(
                _ReplayClient(
                    {"outcome": "success", "goal": "x", "components": [], "notes": "x"}
                )
            ).plan("分析空间", context={})
        self.assertEqual(response_error.exception.code, "plan_response_field_invalid")

        with self.assertRaises(CompositePlannerError) as component_error:
            LLMCompositePlanner(
                _ReplayClient(
                    {
                        "outcome": "success",
                        "goal": "x",
                        "components": [{**_component(), "tool_args": {}}],
                    }
                )
            ).plan("分析空间", context={})
        self.assertEqual(component_error.exception.code, "plan_component_field_invalid")

    def test_application_exposes_bounded_planner_evidence(self):
        application = CompositePlanningApplication(
            host=_Host(),
            projector=_Projection(),
            planner=_ApplicationPlanner(),
            composite_runs=_Runs(),
            context_builder=_ContextBuilder(),
        )

        result = application.prepare("分析空间", domain_ids=["gis"])
        evidence = result["planner_evidence"]

        self.assertEqual(evidence["schema_status"], "valid")
        self.assertEqual(evidence["component_count"], 1)
        self.assertEqual(evidence["request_fingerprint"], result["request_fingerprint"])
        self.assertEqual(evidence["compatibility"]["status"], "normalized")
        self.assertNotIn("prompt", str(evidence).lower())
        self.assertNotIn("raw", str(evidence).lower())

    def test_planning_probe_returns_safe_replay_receipts_without_execution(self):
        planned = run_composite_planning_probe(
            application=_ProbeApplication(
                {
                    "status": "PLANNED",
                    "components": [{"component_id": "space"}],
                    "request_fingerprint": "abc123",
                    "planner_evidence": {
                        "schema_version": "spatial-agent.composite-planner-evidence.v1",
                        "planner_source": "llm",
                        "schema_status": "valid",
                        "component_count": 1,
                        "request_fingerprint": "abc123",
                        "compatibility": {
                            "status": "normalized",
                            "actions": ["alias:status->outcome"],
                        },
                        "prompt": "must not escape",
                    }
                }
            ),
            request="组合分析",
            timeout_seconds=1,
        )
        clarified = run_composite_planning_probe(
            application=_ProbeApplication(
                {"status": "NEEDS_CLARIFICATION", "components": []}
            ),
            request="组合分析",
            timeout_seconds=1,
        )
        failed = run_composite_planning_probe(
            application=_ProbeApplication(error=True),
            request="组合分析",
            timeout_seconds=1,
        )

        self.assertTrue(planned["passed"])
        self.assertEqual(planned["component_count"], 1)
        self.assertEqual(planned["planner_evidence"]["compatibility"]["status"], "normalized")
        self.assertNotIn("prompt", str(planned).lower())
        self.assertFalse(clarified["passed"])
        self.assertEqual(clarified["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(failed["error_code"], "planning_probe_failed")


if __name__ == "__main__":
    unittest.main()
