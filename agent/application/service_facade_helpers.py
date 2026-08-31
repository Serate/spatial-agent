"""Bounded pure projection helpers for AgentService.

Split out of ``service_facade`` so small, self-contained projection functions
live behind a stable seam.  Re-exported by ``service_facade`` for compatibility.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _approval_run_projection(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        status = str(value.get("status") or "")[:32]
        receipt = value.get("action_receipt")
        return {
            "run_id": str(value.get("run_id") or "")[:160],
            "status": status,
            "action_receipt_state": (
                str(receipt.get("state") or "")[:48]
                if isinstance(receipt, Mapping)
                else None
            ),
        }
    status = getattr(value, "status", "")
    status = getattr(status, "value", status)
    receipt = getattr(value, "action_receipt", None)
    return {
        "run_id": str(getattr(value, "run_id", ""))[:160],
        "status": str(status)[:32],
        "action_receipt_state": (
            str(receipt.get("state") or "")[:48]
            if isinstance(receipt, dict)
            else None
        ),
    }
