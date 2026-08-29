"""Domain-neutral execution-policy contract.

The policy is the seam between capability discovery and execution.  A Domain
Pack may contribute policy metadata, but callers only need this small,
validated projection to decide whether a request uses a direct tool, a
generated DAG, an explicit workflow, or the bounded ReAct loop. Open ReAct is
a Runtime execution surface, not an automatically selected Domain workflow.
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

    def __init__(
        self,
        message: str,
        *,
        code: str = "execution_policy_invalid",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code or "execution_policy_invalid")[:96]
        self.details = dict(details) if isinstance(details, Mapping) else {}
        super().__init__(message)


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
        # The following fields are legacy governance evidence retained on the
        # Runtime projection.  They are optional and never participate in
        # policy resolution or authorization.
        "provider_id": {"type": "string", "maxLength": _MAX_TEXT},
        "dependency_evidence_required": {"type": "boolean"},
        "allowed_permission_count": {"type": "integer", "minimum": 0},
        "wildcard_permission": {"type": "boolean"},
        "approved_tool_count": {"type": "integer", "minimum": 0},
        "tools": {
            "type": "array",
            "maxItems": _MAX_ITEMS,
            "items": {"type": "object"},
        },
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


class ExecutionPolicyResolver:
    """Resolve and validate the execution mode for one accepted TaskPlan.

    This class is deliberately Domain-neutral.  A Domain Pack may provide
    descriptive policy metadata through its existing ``plan_policy`` seam,
    but the resolver never imports a Domain, invokes a tool, opens a socket,
    or treats a workflow identifier as executable code.  It is therefore safe
    to use from synchronous planning, preview, recovery, and artifact paths.

    ``known_result_profiles`` is optional for compatibility with old custom
    Domain Packs that used result labels not yet registered in the default
    registry.  When supplied, the server-owned allowlist is enforced.
    Domain-declared result types remain enforced in either case.
    """

    def __init__(
        self,
        *,
        known_tools: Iterable[Any] = (),
        known_result_profiles: Iterable[Any] | None = None,
        max_actions: int = DEFAULT_REACT_MAX_ACTIONS,
        max_turns: int = DEFAULT_REACT_MAX_TURNS,
        network_enabled: bool = True,
        tool_proposals_enabled: bool = True,
        enforce_known_result_profiles: bool = True,
    ) -> None:
        self._known_tools = tuple(_iter_strings(known_tools))
        raw_profiles = (
            tuple(_iter_strings(known_result_profiles))
            if known_result_profiles is not None
            else None
        )
        self._known_result_profiles = raw_profiles
        self._enforce_known_result_profiles = bool(enforce_known_result_profiles)
        self._max_actions = _bounded_constructor_int(
            max_actions, minimum=1, maximum=128, name="max_actions"
        )
        self._max_turns = _bounded_constructor_int(
            max_turns, minimum=1, maximum=32, name="max_turns"
        )
        if not isinstance(network_enabled, bool):
            raise ExecutionPolicyError("network_enabled must be boolean")
        if not isinstance(tool_proposals_enabled, bool):
            raise ExecutionPolicyError("tool_proposals_enabled must be boolean")
        self._network_enabled = network_enabled
        self._tool_proposals_enabled = tool_proposals_enabled

    @property
    def known_tools(self) -> tuple[str, ...]:
        """Return the immutable server-owned tool allowlist."""

        return self._known_tools

    def resolve(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
        domain_policy: Mapping[str, Any] | None = None,
        requested_mode: str | None = None,
        requires_confirmation: bool = False,
        open_react: bool = False,
    ) -> dict[str, Any]:
        """Build a bounded policy from trusted planning-side metadata."""

        steps = _plan_steps(plan)
        output_type = _plan_output_type(plan)
        workflow_value = workflow if isinstance(workflow, Mapping) else {}
        domain_value = domain_policy if isinstance(domain_policy, Mapping) else {}
        has_workflow = _has_workflow_identity(workflow_value)
        domain_available = _domain_policy_available(domain_value)
        if _bool_value(
            domain_value.get("workflow_required")
            or domain_value.get("requires_workflow")
        ) and not has_workflow:
            raise ExecutionPolicyError(
                "this Domain policy requires an explicit workflow",
                code="execution_policy_workflow_required",
            )
        # An open ReAct request is governed by the Runtime/Registry boundary.
        # An automatically inferred Domain template is advisory here; only an
        # explicitly selected workflow may narrow the action set.
        open_react_mode = bool(open_react and not has_workflow)
        if open_react_mode:
            domain_value = {}
            domain_available = False

        normalized_requested = _normalized_mode(requested_mode)
        if requested_mode is not None and normalized_requested is None:
            raise ExecutionPolicyError(
                "requested execution policy mode is unsupported",
                code="execution_policy_mode_invalid",
            )
        mode = normalized_requested or self._mode_for_plan(
            steps,
            has_workflow=has_workflow,
            domain_available=domain_available,
        )

        declared_tools = _first_strings(
            workflow_value.get("allowed_tools"),
            domain_value.get("allowed_tools"),
        )
        actual_tools = _unique_strings(
            getattr(step, "tool", None) for step in steps
        )
        allowed_tools = declared_tools or actual_tools
        declared_results = _first_strings(
            workflow_value.get("result_types"),
            domain_value.get("result_types"),
        )
        allowed_results = declared_results or ([output_type] if output_type else [])

        max_actions = self._max_actions
        for source in (workflow_value, domain_value):
            candidate = _first_int(source.get("max_actions"), source.get("max_steps"))
            if candidate is not None:
                max_actions = min(max_actions, candidate)
        if mode == "direct_tool":
            max_actions = min(max_actions, 1)

        max_turns = self._max_turns if mode == "react" else 1
        for source in (workflow_value, domain_value):
            candidate = _first_int(source.get("max_turns"))
            if candidate is not None:
                max_turns = min(max_turns, candidate)

        confirmation = bool(
            requires_confirmation
            or _bool_value(workflow_value.get("requires_confirmation"))
            or _bool_value(domain_value.get("requires_confirmation"))
        )
        if has_workflow:
            source = "explicit_workflow"
            reason_code = "explicit_workflow_selected"
        elif open_react_mode:
            source = "open_react"
            reason_code = "open_react_policy_selected"
        elif domain_available:
            source = "domain_catalog"
            reason_code = "domain_policy_selected"
        elif mode == "react":
            source = "runtime"
            reason_code = "react_mode_requested"
        else:
            source = "runtime"
            reason_code = "plan_shape_selected"
        return build_execution_policy(
            mode=mode,
            allowed_tools=allowed_tools,
            allowed_result_profiles=allowed_results,
            max_actions=max_actions,
            max_turns=max_turns,
            requires_confirmation=confirmation,
            network_enabled=self._network_enabled,
            tool_proposals_enabled=self._tool_proposals_enabled,
            source=source,
            reason_code=reason_code,
        )

    def validate_plan(self, plan: Any, policy: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a TaskPlan against the resolved policy and server lists."""

        known_tools = self._known_tools if self._known_tools else None
        known_profiles = (
            self._known_result_profiles
            if self._enforce_known_result_profiles
            else None
        )
        normalized = validate_execution_policy(
            policy,
            known_tools=known_tools,
            known_result_profiles=known_profiles,
        )
        if normalized.get("state") != "ready":
            raise ExecutionPolicyError(
                "execution policy is unavailable",
                code="execution_policy_unavailable",
            )
        steps = _plan_steps(plan)
        output_type = _plan_output_type(plan)
        allowed_tools = set(normalized.get("allowed_tools") or [])
        if not output_type:
            raise ExecutionPolicyError(
                "TaskPlan output.type is required by the execution policy",
                code="execution_policy_result_type_missing",
            )
        if output_type not in set(normalized.get("allowed_result_profiles") or []):
            raise ExecutionPolicyError(
                "TaskPlan result type is not allowed by the execution policy",
                code="execution_policy_result_type_not_allowed",
            )
        if len(steps) > int(normalized["max_actions"]):
            raise ExecutionPolicyError(
                "TaskPlan exceeds the execution policy action limit",
                code="execution_policy_action_limit",
            )
        known = set(self._known_tools)
        for step in steps:
            tool = _text(getattr(step, "tool", ""))
            if not tool:
                raise ExecutionPolicyError(
                    "TaskPlan step tool is required",
                    code="execution_policy_tool_missing",
                )
            if known and tool not in known:
                raise ExecutionPolicyError(
                    "TaskPlan selected an unregistered tool",
                    code="execution_policy_tool_unknown",
                )
            if tool not in allowed_tools:
                raise ExecutionPolicyError(
                    "TaskPlan selected a tool outside the execution policy",
                    code="execution_policy_tool_not_allowed",
                )
        mode = normalized["mode"]
        if mode == "direct_tool":
            if len(steps) > 1 or any(
                list(getattr(step, "depends_on", ()) or ()) for step in steps
            ):
                raise ExecutionPolicyError(
                    "direct_tool policy accepts at most one independent tool",
                    code="execution_policy_direct_tool_shape",
                )
            if not steps and output_type != "direct_answer":
                raise ExecutionPolicyError(
                    "direct_tool policy requires one tool or direct_answer",
                    code="execution_policy_direct_tool_missing_action",
                )
        if mode == "domain_workflow" and normalized.get("source") not in {
            "explicit_workflow",
            "domain_catalog",
        }:
            # ``source=domain_catalog`` represents an automatic, uniquely
            # matched Domain policy and is intentionally accepted without a
            # transport workflow object.
            raise ExecutionPolicyError(
                "Domain workflow policy has no stable identity",
                code="execution_policy_workflow_identity_missing",
            )
        return normalized

    def resolve_and_validate(
        self,
        plan: Any,
        *,
        workflow: Mapping[str, Any] | None = None,
        domain_policy: Mapping[str, Any] | None = None,
        requested_mode: str | None = None,
        requires_confirmation: bool = False,
        open_react: bool = False,
    ) -> dict[str, Any]:
        """Resolve then validate a plan in one non-mutating operation."""

        policy = self.resolve(
            plan,
            workflow=workflow,
            domain_policy=domain_policy,
            requested_mode=requested_mode,
            requires_confirmation=requires_confirmation,
            open_react=open_react,
        )
        return self.validate_plan(plan, policy)

    def _mode_for_plan(
        self,
        steps: list[Any],
        *,
        has_workflow: bool,
        domain_available: bool,
    ) -> str:
        if has_workflow or domain_available:
            return "domain_workflow"
        if len(steps) <= 1 and not any(
            list(getattr(step, "depends_on", ()) or ()) for step in steps
        ):
            return "direct_tool"
        return "generated_dag"


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


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or value is None:
        return []
    try:
        values = iter(value)
    except TypeError:
        return []
    result: list[str] = []
    for item in values:
        text = _text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= _MAX_ITEMS:
            break
    return result


