"""Compact M328-A approval-to-run continuation checks."""

from __future__ import annotations

from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest

from agent.models import RunStatus
from agent.react.contracts import REACT_DECISION_SCHEMA_VERSION
from agent.request_model import RequestFacts
from agent.runtime import AgentRuntime
from agent.runtime_state import InMemoryStateStore
from agent.llm_planner import LLMPlanner
from agent.tooling import ToolProposalValidator
from agent.service import AgentService
from agent.tooling.rehydration import rehydrate_approved_tools
from agent.tools import ToolRegistry


def _proposal():
    return {
        "name": "safe_metric",
        "description": "计算一个指标",
        "input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer"}},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer"}},
            "additionalProperties": False,
        },
        "source": 'def run(arguments):\n    return {"value": arguments["value"]}\n',
        "example_arguments": {"value": 3},
    }


class _Sandbox:
    def __init__(self):
        self.validation_calls = 0
        self.execution_calls = 0

    def validate_and_run(self, proposal):
        self.validation_calls += 1
        return {"status": "validated", "reason_code": "proposal_validated"}

    def execute_proposal(self, proposal_id, source_hash, arguments):
        self.execution_calls += 1
        return {
            "status": "validated",
            "reason_code": "proposal_executed",
            "result": {"value": int(arguments["value"]), "result_type": "metrics"},
        }


class _StructuredDecisionClient:
    def complete_json(self, messages, schema, **kwargs):
        del messages, schema, kwargs
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "call_tool",
            "tool_name": "safe_metric",
            "arguments": {"value": 3},
            "output_type": "metrics",
        }


class _Planner:
    react_enabled = True
    execution_policy_mode = "react"

    def __init__(self):
        self.calls = 0

    def decide(self, request, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "propose_tool",
                "summary": "提出受控纯计算工具",
                "proposal": _proposal(),
            }
        if self.calls == 2:
            return {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "call_tool",
                "tool_name": "safe_metric",
                "arguments": {"value": 3},
                "output_type": "metrics",
            }
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "finish",
            "summary": "证据已足够",
        }

    def metrics(self):
        return {"execution_mode": "m328-test"}


class _ApprovalAwarePlanner(_Planner):
    """Model-shaped planner that needs the approval fact after resumption."""

    def decide(self, request, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "propose_tool",
                "summary": "提出受控纯计算工具",
                "proposal": _proposal(),
            }
        history = kwargs.get("history") or []
        approved = any(
            isinstance(item, dict)
            and item.get("action") == "tool_approval_accepted"
            and item.get("tool_name") == "safe_metric"
            for item in history
        )
        tool_completed = any(
            isinstance(item, dict)
            and item.get("action") == "call_tool"
            and item.get("tool_name") == "safe_metric"
            for item in history
        )
        if approved and tool_completed:
            return {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "finish",
                "summary": "证据已足够",
            }
        if approved:
            return {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "call_tool",
                "tool_name": "safe_metric",
                "arguments": {"value": 3},
                "output_type": "metrics",
            }
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "propose_tool",
            "summary": "重复提出同一个工具",
            "proposal": _proposal(),
        }


class _Domain:
    domain_id = "m328-test"

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
        return {"domain_id": self.domain_id, "candidate_ids": [], "candidate_count": 0}

    def extract_request_facts(self, request):
        return RequestFacts(
            text=request,
            admin_name=None,
            tasks=(),
            datasets=(),
            constraints={},
            evidence=("answer",),
        )


class _Answer:
    def compose(self, result, on_delta=None):
        answer = "已完成受控指标计算。"
        if callable(on_delta):
            on_delta(answer)
        return answer

    def compose_failure(self, result):
        return "运行未完成。"


