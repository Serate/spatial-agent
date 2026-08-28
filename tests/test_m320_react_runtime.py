import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.llm_planner import LLMPlanner
from agent.models import RunStatus
from agent.react.contracts import ReactDecisionError, REACT_DECISION_SCHEMA_VERSION
from agent.react.loop import ReactLoop, ReactToolOutcome
from agent.request_model import RequestFacts
from agent.runtime import AgentRuntime
from agent.runtime_state import InMemoryStateStore
from agent.sqlite_store import SQLiteStateStore
from agent.tools import ToolRegistry


class _CapturingClient:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None
        self.schema = None
        self.schema_name = None

    def complete_json(self, messages, schema, *, schema_name=None):
        self.messages = messages
        self.schema = schema
        self.schema_name = schema_name
        return self.payload


class _LegacyClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, schema):
        return self.payload


class _RecoveringClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, messages, schema, *, schema_name=None):
        self.calls.append(("normal", schema_name))
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "call_tool",
            "tool_name": "safe_tool",
            "arguments": [],
            "output_type": "metrics",
            "unexpected": "must be removed",
        }

    def complete_compact_json(self, messages, schema, *, schema_name=None):
        self.calls.append(("compact", schema_name))
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "finish",
            "summary": "已完成安全校正",
            "output_type": "direct_answer",
            "extra_provider_field": "ignored safely",
        }


class _QueueDecider:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def decide(self, request, **kwargs):
        self.calls.append({"request": request, **kwargs})
        return self.decisions.pop(0)


def _decision(action, **values):
    return {
        "schema_version": REACT_DECISION_SCHEMA_VERSION,
        "action": action,
        **values,
    }


class _ReactPlanner:
    react_enabled = True
    execution_policy_mode = "react"

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def plan(self, *_args, **_kwargs):
        raise AssertionError("ReAct runtime must not invoke the TaskPlan planner")

    def decide(self, request, **kwargs):
        self.calls.append({"request": request, **kwargs})
        return self.decisions.pop(0)

    def metrics(self):
        return {"execution_mode": "replay_model"}


class _RuntimeAdapter:
    def __init__(self):
        self.calls = []

    def invoke(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "make_value":
            return {"result_type": "metrics", "value": arguments["value"]}
        if name == "use_value":
            return {"result_type": "metrics", "used": arguments["value"]}
        raise AssertionError(name)


class _MinimalDomain:
    domain_id = "m320-test"

    def capability_catalog(self, *, environment="unknown"):
        return {
            "schema_version": "spatial-agent.capability-catalog.v1",
            "domain_id": self.domain_id,
            "version": "1.0.0",
            "environment": environment,
            "capabilities": [],
            "workflow_templates": {},
            "dataset_groups": {},
        }

    def discover(self, request, request_facts):
        del request, request_facts
        return {
            "domain_id": self.domain_id,
            "candidate_ids": [],
            "candidate_count": 0,
            "selected_capability_id": None,
        }

    def extract_request_facts(self, request):
        return RequestFacts(
            text=request,
            admin_name=None,
            tasks=(),
            datasets=(),
            constraints={},
            evidence=("answer",),
        )


class _AnswerComposer:
    def compose(self, result):
        return "已根据 {} 个工具结果完成分析。".format(len(result.steps))

    def compose_failure(self, result):
        return "分析未完成。"


def _runtime_registry(adapter):
    string_input = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "string"}},
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"result_type": {"const": "metrics"}},
        "additionalProperties": True,
    }
    return ToolRegistry(
        {
            "make_value": {
                "name": "make_value",
                "input_schema": string_input,
                "output_schema": output_schema,
            },
            "use_value": {
                "name": "use_value",
                "input_schema": string_input,
                "output_schema": output_schema,
            },
        },
        adapter,
    )


def _runtime(planner, adapter, store):
    defaults = {
        "react_mode": "full",
        "web_search_enabled": True,
        "tool_proposals_enabled": True,
        "react_max_turns": 8,
        "react_max_actions": 12,
    }
    with patch("agent.runtime.open_agent_defaults", return_value=defaults):
        return AgentRuntime(
            planner,
            _runtime_registry(adapter),
            state_store=store,
            answer_composer=_AnswerComposer(),
            planner_name="openai",
            domain_pack=_MinimalDomain(),
            max_retries=0,
        )


