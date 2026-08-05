import json
from pathlib import Path
from typing import Dict


class ArtifactStore:
    """Writes small run artifacts for demos, handoff, and downstream clients."""

    def __init__(self, root: str = "outputs/runs"):
        self._root = Path(root)

    def write_run(self, payload: Dict) -> str:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("payload must include run_id")
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / (run_id + ".json")
        artifact = {
            "run_id": run_id,
            "status": payload.get("status"),
            "request": payload.get("request"),
            "resolved_request": payload.get("resolved_request"),
            "plan": _plan_summary(payload.get("plan")),
            "steps": [_step_summary(step) for step in payload.get("steps", [])],
            "answer": payload.get("answer"),
            "trace_summary": payload.get("trace_summary", []),
            "error": payload.get("error"),
        }
        path.write_text(json.dumps(artifact, ensure_ascii=True, indent=2), encoding="utf-8")
        return path.as_posix()


def _plan_summary(plan):
    if not isinstance(plan, dict):
        return None
    return {
        "goal": plan.get("goal"),
        "output": plan.get("output", {}),
        "assumptions": plan.get("assumptions", []),
    }


def _step_summary(step):
    if not isinstance(step, dict):
        return {"status": "UNKNOWN"}
    result = step.get("result")
    result_summary = {}
    if isinstance(result, dict):
        for key in ("count", "result_ref", "crs", "sample_names", "file_count"):
            if key in result:
                result_summary[key] = result[key]
    return {
        "id": step.get("id"),
        "tool": step.get("tool"),
        "status": step.get("status"),
        "attempts": step.get("attempts", 0),
        "latency_ms": step.get("latency_ms"),
        "result": result_summary,
        "error": step.get("error"),
    }
