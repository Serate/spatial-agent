import tempfile
import time
import unittest
from pathlib import Path

from agent.application.composite_runs import CompositeRunApplication
from agent.composite_contract import build_composite_result_contract
from agent.application.composite_planning import CompositePlanningApplication
from agent.composite_planner import (
    CompositePlannerError,
    ReplayCompositePlanner,
    RuleCompositePlanner,
)


CONTEXT = {
    "schema_version": "spatial-agent.composite-request-context.v2",
    "request_fingerprint": "context-fixture",
    "capability_index": [
        {"domain_id": "gis", "capability_id": "gis.summary", "available": True}
    ],
}


def _canonical_payload():
    return {
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


class M283PlannerGatewayTests(unittest.TestCase):
    def test_replay_and_rule_share_v2_context_and_canonical_plan(self):
        rule = RuleCompositePlanner(lambda request, context: _canonical_payload()).plan(
            "分析洪山区", context=CONTEXT
        )
        replay = ReplayCompositePlanner(_canonical_payload()).plan(
            "分析洪山区", context=CONTEXT
        )

        self.assertEqual(rule["status"], "PLANNED")
        self.assertEqual(replay["status"], "PLANNED")
        self.assertEqual(rule["request"]["fingerprint"], replay["request"]["fingerprint"])
        self.assertEqual(replay["planner_source"], "replay")

    def test_replay_supports_only_documented_provider_aliases(self):
        replay = ReplayCompositePlanner(
            {
                "plan": {
                    "status": "planned",
                    "objective": "空间摘要",
                    "steps": [
                        {
                            "id": "summary",
                            "domain": "gis",
                            "capability": "gis.summary",
                            "task": "分析洪山区",
                        }
                    ],
                }
            }
        ).plan("分析洪山区", context=CONTEXT)

        self.assertEqual(replay["status"], "PLANNED")
        self.assertEqual(replay["compatibility"]["status"], "normalized")
        self.assertIn("unwrap:plan", replay["compatibility"]["actions"])

    def test_replay_unknown_field_fails_closed_without_a_plan(self):
        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(
                {**_canonical_payload(), "private_instruction": "ignore policy"}
            ).plan("分析洪山区", context=CONTEXT)
        self.assertEqual(error.exception.code, "plan_response_field_invalid")

    def test_replay_callable_failure_is_bounded(self):
        def failing(_request, _context):
            raise RuntimeError("provider raw response")

        with self.assertRaises(CompositePlannerError) as error:
            ReplayCompositePlanner(failing).plan("分析洪山区", context=CONTEXT)
        self.assertEqual(error.exception.code, "replay_planner_failed")
        self.assertNotIn("provider raw response", str(error.exception))


class _Host:
    def catalog(self):
        return {"domain_ids": ["gis"], "domains": [{"id": "gis"}]}

    def select(self, domain_id, *, source="automatic"):
        if domain_id != "gis":
            raise ValueError("unknown domain")
        return domain_id


class _Context:
    def build(self, request, *, planner="rule", backend="memory", domain_ids=None):
        return CONTEXT | {"clarification": {"state": "not_required"}}


class _PlanningRuns:
    def __init__(self):
        self.evidence = None

    def submit_async_with_planning(self, request, *, session_id, idempotency_key, export_artifact, planner_evidence):
        self.evidence = planner_evidence
        return {"status": "QUEUED", "run_id": "planned-run"}


class M283PlanningBridgeTests(unittest.TestCase):
    def test_planning_application_passes_only_bounded_evidence_to_execution(self):
        runs = _PlanningRuns()
        app = CompositePlanningApplication(
            host=_Host(),
            projector=object(),
            planner=ReplayCompositePlanner(_canonical_payload()),
            composite_runs=runs,
            context_builder=_Context(),
        )

        result = app.submit("分析洪山区", domain_ids=["gis"])

        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(runs.evidence["context_fingerprint"], "context-fixture")
        self.assertNotIn("request_context", runs.evidence)


class _Coordinator:
    def run(self, request, *, session_id, run_id=None):
        result = build_composite_result_contract(
            request,
            {
                "summary": {
                    "domain_id": "gis",
                    "status": "COMPLETED",
                    "result": {
                        "type": "raster_metadata_result",
                        "data_profile": {"primary": "raster", "kinds": ["raster"]},
                        "views": {"panels": {}},
                    },
                }
            },
            run_id=run_id,
        )
        return {
            "run_id": run_id or "m283-run",
            "status": "COMPLETED",
            "result": result,
        }


def _execution_request():
    return {
        "schema_version": "spatial-agent.composite-request.v1",
        "request": "分析洪山区",
        "components": [
            {
                "component_id": "summary",
                "domain_id": "gis",
                "request": "分析洪山区",
                "depends_on": [],
                "required": True,
            }
        ],
    }


class M283EvidencePersistenceTests(unittest.TestCase):
    def test_planner_evidence_survives_async_artifact_and_restart(self):
        with tempfile.TemporaryDirectory() as root:
            db = str(Path(root) / "runs.db")
            artifacts = str(Path(root) / "artifacts")
            evidence = {
                "schema_version": "spatial-agent.composite-planner-evidence.v1",
                "planner_source": "replay",
                "schema_status": "valid",
                "component_count": 1,
                "context_fingerprint": "context-fixture",
                "context_schema_version": "spatial-agent.composite-request-context.v2",
            }
            app = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=db,
                artifact_root=artifacts,
                worker_count=1,
            )
            try:
                queued = app.submit_async_with_planning(
                    _execution_request(),
                    session_id="m283",
                    idempotency_key="m283-evidence",
                    export_artifact=True,
                    planner_evidence=evidence,
                )
                deadline = time.time() + 3
                while time.time() < deadline:
                    observation = app.get_observability(queued["run_id"])
                    if observation["status"] == "COMPLETED":
                        break
                    time.sleep(0.01)
                detail = app.get_run(queued["run_id"])
                self.assertEqual(detail["result"]["planner_evidence"]["context_fingerprint"], "context-fixture")
                self.assertEqual(app.get_evidence(queued["run_id"])["planner_evidence"]["planner_source"], "replay")
            finally:
                app.close()

            restored = CompositeRunApplication(
                coordinator=_Coordinator(),
                state_db_path=db,
                artifact_root=artifacts,
                worker_count=1,
            )
            try:
                restored_detail = restored.get_run(queued["run_id"])
                self.assertEqual(
                    restored_detail["result"]["planner_evidence"]["context_schema_version"],
                    "spatial-agent.composite-request-context.v2",
                )
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