class M320ReactDecisionAdapterTests(unittest.TestCase):
    def test_decide_uses_bounded_context_and_effective_tool_allowlist(self):
        client = _CapturingClient(
            {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "call_tool",
                "summary": "读取已登记数据",
                "tool_name": "safe_tool",
                "arguments": {"dataset": "demo"},
                "output_type": "metrics",
            }
        )
        planner = LLMPlanner(client, ("safe_tool", "other_tool"))

        decision = planner.decide(
            "分析数据",
            context={
                "capability": {"id": "demo"},
                "api_key": "must-not-leak",
                "nested": {"system_prompt": "must-not-leak-either"},
            },
            history=[
                {
                    "turn_index": 1,
                    "action": "call_tool",
                    "tool_name": "safe_tool",
                    "result_ref": "step-1",
                    "summary": "返回 3 条记录",
                    "arguments": {"private": "not-forwarded"},
                }
            ],
            allowed_tools=("safe_tool", "unknown_tool"),
            tool_catalog={
                "safe_tool": {
                    "description": "读取演示数据",
                    "input_schema": {
                        "required": ["dataset"],
                        "properties": {"dataset": {"type": "string"}},
                    },
                }
            },
        )

        self.assertEqual(decision["tool_name"], "safe_tool")
        self.assertEqual(client.schema_name, "react_decision")
        self.assertEqual(
            client.schema["properties"]["schema_version"]["const"],
            REACT_DECISION_SCHEMA_VERSION,
        )
        serialized_messages = "\n".join(item["content"] for item in client.messages)
        self.assertIn("safe_tool", serialized_messages)
        self.assertNotIn("other_tool", serialized_messages)
        self.assertNotIn("unknown_tool", serialized_messages)
        self.assertNotIn("must-not-leak", serialized_messages)
        self.assertNotIn("not-forwarded", serialized_messages)
        self.assertIn("step-1", serialized_messages)
        self.assertIn("available_tool_contracts", serialized_messages)
        self.assertIn("dataset", serialized_messages)

    def test_decide_preserves_two_argument_client_compatibility(self):
        planner = LLMPlanner(
            _LegacyClient(
                {
                    "schema_version": REACT_DECISION_SCHEMA_VERSION,
                    "action": "finish",
                    "summary": "已有信息足够回答",
                    "output_type": "direct_answer",
                }
            ),
            ("safe_tool",),
        )

        decision = planner.decide("解释结果")

        self.assertEqual(decision["action"], "finish")

    def test_decide_performs_one_bounded_recovery_for_invalid_action_shape(self):
        client = _RecoveringClient()
        planner = LLMPlanner(client, ("safe_tool",))

        decision = planner.decide("解释已有信息")

        self.assertEqual(decision["action"], "finish")
        self.assertEqual(client.calls, [("normal", "react_decision"), ("compact", "react_decision")])

    def test_decide_rejects_tool_outside_runtime_allowlist(self):
        planner = LLMPlanner(
            _LegacyClient(
                {
                    "schema_version": REACT_DECISION_SCHEMA_VERSION,
                    "action": "call_tool",
                    "tool_name": "safe_tool",
                    "arguments": {},
                }
            ),
            ("safe_tool",),
        )

        with self.assertRaises(ReactDecisionError):
            planner.decide("读取数据", allowed_tools=())

    def test_decide_enforces_network_policy_before_returning_action(self):
        planner = LLMPlanner(
            _LegacyClient(
                {
                    "schema_version": REACT_DECISION_SCHEMA_VERSION,
                    "action": "search",
                    "query": "武汉公开统计数据",
                }
            ),
            (),
        )

        with self.assertRaises(ReactDecisionError):
            planner.decide("查找公开资料", network_enabled=False)


