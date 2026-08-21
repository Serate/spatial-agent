"""Stable identity for comparing a planned TaskPlan with a later execution."""

import hashlib
import json
from typing import Any, Mapping, Optional

from .models import TaskPlan


PLAN_IDENTITY_VERSION = "spatial-agent.plan-identity.v1"


def build_plan_identity(
    plan: TaskPlan,
    *,
    request: str,
    resolved_request: str,
    workflow: Optional[Mapping[str, Any]],
    planner_kind: str,
) -> dict[str, str]:
    """Return a deterministic, credential-free identity for a planned task."""

    canonical = {
        "version": PLAN_IDENTITY_VERSION,
        "request": str(request or ""),
        "resolved_request": str(resolved_request or ""),
        "workflow": dict(workflow) if isinstance(workflow, Mapping) else None,
        "planner_kind": str(planner_kind or ""),
        "plan": {
            "goal": plan.goal,
            "steps": [
                {
                    "id": step.id,
                    "tool": step.tool,
                    "args": dict(step.args),
                    "depends_on": list(step.depends_on),
                }
                for step in plan.steps
            ],
            "output": dict(plan.output),
            "assumptions": list(plan.assumptions),
        },
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": PLAN_IDENTITY_VERSION,
        "fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def normalize_plan_identity(value: Any) -> dict[str, str] | None:
    """Keep a stored plan identity bounded at async and recovery seams."""

    if not isinstance(value, Mapping):
        return None
    version = value.get("version")
    fingerprint = value.get("fingerprint")
    if not isinstance(version, str) or version != PLAN_IDENTITY_VERSION:
        return None
    if not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:"):
        return None
    digest = fingerprint[7:]
    # Production identities are full SHA-256 values.  Short deterministic
    # replay identifiers are also valid at this compatibility seam so old
    # fixtures and recorded planner evidence can still be compared.
    if not 1 <= len(digest) <= 120 or any(
        not (char.isalnum() or char in "_-") for char in digest
    ):
        return None
    return {"version": PLAN_IDENTITY_VERSION, "fingerprint": fingerprint}


__all__ = [
    "PLAN_IDENTITY_VERSION",
    "build_plan_identity",
    "normalize_plan_identity",
]
