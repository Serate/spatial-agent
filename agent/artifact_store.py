import json
from pathlib import Path
from typing import Dict, List, Optional


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
            "session_id": payload.get("session_id"),
            "result_type": payload.get("result_type"),
            "planner_metrics": payload.get("planner_metrics"),
            "context_evidence": payload.get("context_evidence"),
            "plan": _plan_summary(payload.get("plan")),
            "steps": [_step_summary(step) for step in payload.get("steps", [])],
            "provenance": payload.get("provenance"),
            "answer": payload.get("answer"),
            "trace_summary": payload.get("trace_summary", []),
            "error": payload.get("error"),
            "clarification": payload.get("clarification"),
            "retry_count": payload.get("retry_count", 0),
            "replan_events": payload.get("replan_events") or [],
            "geojson_ref": payload.get("geojson_ref"),
            "artifact_ref": path.as_posix(),
        }
        path.write_text(json.dumps(artifact, ensure_ascii=True, indent=2), encoding="utf-8")
        return path.as_posix()

    def read_run(self, run_id: str) -> Optional[Dict]:
        """Read a single persisted run artifact, or None when it is missing.

        Used by the service to serve a degraded run detail (answer, trace,
        provenance, context) from the durable artifact after the in-memory
        store has been lost, without re-invoking the model.
        """
        if not isinstance(run_id, str) or not run_id:
            return None
        path = self._root / (run_id + ".json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        payload.setdefault("run_id", run_id)
        return payload

    def list_runs(self, limit: int = 20) -> List[Dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self._root.exists():
            return []
        records = []
        for path in sorted(self._root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            records.append({
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "request": payload.get("request"),
                "answer": payload.get("answer"),
                "error": payload.get("error"),
                "artifact_ref": path.as_posix(),
                "modified_at": path.stat().st_mtime,
            })
            if len(records) >= limit:
                break
        return records

    def metrics(self) -> Dict:
        records = self.list_runs(limit=10000)
        status_counts = {}
        total_tokens = 0
        for record in records:
            status = record.get("status") or "UNKNOWN"
            status_counts[status] = status_counts.get(status, 0) + 1
            try:
                artifact = json.loads(Path(record["artifact_ref"]).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            usage = ((artifact.get("planner_metrics") or {}).get("usage") or {})
            total_tokens += int(usage.get("total_tokens") or 0)
        return {
            "run_count": len(records),
            "status_counts": status_counts,
            "total_tokens": total_tokens,
        }


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
        "depends_on": list(step.get("depends_on") or []),
        "attempts": step.get("attempts", 0),
        "latency_ms": step.get("latency_ms"),
        "result": result_summary,
        "error": step.get("error"),
    }