class M320ReactLoopTests(unittest.TestCase):
    def test_loop_executes_one_tool_per_turn_then_finishes_with_safe_history(self):
        decider = _QueueDecider(
            [
                _decision(
                    "call_tool",
                    tool_name="safe_tool",
                    arguments={"dataset": "demo"},
                    output_type="metrics",
                ),
                _decision(
                    "finish",
                    summary="已有足够证据",
                    output_type="metrics",
                ),
            ]
        )
        events = []
        executed = []

        def execute_tool(decision, turn_index, action_id):
            executed.append((decision, turn_index, action_id))
            return ReactToolOutcome(
                result={
                    "status": "ok",
                    "result_type": "metrics",
                    "count": 3,
                    "secret": "must-not-enter-history",
                },
                result_ref="step-1",
                output_type="metrics",
            )

        outcome = ReactLoop(
            decider,
            allowed_tools=("safe_tool",),
            on_event=lambda kind, payload: events.append((kind, payload)),
        ).run("分析数据", execute_tool=execute_tool)

        self.assertEqual(outcome.state, "finished")
        self.assertEqual(outcome.turn_count, 2)
        self.assertEqual(outcome.action_count, 1)
        self.assertEqual(len(executed), 1)
        self.assertEqual(decider.calls[1]["history"][0]["result_ref"], "step-1")
        self.assertNotIn(
            "must-not-enter-history",
            str(decider.calls[1]["history"]),
        )
        self.assertEqual([item["validation_state"] for item in outcome.evidence], ["completed", "completed"])
        self.assertTrue(any(kind == "react_action_completed" for kind, _ in events))
        self.assertNotIn("arguments", str([payload for _, payload in events]))

    def test_loop_blocks_repeated_tool_action_without_second_execution(self):
        repeated = _decision(
            "call_tool",
            tool_name="safe_tool",
            arguments={"dataset": "demo"},
        )
        decider = _QueueDecider([repeated, repeated])
        executions = []

        outcome = ReactLoop(decider, allowed_tools=("safe_tool",)).run(
            "读取数据",
            execute_tool=lambda *_args: executions.append(True) or {"status": "ok"},
        )

        self.assertEqual(outcome.state, "blocked")
        self.assertEqual(outcome.reason_code, "react_repeated_action")
        self.assertEqual(len(executions), 1)

    def test_loop_enforces_action_budget_before_second_tool(self):
        decider = _QueueDecider(
            [
                _decision("call_tool", tool_name="safe_tool", arguments={"dataset": "a"}),
                _decision("call_tool", tool_name="safe_tool", arguments={"dataset": "b"}),
            ]
        )
        executions = []

        outcome = ReactLoop(
            decider,
            allowed_tools=("safe_tool",),
            max_actions=1,
        ).run(
            "读取两个数据集",
            execute_tool=lambda *_args: executions.append(True) or {"status": "ok"},
        )

        self.assertEqual(outcome.state, "blocked")
        self.assertEqual(outcome.reason_code, "react_action_budget_exceeded")
        self.assertEqual(len(executions), 1)

    def test_loop_projects_clarification_and_rejection_as_terminal_states(self):
        cases = (
            ("ask_clarification", "clarification", "请补充区域"),
            ("reject", "rejected", "该操作未授权"),
        )
        for action, expected_state, message in cases:
            with self.subTest(action=action):
                outcome = ReactLoop(
                    _QueueDecider([_decision(action, message=message)]),
                    allowed_tools=(),
                ).run("处理请求")
                self.assertEqual(outcome.state, expected_state)
                self.assertEqual(outcome.final_message, message)
                self.assertEqual(outcome.action_count, 0)


