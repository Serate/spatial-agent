"""Versioned ReAct decision and evidence contracts.

This module validates the action envelope, but deliberately does not invoke a
tool, fetch a URL, or execute proposed source.  Those effects belong behind
separate Runtime policy and approval seams.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable, Mapping
from typing import Any


REACT_DECISION_SCHEMA_VERSION = "spatial-agent.react-decision.v1"
REACT_EVIDENCE_SCHEMA_VERSION = "spatial-agent.react-evidence.v1"
REACT_ACTIONS = frozenset(
    {"call_tool", "search", "ask_clarification", "propose_tool", "finish", "reject"}
)
REACT_VALIDATION_STATES = frozenset({"proposed", "accepted", "blocked", "completed"})
REACT_SOURCES = frozenset({"model", "rule", "replay", "runtime"})
_MAX_SUMMARY = 240
_MAX_MESSAGE = 800
_MAX_QUERY = 512
_MAX_ITEMS = 16
_MAX_ARGUMENT_KEYS = 64
_MAX_SOURCE = 48_000


class ReactDecisionError(ValueError):
    """Raised when a ReAct decision cannot cross the Runtime seam."""


REACT_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "action"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {
            "type": "string",
            "const": REACT_DECISION_SCHEMA_VERSION,
        },
        "action": {"type": "string", "enum": sorted(REACT_ACTIONS)},
        "summary": {"type": "string", "maxLength": _MAX_SUMMARY},
        "tool_name": {"type": "string", "maxLength": 96},
        "arguments": {"type": "object"},
        "query": {"type": "string", "maxLength": _MAX_QUERY},
        "domains": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 96},
        },
        "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
        "message": {"type": "string", "maxLength": _MAX_MESSAGE},
        "output_type": {"type": "string", "maxLength": 96},
        "proposal": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "maxLength": 96},
                "description": {"type": "string", "maxLength": 400},
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "source": {"type": "string", "maxLength": _MAX_SOURCE},
            },
        },
    },
}


def react_decision_schema() -> dict[str, Any]:
    return deepcopy(REACT_DECISION_SCHEMA)


def normalize_react_decision(
    value: Any,
    *,
    allowed_tools: Iterable[Any] | None = None,
    network_enabled: bool = True,
    tool_proposals_enabled: bool = True,
) -> dict[str, Any]:
    """Validate and return one action without performing its side effect."""

    if not isinstance(value, Mapping):
        raise ReactDecisionError("react decision must be an object")
    if value.get("schema_version") != REACT_DECISION_SCHEMA_VERSION:
        raise ReactDecisionError("react decision schema_version is unsupported")
    unknown = set(value) - set(REACT_DECISION_SCHEMA["properties"])
    if unknown:
        raise ReactDecisionError("react decision contains unknown fields")
    action = _required_text(value, "action", 48)
    if action not in REACT_ACTIONS:
        raise ReactDecisionError("react decision action is unsupported")
    result: dict[str, Any] = {
        "schema_version": REACT_DECISION_SCHEMA_VERSION,
        "action": action,
    }
    for key, limit in (
        ("summary", _MAX_SUMMARY),
        ("tool_name", 96),
        ("query", _MAX_QUERY),
        ("message", _MAX_MESSAGE),
        ("output_type", 96),
    ):
        if key in value:
            result[key] = _required_text(value, key, limit)
    if "domains" in value:
        result["domains"] = _strings(value.get("domains"), 8)
    if "max_results" in value:
        max_results = value.get("max_results")
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ReactDecisionError("max_results must be an integer")
        if not 1 <= max_results <= 8:
            raise ReactDecisionError("max_results must be between 1 and 8")
        result["max_results"] = max_results
    if "arguments" in value:
        arguments = value.get("arguments")
        if not isinstance(arguments, dict):
            raise ReactDecisionError("arguments must be an object")
        if len(arguments) > _MAX_ARGUMENT_KEYS:
            raise ReactDecisionError("arguments contains too many fields")
        result["arguments"] = deepcopy(arguments)
    if "proposal" in value:
        result["proposal"] = _normalize_proposal(value.get("proposal"))

    if action == "call_tool":
        tool_name = result.get("tool_name")
        if not tool_name:
            raise ReactDecisionError("call_tool requires tool_name")
        if "arguments" not in result:
            raise ReactDecisionError("call_tool requires arguments")
        if allowed_tools is not None and tool_name not in {str(item) for item in allowed_tools}:
            raise ReactDecisionError("react decision selected an unregistered tool")
        _reject_fields(result, {"summary", "tool_name", "arguments", "output_type"})
    elif action == "search":
        if not network_enabled:
            raise ReactDecisionError("network search is disabled by policy")
        if not result.get("query"):
            raise ReactDecisionError("search requires query")
        _reject_fields(result, {"summary", "query", "domains", "max_results"})
    elif action in {"ask_clarification", "reject"}:
        if not result.get("message"):
            raise ReactDecisionError(action + " requires message")
        _reject_fields(result, {"summary", "message"})
    elif action == "propose_tool":
        if not tool_proposals_enabled:
            raise ReactDecisionError("tool proposals are disabled by policy")
        if not isinstance(result.get("proposal"), Mapping):
            raise ReactDecisionError("propose_tool requires proposal")
        _reject_fields(result, {"summary", "proposal"})
    elif action == "finish":
        _reject_fields(result, {"summary", "message", "output_type"})
    return result


def project_react_decision(value: Any) -> dict[str, Any]:
    """Project a decision for trace/UI use without arguments or source code."""

    try:
        decision = normalize_react_decision(value)
    except ReactDecisionError:
        return {
            "schema_version": REACT_DECISION_SCHEMA_VERSION,
            "action": "reject",
            "summary": "无效的 Agent 动作",
        }
    result = {
        "schema_version": REACT_DECISION_SCHEMA_VERSION,
        "action": decision["action"],
    }
    for key in ("summary", "tool_name", "query", "message", "output_type"):
        if key in decision:
            result[key] = decision[key]
    if isinstance(decision.get("arguments"), Mapping):
        result["argument_names"] = [
            str(key)[:96] for key in list(decision["arguments"])[:_MAX_ARGUMENT_KEYS]
        ]
    proposal = decision.get("proposal")
    if isinstance(proposal, Mapping):
        result["proposal"] = {
            key: proposal[key]
            for key in ("name", "description", "input_schema", "output_schema")
            if key in proposal
        }
    return result


def build_react_evidence(
    decision: Any,
    *,
    turn_index: int,
    validation_state: str = "proposed",
    policy_mode: str = "react",
    source: str = "model",
    action_id: str | None = None,
    reason_code: str | None = None,
    result_ref: str | None = None,
    citation_count: int = 0,
) -> dict[str, Any]:
    """Build a bounded, safe evidence record for one ReAct turn."""

    if isinstance(turn_index, bool) or not isinstance(turn_index, int) or turn_index < 0:
        raise ReactDecisionError("turn_index must be a non-negative integer")
    if validation_state not in REACT_VALIDATION_STATES:
        raise ReactDecisionError("react evidence validation_state is unsupported")
    normalized_source = source if source in REACT_SOURCES else "runtime"
    projected = project_react_decision(decision)
    evidence: dict[str, Any] = {
        "schema_version": REACT_EVIDENCE_SCHEMA_VERSION,
        "turn_index": min(turn_index, 128),
        "validation_state": validation_state,
        "policy_mode": str(policy_mode or "react")[:48],
        "source": normalized_source,
        "decision": projected,
        "action_id": str(action_id or "")[:96] or None,
        "reason_code": str(reason_code or "")[:96] or None,
        "result_ref": str(result_ref or "")[:160] or None,
        "citation_count": max(0, min(int(citation_count), 64)),
    }
    return evidence


def normalize_react_evidence(value: Any) -> dict[str, Any]:
    """Normalize persisted evidence and degrade unknown values safely."""

    if not isinstance(value, Mapping) or value.get("schema_version") != REACT_EVIDENCE_SCHEMA_VERSION:
        return {
            "schema_version": REACT_EVIDENCE_SCHEMA_VERSION,
            "turn_index": 0,
            "validation_state": "blocked",
            "policy_mode": "unknown",
            "source": "runtime",
            "decision": {"action": "reject", "summary": "Agent 动作证据不可用"},
            "action_id": None,
            "reason_code": "react_evidence_unknown_schema",
            "result_ref": None,
            "citation_count": 0,
        }
    state = value.get("validation_state")
    if state not in REACT_VALIDATION_STATES:
        state = "blocked"
    source = value.get("source") if value.get("source") in REACT_SOURCES else "runtime"
    turn_index = value.get("turn_index")
    if isinstance(turn_index, bool) or not isinstance(turn_index, int):
        turn_index = 0
    return {
        "schema_version": REACT_EVIDENCE_SCHEMA_VERSION,
        "turn_index": max(0, min(turn_index, 128)),
        "validation_state": state,
        "policy_mode": str(value.get("policy_mode") or "unknown")[:48],
        "source": source,
        "decision": project_react_decision(value.get("decision")),
        "action_id": str(value.get("action_id") or "")[:96] or None,
        "reason_code": str(value.get("reason_code") or "")[:96] or None,
        "result_ref": str(value.get("result_ref") or "")[:160] or None,
        "citation_count": _bounded_int(value.get("citation_count"), 0, 64),
    }


def _normalize_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReactDecisionError("proposal must be an object")
    allowed = {"name", "description", "input_schema", "output_schema", "source"}
    if set(value) - allowed:
        raise ReactDecisionError("proposal contains unknown fields")
    name = _required_text(value, "name", 96)
    description = _required_text(value, "description", 400)
    input_schema = value.get("input_schema")
    output_schema = value.get("output_schema")
    source = value.get("source")
    if not isinstance(input_schema, Mapping) or not isinstance(output_schema, Mapping):
        raise ReactDecisionError("proposal schemas must be objects")
    if source is not None and (not isinstance(source, str) or len(source) > _MAX_SOURCE):
        raise ReactDecisionError("proposal source is invalid")
    result = {
        "name": name,
        "description": description,
        "input_schema": deepcopy(dict(input_schema)),
        "output_schema": deepcopy(dict(output_schema)),
    }
    if source is not None:
        result["source"] = source
    return result


def _required_text(value: Mapping[str, Any], key: str, limit: int) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ReactDecisionError(key + " must be a non-empty string")
    return item.strip()[:limit]


def _strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        raise ReactDecisionError("domains must be an array")
    result: list[str] = []
    for item in value[:limit]:
        if not isinstance(item, str) or not item.strip():
            raise ReactDecisionError("domains must contain non-empty strings")
        text = item.strip()[:96]
        if text not in result:
            result.append(text)
    return result


def _reject_fields(value: Mapping[str, Any], allowed: set[str]) -> None:
    present = set(value) - {"schema_version", "action"}
    if present - allowed:
        raise ReactDecisionError("action contains fields for another action")


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return minimum
    return max(minimum, min(value, maximum))


__all__ = [
    "REACT_ACTIONS",
    "REACT_DECISION_SCHEMA",
    "REACT_DECISION_SCHEMA_VERSION",
    "REACT_EVIDENCE_SCHEMA_VERSION",
    "ReactDecisionError",
    "build_react_evidence",
    "normalize_react_decision",
    "normalize_react_evidence",
    "project_react_decision",
    "react_decision_schema",
]
