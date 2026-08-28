"""Compact M318 contracts for policy, ReAct actions and safe evidence."""

from __future__ import annotations

import json
import os
import unittest

from agent.agent_settings import open_agent_defaults
from agent.react.contracts import (
    REACT_DECISION_SCHEMA_VERSION,
    REACT_EVIDENCE_SCHEMA_VERSION,
    ReactDecisionError,
    build_react_evidence,
    normalize_react_decision,
    normalize_react_evidence,
    project_react_decision,
)
from agent.runtime_core.execution_policy import (
    EXECUTION_POLICY_SCHEMA_VERSION,
    ExecutionPolicyError,
    build_execution_policy,
    normalize_execution_policy,
    validate_execution_policy,
)


class M318OpenAgentContractTests(unittest.TestCase):
    def test_product_defaults_enable_full_react_search_and_proposals(self):
        names = [
            "SPATIAL_AGENT_REACT_MODE",
            "SPATIAL_AGENT_WEB_SEARCH_ENABLED",
            "SPATIAL_AGENT_TOOL_PROPOSALS_ENABLED",
        ]
        old = {name: os.environ.get(name) for name in names}
        try:
            for name in names:
                os.environ.pop(name, None)
            defaults = open_agent_defaults()
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.assertEqual(defaults["react_mode"], "full")
        self.assertTrue(defaults["web_search_enabled"])
        self.assertTrue(defaults["tool_proposals_enabled"])

    def test_execution_policy_is_validated_against_server_allowlists(self):
        policy = build_execution_policy(
            mode="react",
            allowed_tools=["get_dataset_schema"],
            allowed_result_profiles=["raster"],
        )
        result = validate_execution_policy(
            policy,
            known_tools=["get_dataset_schema"],
            known_result_profiles=["raster", "vector"],
        )
        self.assertEqual(result["schema_version"], EXECUTION_POLICY_SCHEMA_VERSION)
        self.assertTrue(result["network_enabled"])
        self.assertTrue(result["tool_proposals_enabled"])

    def test_execution_policy_rejects_unknown_tool(self):
        policy = build_execution_policy(mode="direct_tool", allowed_tools=["not_registered"])
        with self.assertRaises(ExecutionPolicyError):
            validate_execution_policy(policy, known_tools=["registered"])

    def test_react_tool_action_requires_registered_tool_and_object_args(self):
        decision = normalize_react_decision(
            {
                "schema_version": REACT_DECISION_SCHEMA_VERSION,
                "action": "call_tool",
                "tool_name": "get_dataset_schema",
                "arguments": {"dataset": "dem"},
            },
            allowed_tools=["get_dataset_schema"],
        )
        self.assertEqual(decision["tool_name"], "get_dataset_schema")
        self.assertEqual(decision["arguments"], {"dataset": "dem"})

    def test_react_search_and_proposal_obey_policy_switches(self):
        search = {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "search",
            "query": "公开统计资料",
        }
        with self.assertRaises(ReactDecisionError):
            normalize_react_decision(search, network_enabled=False)
        proposal = {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "propose_tool",
            "proposal": {
                "name": "safe_metric",
                "description": "计算指标",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            },
        }
        with self.assertRaises(ReactDecisionError):
            normalize_react_decision(proposal, tool_proposals_enabled=False)

    def test_react_action_rejects_cross_action_fields(self):
        with self.assertRaises(ReactDecisionError):
            normalize_react_decision(
                {
                    "schema_version": REACT_DECISION_SCHEMA_VERSION,
                    "action": "call_tool",
                    "tool_name": "get_dataset_schema",
                    "arguments": {},
                    "query": "不应出现",
                },
                allowed_tools=["get_dataset_schema"],
            )

    def test_evidence_projection_does_not_expose_arguments_or_source(self):
        decision = {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "propose_tool",
            "summary": "提出计算工具",
            "proposal": {
                "name": "safe_metric",
                "description": "计算指标",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "source": "secret source must not enter evidence",
            },
        }
        evidence = build_react_evidence(
            decision,
            turn_index=2,
            validation_state="accepted",
        )
        rendered = json.dumps(evidence, ensure_ascii=False)
        self.assertEqual(evidence["schema_version"], REACT_EVIDENCE_SCHEMA_VERSION)
        self.assertNotIn("secret source", rendered)
        self.assertNotIn("arguments", rendered)

    def test_invalid_persisted_evidence_fails_closed(self):
        evidence = normalize_react_evidence({"schema_version": "old"})
        self.assertEqual(evidence["validation_state"], "blocked")
        self.assertEqual(evidence["reason_code"], "react_evidence_unknown_schema")
        projection = project_react_decision({"action": "unknown"})
        self.assertEqual(projection["action"], "reject")


if __name__ == "__main__":
    unittest.main()