class M320ReactRuntimeTests(unittest.TestCase):
    def test_runtime_can_finish_without_dispatching_a_tool(self):
        planner = _ReactPlanner(
            [
                _decision(
                    "finish",
                    summary="现有上下文足以直接回答",
                    output_type="direct_answer",
                )
            ]
        )
        adapter = _RuntimeAdapter()
        store = InMemoryStateStore()

        result = _runtime(planner, adapter, store).run("解释已有信息")

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.steps, [])
        self.assertEqual(adapter.calls, [])
        self.assertEqual(result.plan.output["type"], "direct_answer")
        self.assertEqual(result.react_evidence["state"], "finished")
        self.assertEqual(result.react_evidence["action_count"], 0)
        self.assertIn("react_finished", [
            item["kind"] for item in store.list_run_events(result.run_id)
        ])

    def test_runtime_executes_dependent_turns_and_persists_safe_evidence(self):
        planner = _ReactPlanner(
            [
                _decision(
                    "call_tool",
                    tool_name="make_value",
                    arguments={"value": "seed"},
                    output_type="metrics",
                ),
                _decision(
                    "call_tool",
                    tool_name="use_value",
                    arguments={"value": {"$from": "react-1", "path": "value"}},
                    depends_on=["react-1"],
                    output_type="metrics",
                ),
                _decision("finish", summary="证据已足够", output_type="metrics"),
            ]
        )
        adapter = _RuntimeAdapter()
        store = InMemoryStateStore()

        result = _runtime(planner, adapter, store).run("执行两步分析")

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual([step.status for step in result.steps], ["COMPLETED", "COMPLETED"])
        self.assertEqual(adapter.calls, [("make_value", {"value": "seed"}), ("use_value", {"value": "seed"})])
        self.assertEqual(result.plan.steps[1].depends_on, ["react-1"])
        self.assertEqual(result.react_evidence["state"], "finished")
        self.assertEqual(result.react_evidence["action_count"], 2)
        self.assertNotIn("arguments", str(result.react_evidence))
        self.assertEqual(result.plan_evidence["execution_policy"]["mode"], "react")
        self.assertEqual(store.get(result.run_id).react_evidence, result.react_evidence)
        self.assertEqual(planner.calls[1]["history"][0]["result_ref"], "react-1")
        events = store.list_run_events(result.run_id)
        event_kinds = [item["kind"] for item in events]
        self.assertIn("react_action_accepted", event_kinds)
        self.assertIn("react_finished", event_kinds)
        self.assertNotIn("arguments", str(events))

    def test_runtime_blocks_invalid_arguments_before_accept_or_dispatch(self):
        planner = _ReactPlanner(
            [
                _decision(
                    "call_tool",
                    tool_name="make_value",
                    arguments={"value": 3},
                    output_type="metrics",
                )
            ]
        )
        adapter = _RuntimeAdapter()
        store = InMemoryStateStore()

        result = _runtime(planner, adapter, store).run("执行非法参数动作")

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.error_code, "tool_arguments_invalid")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(result.react_evidence["state"], "blocked")
        event_kinds = [item["kind"] for item in store.list_run_events(result.run_id)]
        self.assertIn("react_action_blocked", event_kinds)
        self.assertNotIn("react_action_accepted", event_kinds)

    def test_runtime_maps_react_clarification_to_existing_lifecycle(self):
        planner = _ReactPlanner(
            [_decision("ask_clarification", message="请补充分析区域")]
        )
        store = InMemoryStateStore()

        result = _runtime(planner, _RuntimeAdapter(), store).run("分析发展情况")

        self.assertEqual(result.status, RunStatus.NEEDS_CLARIFICATION)
        self.assertEqual(result.react_evidence["state"], "clarification")
        self.assertEqual(result.clarification["state"], "react_clarification")

    def test_sqlite_reopen_restores_react_result_and_evidence(self):
        planner = _ReactPlanner(
            [
                _decision(
                    "call_tool",
                    tool_name="make_value",
                    arguments={"value": "persisted"},
                    output_type="metrics",
                ),
                _decision("finish", summary="持久化证据已足够", output_type="metrics"),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "state.db")
            result = _runtime(
                planner,
                _RuntimeAdapter(),
                SQLiteStateStore(database, legacy_domain_id="m320-test"),
            ).run("执行并持久化分析")

            restored = SQLiteStateStore(
                database, legacy_domain_id="m320-test"
            ).get(result.run_id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, RunStatus.COMPLETED)
        self.assertEqual(restored.react_evidence, result.react_evidence)
        self.assertEqual(restored.to_dict()["plan"], result.to_dict()["plan"])
        self.assertEqual(restored.steps[0].result, result.steps[0].result)
        self.assertNotIn("arguments", str(restored.react_evidence))


if __name__ == "__main__":
    unittest.main()
