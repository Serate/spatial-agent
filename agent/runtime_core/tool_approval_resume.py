"""Approval-bound continuation for ReAct tool proposals.

This seam translates the durable approval state into one of two safe runtime
actions: resume the exact waiting run after a valid publication, or close it
as rejected/expired.  It never loads proposal source code or asks the model to
re-plan the original request before the approval binding is checked.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..errors import ToolError
from ..models import AgentRunResult, RunStatus


class RuntimeToolApprovalResume:
    """Own the run-side half of the tool-approval lifecycle."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def apply(
        self,
        approval: Mapping[str, Any],
        *,
        timeout_seconds: Optional[float] = None,
    ) -> AgentRunResult | None:
        runtime = self._runtime
        run_id = str(approval.get("run_id") or "").strip()
        if not run_id:
            raise ToolError(
                "approved tool has no waiting run",
                category="approval",
                code="approval_run_missing",
                retryable=False,
            )
        result = runtime._state_store.get(run_id)
        if result is None:
            raise ToolError(
                "approval waiting run was not found",
                category="approval",
                code="approval_run_not_found",
                retryable=False,
            )
        self._validate_waiting_result(result, approval)
        status = str(approval.get("status") or "")
        if status == "approved":
            self._require_binding(approval)
            return runtime._run_lifecycle.resume_tool_approval(
                result,
                approval=approval,
                timeout_seconds=timeout_seconds,
            )
        if status in {"rejected", "revoked", "expired", "invalid"}:
            return self._close_without_execution(result, approval)
        raise ToolError(
            "tool approval is not actionable: " + status,
            category="approval",
            code="approval_state_not_actionable",
            retryable=False,
        )

    def _validate_waiting_result(
        self, result: AgentRunResult, approval: Mapping[str, Any]
    ) -> None:
        if result.status != RunStatus.WAITING_FOR_DECISION:
            raise ToolError(
                "approval run is no longer waiting",
                category="approval",
                code="approval_run_not_waiting",
                retryable=False,
            )
        receipt = result.action_receipt if isinstance(result.action_receipt, Mapping) else {}
        stored = receipt.get("approval") if isinstance(receipt.get("approval"), Mapping) else {}
        if (
            str(stored.get("approval_id") or "") != str(approval.get("approval_id") or "")
            or str(stored.get("receipt_fingerprint") or "")
            != str(approval.get("receipt_fingerprint") or "")
        ):
            raise ToolError(
                "approval and waiting run fingerprints differ",
                category="approval",
                code="approval_fingerprint_mismatch",
                retryable=False,
            )

    def _require_binding(self, approval: Mapping[str, Any]) -> None:
        registry = getattr(self._runtime, "_registry", None)
        dynamic = getattr(registry, "dynamic_tools", None)
        bindings = dynamic() if callable(dynamic) else []
        expected_id = str(approval.get("approval_id") or "")
        expected_version = int(approval.get("version") or 0)
        expected_fingerprint = str(approval.get("receipt_fingerprint") or "")
        for item in bindings if isinstance(bindings, list) else []:
            if not isinstance(item, Mapping):
                continue
            if (
                str(item.get("approval_id") or "") == expected_id
                and int(item.get("approval_version") or 0) == expected_version
                and str(item.get("approval_fingerprint") or "") == expected_fingerprint
            ):
                resolver = getattr(self._runtime, "_execution_policy_resolver", None)
                refresh = getattr(resolver, "refresh_known_tools", None)
                if callable(refresh):
                    refresh(getattr(registry, "names", ()))
                return
        raise ToolError(
            "approved tool binding is unavailable",
            category="approval",
            code="approval_binding_missing",
            retryable=False,
        )

    def _close_without_execution(
        self, result: AgentRunResult, approval: Mapping[str, Any]
    ) -> AgentRunResult:
        runtime = self._runtime
        status = str(approval.get("status") or "invalid")
        result.status = RunStatus.REJECTED
        result.error_category = "approval"
        result.error_code = "tool_approval_" + status
        result.error = {
            "rejected": "用户拒绝了工具提案。",
            "revoked": "工具提案审批已撤销。",
            "expired": "工具提案审批已过期。",
            "invalid": "工具提案审批无效。",
        }.get(status, "工具提案未获批准。")
        result.answer = result.error
        result.action_receipt = {
            **(
                dict(result.action_receipt)
                if isinstance(result.action_receipt, Mapping)
                else {}
            ),
            "state": "closed_without_execution",
            "approval": dict(approval),
        }
        runtime._conversation_store.clear_pending(result.session_id or "default")
        runtime._state_store.save(result)
        runtime._emit_progress_event(
            result.run_id,
            phase="execute",
            kind="run_finished",
            status=RunStatus.REJECTED.value,
            message="工具提案未获批准，运行已安全结束",
            data={"reason_code": result.error_code},
            terminal=True,
        )
        runtime._emit_run_event(result)
        return result


__all__ = ["RuntimeToolApprovalResume"]
