"""Compact M313 contract tests for the durable realtime event seam."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from agent.models import AgentRunResult, PlanStep, RunStatus, TaskPlan
from agent.runtime import AgentRuntime
from agent.application.http import HTTPApplication
from agent.run_events import (
    RunEventError,
    new_run_event,
    normalize_run_event,
    validate_event_cursor,
)
from agent.runtime_state import InMemoryStateStore
from agent.sqlite_store import SQLiteStateStore
from agent.tools import ToolRegistry


class _Planner:
    def plan(self, request, workflow=None, context=None):
        return TaskPlan(
            goal="完成测试分析",
            steps=[PlanStep("step-1", "make_value", {}, [])],
            output={"type": "buildability_result"},
        )


class _Adapter:
    def invoke(self, name, arguments):
        return {"value": 1}


class _EventService:
    def __init__(self, events):
        self.events = events

    def list_run_events(self, run_id, *, after=0, limit=100):
        return [item for item in self.events if item["sequence"] > after][:limit]

    def get_run(self, run_id, planner="rule", backend="memory"):
        return {"run_id": run_id, "status": "EXECUTING"}


class _PagedEventReader:
    def __init__(self, events):
        self.events = events
        self.reads = []

    def read(self, action, body, resource_id=None):
        self.reads.append((action, dict(body), resource_id))
        after = int(body.get("after") or 0)
        limit = int(body.get("limit") or 100)
        page = [event for event in self.events if event["sequence"] > after][:limit]
        return {
            "schema_version": "spatial-agent.run-event.v1",
            "run_id": resource_id,
            "events": page,
            "after": after,
            "next_cursor": page[-1]["sequence"] if page else after,
            # This is Run-level terminal state, not proof that this page contains
            # the terminal event. It reproduces the production pagination bug.
            "terminal": True,
            "has_more": len(page) >= limit,
        }


class _ConnectedRequest:
    async def is_disconnected(self):
        return False


def _registry():
    return ToolRegistry(
        {
            "make_value": {
                "name": "make_value",
                "input_schema": {"type": "object", "additionalProperties": True},
            }
        },
        _Adapter(),
    )


class M313RunEventContractTests(unittest.TestCase):
    def test_event_is_bounded_and_sensitive_fields_are_not_forwarded(self):
        event = new_run_event(
            run_id="run-1",
            phase="plan",
            kind="stage_progress",
            status="PLANNING",
            message="正在生成任务计划",
            data={
                "stage_index": 3,
                "stage_count": 7,
                "tool": "query_metadata",
                "prompt": "must not cross the event boundary",
                "answer_delta": "安全摘要",
            },
        )
        self.assertEqual(event["schema_version"], "spatial-agent.run-event.v1")
        self.assertEqual(event["sequence"], 0)
        self.assertNotIn("prompt", event["data"])
        self.assertEqual(event["data"]["stage_count"], 7)

    def test_invalid_phase_kind_status_and_cursor_fail_closed(self):
        base = new_run_event(
            run_id="run-1",
            phase="plan",
            kind="stage_started",
            status="PLANNING",
            message="开始规划",
        )
        for field, value in (("phase", "private"), ("kind", "unknown"), ("status", "BROKEN")):
            invalid = dict(base)
            invalid[field] = value
            with self.assertRaises(RunEventError):
                normalize_run_event(invalid)
        with self.assertRaises(RunEventError):
            validate_event_cursor("not-a-cursor")
        self.assertEqual(validate_event_cursor(None), 0)

    def test_memory_store_assigns_order_and_replays_after_cursor(self):
        store = InMemoryStateStore()
        first = store.append_run_event(
            new_run_event(
                run_id="run-1",
                phase="resolve",
                kind="stage_completed",
                status="PLANNING",
                message="已理解请求",
            )
        )
        second = store.append_run_event(
            new_run_event(
                run_id="run-1",
                phase="plan",
                kind="stage_started",
                status="PLANNING",
                message="正在生成计划",
            )
        )
        replay = store.append_run_event(dict(first))
        self.assertEqual((first["sequence"], second["sequence"]), (1, 2))
        self.assertEqual(replay, first)
        self.assertEqual(store.list_run_events("run-1", after=1), [second])

    def test_sqlite_store_replays_events_after_reopen_and_clears_with_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            first_store = SQLiteStateStore(path)
            result = AgentRunResult(
                run_id="run-1",
                status=RunStatus.PLANNING,
                request="测试请求",
                session_id="session-1",
                domain_id="gis",
            )
            first_store.save(result)
            first = first_store.append_run_event(
                new_run_event(
                    run_id="run-1",
                    phase="resolve",
                    kind="stage_completed",
                    status="PLANNING",
                    message="已理解请求",
                )
            )
            first_store.append_run_event(
                new_run_event(
                    run_id="run-1",
                    phase="plan",
                    kind="stage_started",
                    status="PLANNING",
                    message="正在生成计划",
                )
            )
            reopened = SQLiteStateStore(path)
            self.assertEqual(reopened.list_run_events("run-1", after=first["sequence"])[0]["sequence"], 2)
            self.assertEqual(reopened.clear_session_runs("session-1", domain_id="gis"), 1)
            self.assertEqual(reopened.list_run_events("run-1"), [])

    def test_runtime_emits_real_lifecycle_and_tool_events(self):
        store = InMemoryStateStore()
        runtime = AgentRuntime(
            _Planner(),
            _registry(),
            state_store=store,
        )
        result = runtime.run("测试分析", session_id="session-1")
        events = store.list_run_events(result.run_id)
        kinds = [item["kind"] for item in events]
        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual([item["sequence"] for item in events], list(range(1, len(events) + 1)))
        for expected in (
            "stage_completed",
            "tool_started",
            "tool_completed",
            "run_completed",
        ):
            self.assertIn(expected, kinds)
        self.assertEqual(events[-1]["terminal"], True)

    def test_http_read_uses_the_same_event_window_contract(self):
        event = new_run_event(
            run_id="run-http",
            phase="execute",
            kind="tool_completed",
            status="EXECUTING",
            message="步骤已完成",
        )
        event["sequence"] = 1
        payload = HTTPApplication(_EventService([event])).read(
            "run_events",
            {"after": "0", "limit": "10"},
            resource_id="run-http",
        )
        self.assertEqual(payload["schema_version"], "spatial-agent.run-event.v1")
        self.assertEqual(payload["next_cursor"], 1)
        self.assertFalse(payload["terminal"])
        self.assertEqual(
            HTTPApplication(_EventService([event])).read(
                "run_events", {"after": 1}, resource_id="run-http"
            )["events"],
            [],
        )

    def test_production_sse_reads_past_a_full_nonterminal_page(self):
        """A terminal Run must not truncate a page before its terminal event."""
        import asyncio

        from production_api import _run_event_stream

        events = [
            new_run_event(
                run_id="run-sse",
                phase="execute",
                kind="tool_completed",
                status="EXECUTING",
                message="步骤已完成",
            )
            for _ in range(100)
        ]
        for sequence, event in enumerate(events, start=1):
            event["sequence"] = sequence
        terminal = new_run_event(
            run_id="run-sse",
            phase="evidence",
            kind="run_completed",
            status="COMPLETED",
            message="分析完成",
            terminal=True,
        )
        terminal["sequence"] = 101
        events.append(terminal)
        reader = _PagedEventReader(events)

        async def collect():
            chunks = []
            with patch("production_api.asyncio.sleep", return_value=None):
                async for chunk in _run_event_stream(
                    reader,
                    "run-sse",
                    after=0,
                    limit=100,
                    request=_ConnectedRequest(),
                ):
                    chunks.append(chunk)
            return chunks

        chunks = asyncio.run(collect())
        ids = [
            line[4:]
            for chunk in chunks
            for line in chunk.splitlines()
            if line.startswith("id: ")
        ]
        self.assertEqual(ids, [str(sequence) for sequence in range(1, 102)])
        self.assertTrue(chunks[-1].endswith("\n\n"))
        self.assertEqual([item[1]["after"] for item in reader.reads], [0, 100])


if __name__ == "__main__":
    unittest.main()
