"""Compact M322 contracts for safe Python tool proposals."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.models import RunStatus
from agent.react.contracts import REACT_DECISION_SCHEMA_VERSION
from agent.react.loop import ReactLoop
from agent.request_model import RequestFacts
from agent.runtime import AgentRuntime
from agent.runtime_state import InMemoryStateStore
from agent.sqlite_store import SQLiteStateStore
from agent.tooling import (
    TOOL_PROPOSAL_RECEIPT_SCHEMA_VERSION,
    ToolProposalValidator,
    UnixSocketSandboxClient,
    normalize_tool_proposal,
    validate_source_ast,
)
from agent.tools import ToolRegistry


def _proposal(source: str = 'def run(arguments):\n    return {"value": arguments["value"]}\n'):
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
        "source": source,
        "example_arguments": {"value": 3},
    }


class _FakeSandbox:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def validate_and_run(self, proposal):
        self.calls.append(proposal)
        return self.response


class M322ProposalContractTests(unittest.TestCase):
    def test_normalization_assigns_stable_hashes_and_requires_example(self):
        normalized = normalize_tool_proposal(_proposal())
        self.assertEqual(normalized["schema_version"], "spatial-agent.tool-proposal.v1")
        self.assertTrue(normalized["proposal_id"].startswith("proposal-"))
        self.assertTrue(normalized["source_hash"].startswith("sha256:"))
        self.assertTrue(normalized["schema_hash"].startswith("sha256:"))
        with self.assertRaisesRegex(ValueError, "example_arguments"):
            normalize_tool_proposal({key: value for key, value in _proposal().items() if key != "example_arguments"})

    def test_ast_policy_rejects_effects_and_accepts_pure_function(self):
        self.assertEqual(validate_source_ast(_proposal()["source"])["status"], "passed")
        for source, reason in (
            ("import os\ndef run(arguments):\n    return {}\n", "proposal_ast_forbidden_node"),
            ("def run(arguments):\n    return open('x')\n", "proposal_call_forbidden"),
            ("def run(arguments):\n    return arguments.x\n", "proposal_attribute_forbidden"),
            ("def run(arguments):\n    return exec('1')\n", "proposal_call_forbidden"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(validate_source_ast(source)["reason_code"], reason)

    def test_validator_returns_receipt_without_source_or_sample(self):
        sandbox = _FakeSandbox(
            {
                "status": "validated",
                "reason_code": "proposal_validated",
                "output_bytes": 12,
                "checks": {"execution": "passed"},
            }
        )
        receipt = ToolProposalValidator(sandbox).validate(
            _proposal(), existing_tools=("web_search",)
        )
        self.assertEqual(receipt["status"], "validated")
        self.assertEqual(receipt["schema_version"], TOOL_PROPOSAL_RECEIPT_SCHEMA_VERSION)
        self.assertIn("source_hash", receipt)
        self.assertNotIn("source", receipt)
        self.assertNotIn("example_arguments", receipt)
        self.assertEqual(len(sandbox.calls), 1)

    def test_validator_fails_closed_when_sandbox_is_unavailable(self):
        receipt = ToolProposalValidator(None).validate(_proposal())
        self.assertEqual(receipt["status"], "unavailable")
        self.assertEqual(receipt["reason_code"], "sandbox_unavailable")


@unittest.skipUnless(os.name == "posix", "sandbox worker uses Unix sockets")
class M322SandboxWorkerTests(unittest.TestCase):
    def test_worker_validates_pure_code_and_rejects_import(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            socket_path = str(Path(directory) / "worker.sock")
            environment = os.environ.copy()
            environment["SPATIAL_AGENT_TOOL_PROPOSAL_SANDBOX_SOCKET"] = socket_path
            worker = subprocess.Popen(
                [sys.executable, "-m", "agent.tooling.sandbox_worker"],
                cwd=root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(40):
                    if Path(socket_path).exists():
                        break
                    time.sleep(0.05)
                client = UnixSocketSandboxClient(socket_path, timeout_seconds=3)
                validated = client.validate_and_run(_proposal())
                self.assertEqual(validated["status"], "validated")
                rejected = client.validate_and_run(
                    normalize_tool_proposal(
                        _proposal("import os\ndef run(arguments):\n    return {\"value\": 1}\n")
                    )
                )
                self.assertEqual(rejected["status"], "rejected")
                self.assertEqual(rejected["reason_code"], "proposal_ast_forbidden_node")
            finally:
                worker.terminate()
                worker.wait(timeout=3)


class _ProposalPlanner:
    react_enabled = True
    execution_policy_mode = "react"

    def __init__(self):
        self.calls = 0

    def decide(self, request, **kwargs):
        self.calls += 1
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "propose_tool",
            "summary": "缺少现有计算能力，提出纯计算工具",
            "proposal": _proposal(),
        }

    def metrics(self):
        return {"execution_mode": "proposal-test"}


class _ProposalDomain:
    domain_id = "m322-test"

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
        return {"domain_id": self.domain_id, "candidate_ids": [], "candidate_count": 0, "selected_capability_id": None}

    def extract_request_facts(self, request):
        return RequestFacts(text=request, admin_name=None, tasks=(), datasets=(), constraints={}, evidence=("answer",))


class _ProposalAnswer:
    def compose_failure(self, result):
        return "提案未完成。"


class M322ReactRuntimeTests(unittest.TestCase):
    def test_proposal_waits_for_approval_and_never_enters_registry(self):
        registry = ToolRegistry(
            {
                "existing_tool": {
                    "name": "existing_tool",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            },
            lambda name, arguments: {},
        )
        validator = ToolProposalValidator(
            _FakeSandbox({"status": "validated", "reason_code": "proposal_validated"})
        )
        defaults = {
            "react_mode": "full",
            "web_search_enabled": False,
            "tool_proposals_enabled": True,
            "react_max_turns": 8,
            "react_max_actions": 12,
        }
        with patch("agent.runtime.open_agent_defaults", return_value=defaults):
            runtime = AgentRuntime(
                _ProposalPlanner(),
                registry,
                state_store=InMemoryStateStore(),
                answer_composer=_ProposalAnswer(),
                planner_name="openai",
                domain_pack=_ProposalDomain(),
                proposal_validator=validator,
                max_retries=0,
            )
        result = runtime.run("计算一个没有现有工具支持的指标")
        self.assertEqual(result.status, RunStatus.WAITING_FOR_DECISION, result.error)
        self.assertEqual(result.react_evidence["state"], "awaiting_approval")
        self.assertEqual(result.action_receipt["state"], "awaiting_approval")
        self.assertEqual(registry.names, ("existing_tool",))
        receipt = result.to_dict()["action_receipt"]["receipt"]
        self.assertNotIn("source", receipt)
        self.assertNotIn("example_arguments", receipt)
        self.assertIn(
            "react_tool_proposal_awaiting_approval",
            str(result.to_dict()),
        )

    def test_proposal_receipt_survives_sqlite_restore(self):
        registry = ToolRegistry(
            {
                "existing_tool": {
                    "name": "existing_tool",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            },
            lambda name, arguments: {},
        )
        validator = ToolProposalValidator(
            _FakeSandbox({"status": "validated", "reason_code": "proposal_validated"})
        )
        defaults = {
            "react_mode": "full",
            "web_search_enabled": False,
            "tool_proposals_enabled": True,
            "react_max_turns": 8,
            "react_max_actions": 12,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStateStore(str(Path(directory) / "state.db"), legacy_domain_id="m322-test")
            with patch("agent.runtime.open_agent_defaults", return_value=defaults):
                runtime = AgentRuntime(
                    _ProposalPlanner(),
                    registry,
                    state_store=store,
                    answer_composer=_ProposalAnswer(),
                    planner_name="openai",
                    domain_pack=_ProposalDomain(),
                    proposal_validator=validator,
                    max_retries=0,
                )
            result = runtime.run("持久化一个待审批工具提案")
            restored = store.get(result.run_id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.status, RunStatus.WAITING_FOR_DECISION)
        self.assertEqual(restored.action_receipt, result.action_receipt)
        self.assertNotIn("source", restored.to_dict()["action_receipt"]["receipt"])


if __name__ == "__main__":
    unittest.main()
