"""Controlled, domain-neutral ReAct loop.

The loop owns only decision sequencing and safety budgets.  Tool effects are
injected by the Runtime bridge, which keeps ToolRegistry, Domain preflight,
retry and result contracts as the only execution path.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from ..errors import RunCancelled, RunTimedOut
from .contracts import (
    ReactDecisionError,
    build_react_evidence,
    normalize_react_decision,
    project_react_decision,
)


@dataclass(frozen=True)
class ReactToolOutcome:
    """Safe adapter return shape for one completed tool action.

    ``result`` is kept in process for the Runtime to persist through StepRun,
    but the loop only forwards the bounded summary and reference to the next
    model decision.
    """

    result: Mapping[str, Any]
    result_ref: Optional[str] = None
    output_type: Optional[str] = None
    summary: Optional[str] = None
    citation_count: int = 0


@dataclass(frozen=True)
class ReactLoopOutcome:
    """Bounded outcome of one ReAct run."""

    state: str
    turn_count: int
    action_count: int
    evidence: tuple[dict[str, Any], ...]
    history: tuple[dict[str, Any], ...]
    final_decision: Optional[dict[str, Any]] = None
    final_message: Optional[str] = None
    output_type: Optional[str] = None
    reason_code: Optional[str] = None
    error_category: Optional[str] = None
    error_code: Optional[str] = None
    retryable: Optional[bool] = None
    proposal_receipt: Optional[dict[str, Any]] = None


class ReactLoop:
    """Run bounded, one-action-at-a-time ReAct decisions."""

    def __init__(
        self,
        decision_provider: Any,
        *,
        allowed_tools: Any = (),
        tool_catalog: Optional[Mapping[str, Any]] = None,
        max_turns: int = 8,
        max_actions: int = 12,
        network_enabled: bool = True,
        tool_proposals_enabled: bool = True,
        control_check: Optional[Callable[[], None]] = None,
        on_event: Optional[Callable[[str, Mapping[str, Any]], None]] = None,
    ) -> None:
        self._decision_provider = decision_provider
        self._allowed_tools = tuple(str(item) for item in (allowed_tools or ()) if str(item))
        self._tool_catalog = tool_catalog
        self._max_turns = _bounded_int(max_turns, 1, 32)
        self._max_actions = _bounded_int(max_actions, 1, 128)
        if not isinstance(network_enabled, bool):
            raise ValueError("network_enabled must be boolean")
        if not isinstance(tool_proposals_enabled, bool):
            raise ValueError("tool_proposals_enabled must be boolean")
        self._network_enabled = network_enabled
        self._tool_proposals_enabled = tool_proposals_enabled
        self._control_check = control_check
        self._on_event = on_event

    def run(
        self,
        request: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
        initial_decision: Any = None,
        validate_action: Optional[Callable[[Mapping[str, Any], int, str], Any]] = None,
        execute_tool: Optional[Callable[[Mapping[str, Any], int, str], Any]] = None,
        execute_search: Optional[Callable[[Mapping[str, Any], int, str], Any]] = None,
        validate_proposal: Optional[Callable[[Mapping[str, Any], int, str], Any]] = None,
    ) -> ReactLoopOutcome:
        """Run until finish, clarification, rejection or a bounded stop.

        ``initial_decision`` is used by the Runtime because the first model
        call happens in its explicit plan stage.  Subsequent decisions receive
        only ``history`` entries built by this loop.
        """

        history: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        action_count = 0
        initial = initial_decision

        for turn_index in range(1, self._max_turns + 1):
            self._check_control()
            action_id = "react-{}".format(turn_index)
            self._emit(
                "react_turn_started",
                {
                    "turn_index": turn_index,
                    "action_id": action_id,
                    "action_count": action_count,
                    "max_actions": self._max_actions,
                    "max_turns": self._max_turns,
                },
            )
            try:
                raw = initial if turn_index == 1 and initial is not None else invoke_react_decider(
                    self._decision_provider,
                    request,
                    context=context,
                    history=history,
                    allowed_tools=self._allowed_tools,
                    tool_catalog=self._tool_catalog,
                    network_enabled=self._network_enabled,
                    tool_proposals_enabled=self._tool_proposals_enabled,
                )
                decision = normalize_react_decision(
                    raw,
                    allowed_tools=self._allowed_tools,
                    network_enabled=self._network_enabled,
                    tool_proposals_enabled=self._tool_proposals_enabled,
                )
            except ReactDecisionError:
                item = build_react_evidence(
                    {"action": "reject"},
                    turn_index=turn_index,
                    validation_state="blocked",
                    policy_mode="react",
                    source="runtime",
                    action_id=action_id,
                    reason_code="react_decision_invalid",
                )
                evidence.append(item)
                self._emit("react_action_blocked", item)
                return self._outcome(
                    "blocked",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    reason_code="react_decision_invalid",
                )
            finally:
                if turn_index == 1:
                    initial = None

            signature = _action_signature(decision)
            if signature in seen_signatures:
                item = build_react_evidence(
                    decision,
                    turn_index=turn_index,
                    validation_state="blocked",
                    policy_mode="react",
                    source="runtime",
                    action_id=action_id,
                    reason_code="react_repeated_action",
                )
                evidence.append(item)
                self._emit("react_action_blocked", item)
                return self._outcome(
                    "blocked",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    final_decision=decision,
                    reason_code="react_repeated_action",
                )
            seen_signatures.add(signature)
            action = decision["action"]
            if action in {"call_tool", "search", "propose_tool"}:
                if action_count >= self._max_actions:
                    item = build_react_evidence(
                        decision,
                        turn_index=turn_index,
                        validation_state="blocked",
                        policy_mode="react",
                        source="runtime",
                        action_id=action_id,
                        reason_code="react_action_budget_exceeded",
                    )
                    evidence.append(item)
                    self._emit("react_action_blocked", item)
                    return self._outcome(
                        "blocked",
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        final_decision=decision,
                        reason_code="react_action_budget_exceeded",
                    )
                action_count += 1

            if callable(validate_action):
                try:
                    validate_action(decision, turn_index, action_id)
                except (RunCancelled, RunTimedOut):
                    raise
                except Exception as exc:
                    return self._blocked(
                        decision,
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        action_id=action_id,
                        reason_code=str(
                            getattr(exc, "code", None) or "react_action_validation_failed"
                        )[:96],
                        error_category=getattr(exc, "category", None),
                        error_code=getattr(exc, "code", None),
                        retryable=getattr(exc, "retryable", None),
                    )

            proposal_receipt = None
            if action == "propose_tool" and callable(validate_proposal):
                try:
                    proposal_receipt = validate_proposal(decision, turn_index, action_id)
                except (RunCancelled, RunTimedOut):
                    raise
                except Exception as exc:
                    return self._blocked(
                        decision,
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        action_id=action_id,
                        reason_code=str(
                            getattr(exc, "code", None) or "react_tool_proposal_validation_failed"
                        )[:96],
                        error_category=getattr(exc, "category", None),
                        error_code=getattr(exc, "code", None),
                        retryable=getattr(exc, "retryable", None),
                    )
                if not isinstance(proposal_receipt, Mapping):
                    return self._blocked(
                        decision,
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        action_id=action_id,
                        reason_code="react_tool_proposal_invalid_receipt",
                    )
                if proposal_receipt.get("status") != "validated":
                    return self._blocked(
                        decision,
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        action_id=action_id,
                        reason_code=str(
                            proposal_receipt.get("reason_code") or "react_tool_proposal_rejected"
                        )[:96],
                        proposal_receipt=proposal_receipt,
                    )

            accepted = build_react_evidence(
                decision,
                turn_index=turn_index,
                validation_state="accepted",
                policy_mode="react",
                source="model",
                action_id=action_id,
                reason_code="react_action_accepted",
            )
            self._emit("react_action_accepted", accepted)

            if action in {"call_tool", "search"}:
                executor = execute_tool if action == "call_tool" else execute_search
                if executor is None:
                    return self._blocked(
                        decision,
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        action_id=action_id,
                        reason_code=(
                            "react_tool_executor_missing"
                            if action == "call_tool"
                            else "react_search_executor_missing"
                        ),
                    )
                try:
                    raw_outcome = executor(decision, turn_index, action_id)
                    outcome = _coerce_tool_outcome(raw_outcome, action_id)
                except (RunCancelled, RunTimedOut):
                    raise
                except Exception as exc:
                    fallback_code = (
                        "react_tool_execution_failed"
                        if action == "call_tool"
                        else "react_search_execution_failed"
                    )
                    reason_code = str(getattr(exc, "code", None) or fallback_code)[:96]
                    item = build_react_evidence(
                        decision,
                        turn_index=turn_index,
                        validation_state="blocked",
                        policy_mode="react",
                        source="runtime",
                        action_id=action_id,
                        reason_code=reason_code,
                    )
                    evidence.append(item)
                    self._emit("react_action_blocked", item)
                    return self._outcome(
                        "blocked",
                        turn_index,
                        action_count,
                        evidence,
                        history,
                        final_decision=decision,
                        reason_code=reason_code,
                        error_category=getattr(exc, "category", None),
                        error_code=getattr(exc, "code", None),
                        retryable=getattr(exc, "retryable", None),
                    )
                result_ref = _bounded_text(outcome.result_ref or action_id, 160)
                summary = _bounded_text(
                    outcome.summary or summarize_tool_result(outcome.result),
                    512,
                )
                history.append(
                    {
                        "turn_index": turn_index,
                        "action_id": action_id,
                        "action": action,
                        "tool_name": decision.get("tool_name") if action == "call_tool" else None,
                        "query": decision.get("query") if action == "search" else None,
                        "result_ref": result_ref,
                        "output_type": _bounded_text(outcome.output_type or decision.get("output_type"), 96) or None,
                        "summary": summary,
                    }
                )
                item = build_react_evidence(
                    decision,
                    turn_index=turn_index,
                    validation_state="completed",
                    policy_mode="react",
                    source="model",
                    action_id=action_id,
                    reason_code=(
                        "react_tool_completed"
                        if action == "call_tool"
                        else "react_search_completed"
                    ),
                    result_ref=result_ref,
                    citation_count=outcome.citation_count,
                )
                evidence.append(item)
                self._emit("react_action_completed", item)
                continue

            if action == "propose_tool" and callable(validate_proposal):
                item = build_react_evidence(
                    decision,
                    turn_index=turn_index,
                    validation_state="completed",
                    policy_mode="react",
                    source="model",
                    action_id=action_id,
                    reason_code="react_tool_proposal_validated",
                    proposal_receipt=proposal_receipt,
                )
                evidence.append(item)
                self._emit("react_action_completed", item)
                self._emit("react_waiting_for_approval", item)
                return self._outcome(
                    "awaiting_approval",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    final_decision=decision,
                    reason_code="react_tool_proposal_awaiting_approval",
                    proposal_receipt=dict(proposal_receipt),
                )

            if action == "propose_tool":
                item = build_react_evidence(
                    decision,
                    turn_index=turn_index,
                    validation_state="blocked",
                    policy_mode="react",
                    source="runtime",
                    action_id=action_id,
                    reason_code="react_tool_proposal_unavailable",
                )
                evidence.append(item)
                self._emit("react_action_blocked", item)
                return self._outcome(
                    "blocked",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    final_decision=decision,
                    reason_code="react_tool_proposal_unavailable",
                )

            item = build_react_evidence(
                decision,
                turn_index=turn_index,
                validation_state="completed",
                policy_mode="react",
                source="model",
                action_id=action_id,
                reason_code="react_{}".format(action),
            )
            evidence.append(item)
            self._emit("react_action_completed", item)
            self._emit("react_finished", item)
            if action == "finish":
                return self._outcome(
                    "finished",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    final_decision=decision,
                    final_message=decision.get("message") or decision.get("summary"),
                    output_type=decision.get("output_type"),
                    reason_code="react_finished",
                )
            if action == "ask_clarification":
                return self._outcome(
                    "clarification",
                    turn_index,
                    action_count,
                    evidence,
                    history,
                    final_decision=decision,
                    final_message=decision.get("message"),
                    reason_code="react_clarification_requested",
                )
            return self._outcome(
                "rejected",
                turn_index,
                action_count,
                evidence,
                history,
                final_decision=decision,
                final_message=decision.get("message"),
                reason_code="react_request_rejected",
            )

        return self._outcome(
            "blocked",
            self._max_turns,
            action_count,
            evidence,
            history,
            reason_code="react_turn_budget_exceeded",
        )

    def _blocked(
        self,
        decision: Mapping[str, Any],
        turn_index: int,
        action_count: int,
        evidence: list[dict[str, Any]],
        history: list[dict[str, Any]],
        *,
        action_id: str,
        reason_code: str,
        error_category: Optional[str] = None,
        error_code: Optional[str] = None,
        retryable: Optional[bool] = None,
        proposal_receipt: Optional[Mapping[str, Any]] = None,
    ) -> ReactLoopOutcome:
        item = build_react_evidence(
            decision,
            turn_index=turn_index,
            validation_state="blocked",
            policy_mode="react",
            source="runtime",
            action_id=action_id,
            reason_code=reason_code,
            proposal_receipt=proposal_receipt,
        )
        evidence.append(item)
        self._emit("react_action_blocked", item)
        return self._outcome(
            "blocked",
            turn_index,
            action_count,
            evidence,
            history,
            final_decision=dict(decision),
            reason_code=reason_code,
            error_category=error_category,
            error_code=error_code,
            retryable=retryable,
            proposal_receipt=dict(proposal_receipt) if isinstance(proposal_receipt, Mapping) else None,
        )

    def _outcome(self, state: str, turn_count: int, action_count: int, evidence, history, **kwargs):
        return ReactLoopOutcome(
            state=state,
            turn_count=min(max(0, int(turn_count)), self._max_turns),
            action_count=min(max(0, int(action_count)), self._max_actions),
            evidence=tuple(dict(item) for item in evidence[-32:]),
            history=tuple(dict(item) for item in history[-32:]),
            **kwargs,
        )

    def _check_control(self) -> None:
        if callable(self._control_check):
            self._control_check()

    def _emit(self, kind: str, payload: Mapping[str, Any]) -> None:
        if not callable(self._on_event):
            return
        try:
            self._on_event(str(kind), dict(payload))
        except Exception:
            # Event delivery is observational and must not alter execution.
            return


def invoke_react_decider(
    provider: Any,
    request: str,
    *,
    context: Optional[Mapping[str, Any]] = None,
    history: Any = (),
    allowed_tools: Any = (),
    tool_catalog: Optional[Mapping[str, Any]] = None,
    network_enabled: bool = True,
    tool_proposals_enabled: bool = True,
) -> Any:
    """Invoke a decider with only the kwargs its adapter declares."""

    method = getattr(provider, "decide", None)
    if not callable(method) and callable(provider):
        method = provider
    if not callable(method):
        raise ReactDecisionError("react decision provider is unavailable")
    values = {
        "context": context,
        "history": list(history) if isinstance(history, (list, tuple)) else [],
        "allowed_tools": tuple(allowed_tools or ()),
        "tool_catalog": tool_catalog,
        "network_enabled": network_enabled,
        "tool_proposals_enabled": tool_proposals_enabled,
    }
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()
    )
    kwargs = values if accepts_kwargs else {
        name: value for name, value in values.items() if name in parameters
    }
    return method(request, **kwargs)


def summarize_tool_result(result: Any) -> str:
    """Return a small model-facing summary without forwarding raw result data."""

    if not isinstance(result, Mapping):
        return "工具返回了不可读取的结果。"
    parts: list[str] = []
    status = result.get("status")
    result_type = result.get("result_type") or result.get("type")
    if status is not None:
        parts.append("状态=" + _bounded_text(status, 32))
    if result_type is not None:
        parts.append("结果类型=" + _bounded_text(result_type, 96))
    for key in ("count", "feature_count", "row_count", "sample_count", "file_count"):
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parts.append("{}={}".format(key, value))
    for key in ("warning", "reason", "summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(_bounded_text(value, 180))
            break
    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        parts.append("warning_count={}".format(min(len(warnings), 16)))
    return "；".join(parts)[:512] or "工具已返回结构化结果。"


def _coerce_tool_outcome(value: Any, action_id: str) -> ReactToolOutcome:
    if isinstance(value, ReactToolOutcome):
        result = value.result
        if not isinstance(result, Mapping):
            raise ReactDecisionError("react tool result must be an object")
        return value
    if isinstance(value, Mapping):
        return ReactToolOutcome(result=value, result_ref=action_id)
    raise ReactDecisionError("react tool outcome is invalid")


def _action_signature(decision: Mapping[str, Any]) -> str:
    action = decision.get("action")
    if action == "call_tool":
        body = {
            "action": action,
            "tool_name": decision.get("tool_name"),
            "arguments": decision.get("arguments") or {},
            "depends_on": decision.get("depends_on") or [],
        }
    elif action == "search":
        body = {
            "action": action,
            "query": decision.get("query"),
            "domains": decision.get("domains"),
            "max_results": decision.get("max_results"),
        }
    elif action == "propose_tool":
        proposal = decision.get("proposal") or {}
        body = {"action": action, "name": proposal.get("name")}
    else:
        body = {"action": action, "message": decision.get("message")}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return minimum
    return max(minimum, min(value, maximum))


__all__ = [
    "ReactLoop",
    "ReactLoopOutcome",
    "ReactToolOutcome",
    "invoke_react_decider",
    "summarize_tool_result",
]
