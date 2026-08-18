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
