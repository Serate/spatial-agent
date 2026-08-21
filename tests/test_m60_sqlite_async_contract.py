import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.errors import ToolError
from agent.models import PlanStep, TaskPlan
from agent.runtime import AgentRuntime
from agent.service import AgentService
from agent.sqlite_store import SQLiteStateStore
from agent.tools import ToolRegistry


class _RetryPlanner:
    def plan(self, request):
        return TaskPlan(
            goal="跨服务重试契约",
            steps=[
                PlanStep("prepare", "m60_prepare", {}, []),
                PlanStep("flaky", "m60_flaky", {}, ["prepare"]),
            ],
        )


class _ProcessRecreatedAdapter:
    calls = 0

    def invoke(self, name, arguments):
        type(self).calls += 1
        if name == "m60_prepare":
            return {"value": "persisted prerequisite"}
        if name == "m60_flaky" and type(self).calls == 2:
            raise ToolError("transient failure")
        if name == "m60_flaky":
            return {"value": "recovered after service restart"}
        raise AssertionError(name)


def _build_retry_runtime(
    _planner_name,
    _backend_name,
    state_store=None,
    conversation_store=None,
    memory=None,
    observability=None,
    decision_store=None,
):
    definitions = {
        name: {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": False},
        }
        for name in ("m60_prepare", "m60_flaky")
    }
    return AgentRuntime(
        _RetryPlanner(),
        ToolRegistry(definitions, _ProcessRecreatedAdapter()),
        state_store=state_store,
        conversation_store=conversation_store,
        memory=memory,
        observability=observability,
        decision_store=decision_store,
        max_retries=0,
    )


class M60SQLiteAsyncContractTests(unittest.TestCase):
    def test_result_reference_remains_readable_after_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            first_service = AgentService(state_db_path=path)
            self.addCleanup(first_service.close)
            first = first_service.run(
                "查询洪山区行政区边界", session_id="result-ref-session"
            )
            restored_service = AgentService(state_db_path=path)
            self.addCleanup(restored_service.close)
            restored = restored_service.get_run(first["run_id"])

        step = next(item for item in restored["steps"] if item["tool"] == "range_query")
        self.assertEqual(step["result"]["result_ref"], "memory://range/admin_areas")
        self.assertEqual(step["result"]["first_name"], "洪山区")
        evidence_steps = restored["result"]["data"]["evidence_steps"]
        self.assertTrue(
            any(
                isinstance(item, dict)
                and item.get("tool") == "range_query"
                and item.get("summary", {}).get("result_ref")
                == "memory://range/admin_areas"
                for item in evidence_steps
            )
        )

    def test_cleared_session_has_no_history_after_service_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            first = AgentService(state_db_path=path)
            self.addCleanup(first.close)
            first.run("你好", session_id="clear-after-restart")

            clear_service = AgentService(state_db_path=path)
            self.addCleanup(clear_service.close)
            cleared = clear_service.clear_session("clear-after-restart")
            restored = AgentService(state_db_path=path)
            self.addCleanup(restored.close)

            self.assertEqual(cleared["cleared_runs"], 1)
            self.assertEqual(
                restored.list_session_runs("clear-after-restart")["runs"], []
            )

    def test_cancel_marker_survives_store_recreation_and_is_cleared_persistently(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            SQLiteStateStore(path).request_cancel("cross-process-run")

            recreated = SQLiteStateStore(path)
            self.assertTrue(recreated.is_cancel_requested("cross-process-run"))
            recreated.clear_cancel("cross-process-run")

            self.assertFalse(SQLiteStateStore(path).is_cancel_requested("cross-process-run"))

    def test_failed_run_can_retry_after_service_recreation(self):
        _ProcessRecreatedAdapter.calls = 0
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            with patch("agent.service.build_runtime", side_effect=_build_retry_runtime):
                failed_service = AgentService(state_db_path=path)
                self.addCleanup(failed_service.close)
                failed = failed_service.run(
                    "触发一次瞬态故障", session_id="retry-after-restart"
                )
                self.assertEqual(failed["status"], "FAILED")
                failed_run_id = failed["run_id"]

                recovered_service = AgentService(state_db_path=path)
                self.addCleanup(recovered_service.close)
                recovered = recovered_service.retry(failed_run_id)

        self.assertEqual(recovered["status"], "COMPLETED")
        self.assertEqual(
            recovered["steps"][-1]["result"]["value"],
            "recovered after service restart",
        )


if __name__ == "__main__":
    unittest.main()