def _unique_strings(values: Iterable[Any]) -> list[str]:
    return _iter_strings(values)


def _first_strings(*values: Any) -> list[str]:
    for value in values:
        result = _iter_strings(value)
        if result:
            return result
    return []


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value >= 1:
            return min(value, 128)
    return None


def _bounded_constructor_int(value: Any, *, minimum: int, maximum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExecutionPolicyError(name + " must be an integer")
    if not minimum <= value <= maximum:
        raise ExecutionPolicyError(
            "{} must be between {} and {}".format(name, minimum, maximum)
        )
    return value


def _normalized_mode(value: Any) -> str | None:
    if value is None:
        return None
    text = _text(value)
    return text if text in EXECUTION_POLICY_MODES else None


def _bool_value(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _plan_steps(plan: Any) -> list[Any]:
    value = getattr(plan, "steps", None)
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(plan, Mapping) and isinstance(plan.get("steps"), list):
        return list(plan["steps"])
    return []


def _plan_output_type(plan: Any) -> str:
    output = getattr(plan, "output", None)
    if not isinstance(output, Mapping) and isinstance(plan, Mapping):
        output = plan.get("output")
    return _text(output.get("type")) if isinstance(output, Mapping) else ""


def _has_workflow_identity(value: Mapping[str, Any]) -> bool:
    return bool(value.get("template_id") or value.get("components"))


def _domain_policy_available(value: Mapping[str, Any]) -> bool:
    if not value or value.get("available") is False:
        return False
    return bool(
        value.get("policy_id")
        or value.get("workflow_template_id")
        or value.get("allowed_tools")
        or value.get("result_types")
    )


__all__ = [
    "DEFAULT_REACT_MAX_ACTIONS",
    "DEFAULT_REACT_MAX_TURNS",
    "EXECUTION_POLICY_MODES",
    "EXECUTION_POLICY_SCHEMA_VERSION",
    "EXECUTION_POLICY_SCHEMA",
    "EXECUTION_POLICY_STATES",
    "ExecutionPolicyError",
    "ExecutionPolicyResolver",
    "build_execution_policy",
    "execution_policy_schema",
    "normalize_execution_policy",
    "validate_execution_policy",
]
