"""Domain-neutral execution-policy contract.

The policy is the seam between capability discovery and execution.  A Domain
Pack may contribute policy metadata, but callers only need this small,
validated projection to decide whether a request uses a direct tool, a
generated DAG, an explicit workflow, or the bounded ReAct loop.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable, Mapping
from typing import Any


EXECUTION_POLICY_SCHEMA_VERSION = "spatial-agent.execution-policy.v1"
EXECUTION_POLICY_MODES = frozenset(
    {"direct_tool", "generated_dag", "domain_workflow", "react"}
)
EXECUTION_POLICY_STATES = frozenset({"ready", "unavailable"})
DEFAULT_REACT_MAX_TURNS = 8
DEFAULT_REACT_MAX_ACTIONS = 12
_MAX_ITEMS = 32
_MAX_TEXT = 96


class ExecutionPolicyError(ValueError):
    """Raised when an execution policy cannot cross the public seam."""


EXECUTION_POLICY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema_version",
        "mode",
        "allowed_tools",
        "allowed_result_profiles",
        "max_actions",
        "max_turns",
        "requires_confirmation",
        "network_enabled",
        "tool_proposals_enabled",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string", "const": EXECUTION_POLICY_SCHEMA_VERSION},
        "state": {"type": "string", "enum": sorted(EXECUTION_POLICY_STATES)},
        "mode": {"type": "string", "enum": sorted(EXECUTION_POLICY_MODES)},
        "allowed_tools": {
            "type": "array",
            "maxItems": _MAX_ITEMS,
            "items": {"type": "string", "maxLength": _MAX_TEXT},
        },
        "allowed_result_profiles": {
            "type": "array",
            "maxItems": _MAX_ITEMS,
            "items": {"type": "string", "maxLength": _MAX_TEXT},
        },
        "max_actions": {"type": "integer", "minimum": 1, "maximum": 128},
        "max_turns": {"type": "integer", "minimum": 1, "maximum": 32},
        "requires_confirmation": {"type": "boolean"},
        "network_enabled": {"type": "boolean"},
        "tool_proposals_enabled": {"type": "boolean"},
        "source": {"type": "string", "maxLength": _MAX_TEXT},
        "reason_code": {"type": "string", "maxLength": _MAX_TEXT},
    },
}


def execution_policy_schema() -> dict[str, Any]:
    """Return a copy so a provider cannot mutate the shared schema."""

    return deepcopy(EXECUTION_POLICY_SCHEMA)


def build_execution_policy(
    *,
    mode: str = "react",
    allowed_tools: Iterable[Any] = (),
    allowed_result_profiles: Iterable[Any] = (),
    max_actions: int = DEFAULT_REACT_MAX_ACTIONS,
    max_turns: int = DEFAULT_REACT_MAX_TURNS,
    requires_confirmation: bool = False,
    network_enabled: bool = True,
    tool_proposals_enabled: bool = True,
    state: str = "ready",
    source: str = "runtime",
    reason_code: str = "policy_resolved",
) -> dict[str, Any]:
    """Build a bounded JSON-safe policy projection."""

    normalized_mode = _text(mode)
    if normalized_mode not in EXECUTION_POLICY_MODES:
        raise ExecutionPolicyError("unsupported execution policy mode")
    normalized_state = _text(state)
    if normalized_state not in EXECUTION_POLICY_STATES:
        raise ExecutionPolicyError("unsupported execution policy state")
    if not isinstance(max_actions, int) or isinstance(max_actions, bool):
        raise ExecutionPolicyError("max_actions must be an integer")
    if not isinstance(max_turns, int) or isinstance(max_turns, bool):
        raise ExecutionPolicyError("max_turns must be an integer")
    if not 1 <= max_actions <= 128:
        raise ExecutionPolicyError("max_actions must be between 1 and 128")
    if not 1 <= max_turns <= 32:
        raise ExecutionPolicyError("max_turns must be between 1 and 32")
    for name, value in {
        "requires_confirmation": requires_confirmation,
        "network_enabled": network_enabled,
        "tool_proposals_enabled": tool_proposals_enabled,
    }.items():
        if not isinstance(value, bool):
            raise ExecutionPolicyError(name + " must be boolean")
    return {
        "schema_version": EXECUTION_POLICY_SCHEMA_VERSION,
        "state": normalized_state,
        "mode": normalized_mode,
        "allowed_tools": _strings(allowed_tools),
        "allowed_result_profiles": _strings(allowed_result_profiles),
        "max_actions": max_actions,
        "max_turns": max_turns,
        "requires_confirmation": requires_confirmation,
        "network_enabled": network_enabled,
        "tool_proposals_enabled": tool_proposals_enabled,
        "source": _text(source) or "runtime",
        "reason_code": _text(reason_code) or "policy_resolved",
    }


def normalize_execution_policy(value: Any) -> dict[str, Any]:
    """Normalize persisted policy data; invalid data fails closed."""

    if not isinstance(value, Mapping):
        return build_execution_policy(
            mode="react",
            state="unavailable",
            source="normalizer",
            reason_code="policy_missing",
        )
    try:
        normalized = build_execution_policy(
            mode=value.get("mode", "react"),
            allowed_tools=value.get("allowed_tools", []),
            allowed_result_profiles=value.get("allowed_result_profiles", []),
            max_actions=value.get("max_actions", DEFAULT_REACT_MAX_ACTIONS),
            max_turns=value.get("max_turns", DEFAULT_REACT_MAX_TURNS),
            requires_confirmation=value.get("requires_confirmation", False),
            network_enabled=value.get("network_enabled", False),
            tool_proposals_enabled=value.get("tool_proposals_enabled", False),
            state=value.get("state", "ready"),
            source=value.get("source", "persisted"),
            reason_code=value.get("reason_code", "policy_normalized"),
        )
    except (ExecutionPolicyError, TypeError, ValueError):
        return build_execution_policy(
            mode="react",
            state="unavailable",
            source="normalizer",
            reason_code="policy_invalid",
        )
    if value.get("schema_version") != EXECUTION_POLICY_SCHEMA_VERSION:
        normalized["state"] = "unavailable"
        normalized["reason_code"] = "policy_unknown_schema"
    return normalized


def validate_execution_policy(
    value: Mapping[str, Any],
    *,
    known_tools: Iterable[Any] | None = None,
    known_result_profiles: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Validate a policy against optional server-owned allowlists."""

    if not isinstance(value, Mapping):
        raise ExecutionPolicyError("execution policy must be an object")
    if value.get("schema_version") != EXECUTION_POLICY_SCHEMA_VERSION:
        raise ExecutionPolicyError("execution policy schema_version is unsupported")
    normalized = build_execution_policy(
        mode=value.get("mode"),
        allowed_tools=value.get("allowed_tools"),
        allowed_result_profiles=value.get("allowed_result_profiles"),
        max_actions=value.get("max_actions"),
        max_turns=value.get("max_turns"),
        requires_confirmation=value.get("requires_confirmation"),
        network_enabled=value.get("network_enabled"),
        tool_proposals_enabled=value.get("tool_proposals_enabled"),
        state=value.get("state", "ready"),
        source=value.get("source", "runtime"),
        reason_code=value.get("reason_code", "policy_validated"),
    )
    if set(value) - set(EXECUTION_POLICY_SCHEMA["properties"]):
        raise ExecutionPolicyError("execution policy contains unknown fields")
    if known_tools is not None:
        allowed = {str(item) for item in known_tools}
        unknown = [item for item in normalized["allowed_tools"] if item not in allowed]
        if unknown:
            raise ExecutionPolicyError("execution policy contains unknown tools")
    if known_result_profiles is not None:
        allowed_profiles = {str(item) for item in known_result_profiles}
        unknown = [
            item
            for item in normalized["allowed_result_profiles"]
            if item not in allowed_profiles
        ]
        if unknown:
            raise ExecutionPolicyError("execution policy contains unknown result profiles")
    return normalized


def _text(value: Any) -> str:
    return str(value or "").strip()[:_MAX_TEXT]


def _strings(value: Iterable[Any] | Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set, frozenset)) else []
    result: list[str] = []
    for item in values:
        text = _text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= _MAX_ITEMS:
            break
    return result


__all__ = [
    "DEFAULT_REACT_MAX_ACTIONS",
    "DEFAULT_REACT_MAX_TURNS",
    "EXECUTION_POLICY_MODES",
    "EXECUTION_POLICY_SCHEMA_VERSION",
    "EXECUTION_POLICY_SCHEMA",
    "EXECUTION_POLICY_STATES",
    "ExecutionPolicyError",
    "build_execution_policy",
    "execution_policy_schema",
    "normalize_execution_policy",
    "validate_execution_policy",
]