class M328ApprovalResumeTests(unittest.TestCase):
    def test_react_planner_accepts_runtime_registered_dynamic_tool(self):
        planner = LLMPlanner(
            _StructuredDecisionClient(),
            allowed_tools=("existing_tool",),
            react_enabled=True,
        )

        decision = planner.decide(
            "调用已批准的新指标工具",
            allowed_tools=("existing_tool", "safe_metric"),
            tool_catalog={"safe_metric": {"description": "安全指标"}},
        )

        self.assertEqual(decision["tool_name"], "safe_metric")

    def test_runtime_context_stays_stable_after_dynamic_tool_rehydration(self):
        sandbox = _Sandbox()
        runtime = self._runtime(sandbox)
        before = runtime.runtime_context()
        waiting = runtime.run("计算一个新指标")
        pending = waiting.action_receipt["approval"]
        approved = runtime._approval_store.resolve(
            pending["approval_id"],
            action="approve",
            domain_id=runtime.domain_id,
            expected_version=1,
            expected_fingerprint=pending["receipt_fingerprint"],
        )

        rehydrate_approved_tools(
            registry=runtime._registry,
            records=[approved],
            handler_factory=runtime._proposal_validator.handler_for,
            domain_id=runtime.domain_id,
        )

        self.assertEqual(runtime.runtime_context(), before)
        self.assertIn("safe_metric", runtime._registry.names)

    def _runtime(self, sandbox):
        defaults = {
            "react_mode": "full",
            "web_search_enabled": False,
            "tool_proposals_enabled": True,
            "react_max_turns": 8,
            "react_max_actions": 12,
        }
        with patch("agent.runtime.open_agent_defaults", return_value=defaults):
            return AgentRuntime(
                _Planner(),
                ToolRegistry(
                    {
                        "existing_tool": {
                            "name": "existing_tool",
                            "input_schema": {"type": "object"},
                            "output_schema": {"type": "object"},
                        }
                    },
                    lambda name, arguments: {},
                ),
                state_store=InMemoryStateStore(),
                answer_composer=_Answer(),
                planner_name="openai",
                domain_pack=_Domain(),
                proposal_validator=ToolProposalValidator(sandbox),
                max_retries=0,
            )

    def test_approval_resumes_same_run_and_executes_only_after_binding(self):
        sandbox = _Sandbox()
        runtime = self._runtime(sandbox)
        waiting = runtime.run("计算一个新指标")
        self.assertEqual(waiting.status, RunStatus.WAITING_FOR_DECISION)
        self.assertEqual(sandbox.execution_calls, 0)
        receipt = waiting.action_receipt
        pending = receipt["approval"]
        self.assertEqual(pending["run_id"], waiting.run_id)
        self.assertEqual(pending["version"], 1)

        approved = runtime._approval_store.resolve(
            pending["approval_id"],
            action="approve",
            domain_id=runtime.domain_id,
            expected_version=1,
            expected_fingerprint=pending["receipt_fingerprint"],
        )
        rehydrate = rehydrate_approved_tools(
            registry=runtime._registry,
            records=[approved],
            handler_factory=runtime._proposal_validator.handler_for,
            domain_id=runtime.domain_id,
        )
        self.assertEqual(rehydrate["bound_count"], 1)
        resumed = runtime.apply_tool_approval(approved.as_dict())

        self.assertEqual(resumed.run_id, waiting.run_id)
        self.assertEqual(resumed.status, RunStatus.COMPLETED, resumed.error)
        self.assertEqual(sandbox.execution_calls, 1)
        self.assertEqual(resumed.action_receipt["state"], "approved_resume")
        self.assertEqual(
            resumed.action_receipt["approval"]["receipt_fingerprint"],
            pending["receipt_fingerprint"],
        )

    def test_approval_resume_projects_accepted_tool_into_safe_model_history(self):
        sandbox = _Sandbox()
        runtime = self._runtime(sandbox)
        runtime._planner = _ApprovalAwarePlanner()
        waiting = runtime.run("计算一个新指标")
        self.assertEqual(waiting.status, RunStatus.WAITING_FOR_DECISION)
        pending = waiting.action_receipt["approval"]

        approved = runtime._approval_store.resolve(
            pending["approval_id"],
            action="approve",
            domain_id=runtime.domain_id,
            expected_version=1,
            expected_fingerprint=pending["receipt_fingerprint"],
        )
        rehydrate_approved_tools(
            registry=runtime._registry,
            records=[approved],
            handler_factory=runtime._proposal_validator.handler_for,
            domain_id=runtime.domain_id,
        )
        resumed = runtime.apply_tool_approval(approved.as_dict())

        self.assertEqual(
            resumed.status,
            RunStatus.COMPLETED,
            "{}; planner_calls={}; react={}".format(
                resumed.error,
                runtime._planner.calls,
                resumed.react_evidence,
            ),
        )
        self.assertEqual(sandbox.execution_calls, 1)

    def test_rejection_closes_waiting_run_without_execution(self):
        sandbox = _Sandbox()
        runtime = self._runtime(sandbox)
        waiting = runtime.run("拒绝一个新指标")
        pending = waiting.action_receipt["approval"]
        rejected = runtime._approval_store.resolve(
            pending["approval_id"],
            action="reject",
            domain_id=runtime.domain_id,
            expected_version=1,
            expected_fingerprint=pending["receipt_fingerprint"],
        )
        closed = runtime.apply_tool_approval(rejected.as_dict())
        self.assertEqual(closed.status, RunStatus.REJECTED)
        self.assertEqual(closed.action_receipt["state"], "closed_without_execution")
        self.assertEqual(sandbox.execution_calls, 0)

    def test_service_approval_projects_the_resumed_run(self):
        sandbox = _Sandbox()
        domain = _Domain()
        with tempfile.TemporaryDirectory() as directory:
            service = AgentService(
                domain_pack=domain,
                state_db_path=str(Path(directory) / "m328.db"),
            )

            def factory(planner, backend, **kwargs):
                return AgentRuntime(
                    _Planner(),
                    ToolRegistry(
                        {
                            "existing_tool": {
                                "name": "existing_tool",
                                "input_schema": {"type": "object"},
                                "output_schema": {"type": "object"},
                            }
                        },
                        lambda name, arguments: {},
                    ),
                    answer_composer=_Answer(),
                    backend_name=backend,
                    planner_name=planner,
                    domain_pack=domain,
                    proposal_validator=ToolProposalValidator(sandbox),
                    max_retries=0,
                    **kwargs,
                )

            service._state._runtime_factory = factory
            service._catalog_application._runtime_factory = factory
            try:
                waiting = service.run("计算一个新指标", planner="openai", backend="memory")
                self.assertEqual(waiting["status"], RunStatus.WAITING_FOR_DECISION.value)
                pending = waiting["action_receipt"]["approval"]
                self.assertEqual(pending["run_id"], waiting["run_id"])
                resolved = service.resolve_tool_approval(
                    pending["approval_id"],
                    action="approve",
                    expected_version=pending["version"],
                    receipt_fingerprint=pending["receipt_fingerprint"],
                )
                self.assertEqual(resolved["run"]["run_id"], waiting["run_id"])
                self.assertEqual(resolved["run"]["status"], RunStatus.COMPLETED.value)
                self.assertEqual(resolved["approval"]["status"], "approved")
                self.assertEqual(sandbox.execution_calls, 1)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
