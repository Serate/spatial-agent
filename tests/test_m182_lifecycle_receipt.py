import tempfile
import unittest
from pathlib import Path

from agent.artifact_store import ArtifactStore
from agent.api_contract import cancel_kwargs, decision_resolve_kwargs, retry_kwargs
from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.tools import ToolRegistry


class _RetryPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="M182 lifecycle receipt retry",
            steps=[
                PlanStep("prepare", "m182_prepare", {}, []),
                PlanStep("flaky", "m182_flaky", {}, ["prepare"]),
            ],
        )


class _FlakyAdapter:
    def __init__(self, failures_remaining):
        self.failures_remaining = failures_remaining

    def invoke(self, name, arguments):
        if name == "m182_prepare":
            return {"value": "retained"}
        if name == "m182_flaky":
            if self.failures_remaining:
                self.failures_remaining -= 1
                raise ToolError("M182 transient failure")
            return {"value": "recovered"}
        raise AssertionError(name)


def _retry_factory(adapter):
    def factory(
        _planner,
        _backend,
        state_store=None,
        conversation_store=None,
        memory=None,
        observability=None,
        decision_store=None,
    ):
        definitions = {
            name: {
                "name": name,
                "input_schema": {
                    "type": "object",
                    "additionalProperties": False,
                },
            }
            for name in ("m182_prepare", "m182_flaky")
        }
        return AgentRuntime(
            _RetryPlanner(),
            ToolRegistry(definitions, adapter),
            state_store=state_store,
            conversation_store=conversation_store,
            memory=memory,
            observability=observability,
            decision_store=decision_store,
            max_retries=0,
        )

    return factory


class M182LifecycleReceiptTests(unittest.TestCase):
    def test_http_contract_forwards_lifecycle_idempotency_keys(self):
        self.assertEqual(
            retry_kwargs({"idempotency_key": "retry-1"})["idempotency_key"],
            "retry-1",
        )
        self.assertEqual(
            cancel_kwargs({"idempotency_key": "cancel-1"})["idempotency_key"],
            "cancel-1",
        )
        self.assertEqual(
            decision_resolve_kwargs({"idempotency_key": "decision-1"})[
                "idempotency_key"
            ],
            "decision-1",
        )

    def test_cancel_replays_the_same_action_receipt(self):
        service = AgentService()
        self.addCleanup(service.close)

        waiting = service.run(
            "查询DEM栅格元数据",
            session_id="m182-cancel",
            require_confirmation=True,
        )
        idempotency_key = "m182-cancel-" + waiting["run_id"]
        first = service.cancel(
            waiting["run_id"],
            idempotency_key=idempotency_key,
        )
        replay = service.cancel(
            waiting["run_id"],
            idempotency_key=idempotency_key,
        )

        self.assertEqual(first["status"], "CANCELLED")
        self.assertEqual(first["action_receipt"]["action_id"], "cancel")
        self.assertFalse(first["action_receipt"]["reused"])
        self.assertTrue(replay["action_receipt"]["reused"])
        self.assertEqual(replay["status"], first["status"])

    def test_decision_receipt_replays_after_service_restart(self):
        with tempfile.TemporaryDirectory(prefix="m182-decision-") as directory:
            state_path = str(Path(directory) / "state.db")
            first_service = AgentService(state_db_path=state_path)
            waiting = first_service.run(
                "查询DEM栅格元数据",
                session_id="m182-decision",
                require_confirmation=True,
            )
            evidence = waiting["decision_evidence"]
            first = first_service.resolve_decision(
                evidence["decision_id"],
                "approve",
                expected_version=evidence["version"],
                idempotency_key="m182-approve-1",
            )
            first_service.close()

            restarted = AgentService(state_db_path=state_path)
            try:
                replay = restarted.resolve_decision(
                    evidence["decision_id"],
                    "approve",
                    expected_version=evidence["version"],
                    idempotency_key="m182-approve-1",
                )
            finally:
                restarted.close()

        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(first["action_receipt"]["action_id"], "approve")
        self.assertTrue(replay["action_receipt"]["reused"])
        self.assertEqual(replay["action_receipt"]["result_ref"], first["action_receipt"]["result_ref"])

    def test_reject_and_cancel_receipts_reach_artifact_and_history(self):
        with tempfile.TemporaryDirectory(prefix="m182-artifact-receipt-") as directory:
            root = Path(directory)
            store = ArtifactStore(root / "artifacts")
            service = AgentService(
                state_db_path=str(root / "state.db"),
                artifact_store=store,
            )
            try:
                waiting = service.run(
                    "查询DEM栅格元数据",
                    session_id="m182-reject",
                    require_confirmation=True,
                    export_artifact=True,
                )
                evidence = waiting["decision_evidence"]
                rejected = service.resolve_decision(
                    evidence["decision_id"],
                    "reject",
                    expected_version=evidence["version"],
                    idempotency_key="m182-reject-1",
                )
                artifact = store.read_run(rejected["run_id"], domain_id="gis")
                history = next(
                    item
                    for item in service.list_runs()["runs"]
                    if item["run_id"] == rejected["run_id"]
                )
            finally:
                service.close()

        self.assertEqual(rejected["action_receipt"]["action_id"], "reject")
        self.assertEqual(artifact["action_receipt"], rejected["action_receipt"])
        self.assertEqual(history["action_receipt"], rejected["action_receipt"])

    def test_retry_with_explicit_key_replays_without_running_again(self):
        adapter = _FlakyAdapter(failures_remaining=1)
        with tempfile.TemporaryDirectory(prefix="m182-retry-key-") as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "state.db"),
                artifact_store=ArtifactStore(Path(directory) / "artifacts"),
                runtime_factory=_retry_factory(adapter),
            )
            try:
                failed = service.run("触发一次瞬态故障", session_id="m182-retry-key")
                first = service.retry(
                    failed["run_id"],
                    idempotency_key="m182-retry-1",
                )
                calls_after_first = adapter.failures_remaining
                replay = service.retry(
                    failed["run_id"],
                    idempotency_key="m182-retry-1",
                )
            finally:
                service.close()

        self.assertEqual(first["status"], "COMPLETED")
        self.assertFalse(first["action_receipt"]["reused"])
        self.assertTrue(replay["action_receipt"]["reused"])
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertEqual(adapter.failures_remaining, calls_after_first)

    def test_retry_without_key_can_start_a_new_attempt_after_failure(self):
        adapter = _FlakyAdapter(failures_remaining=2)
        with tempfile.TemporaryDirectory(prefix="m182-retry-attempt-") as directory:
            service = AgentService(
                state_db_path=str(Path(directory) / "state.db"),
                artifact_store=ArtifactStore(Path(directory) / "artifacts"),
                runtime_factory=_retry_factory(adapter),
            )
            try:
                failed = service.run("触发两次瞬态故障", session_id="m182-retry-attempt")
                first_retry = service.retry(failed["run_id"])
                second_retry = service.retry(failed["run_id"])
            finally:
                service.close()

        self.assertEqual(first_retry["status"], "FAILED")
        self.assertEqual(first_retry["action_receipt"]["status"], "FAILED")
        self.assertEqual(second_retry["status"], "COMPLETED")
        self.assertEqual(second_retry["action_receipt"]["action_id"], "retry")
        self.assertFalse(second_retry["action_receipt"]["reused"])


if __name__ == "__main__":
    unittest.main()
