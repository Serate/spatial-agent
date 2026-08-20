import json
from pathlib import Path
from typing import Dict, List, Optional

from agent.execution_contract import build_execution_record


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
        execution_record = build_execution_record(
            {**payload, "artifact_ref": path.as_posix()}, kind="run"
        )
        artifact = {
            "run_id": run_id,
            "status": payload.get("status"),
            "request": payload.get("request"),
            "resolved_request": payload.get("resolved_request"),
            "request_facts": payload.get("request_facts"),
            "session_id": payload.get("session_id"),
            "domain_id": payload.get("domain_id", "gis"),
            "runtime_context": payload.get("runtime_context"),
            "result_type": payload.get("result_type"),
            "planner_metrics": payload.get("planner_metrics"),
            "context_evidence": payload.get("context_evidence"),
            "plan_evidence": payload.get("plan_evidence"),
            "plan": _plan_summary(payload.get("plan")),
            "steps": [_step_summary(step) for step in payload.get("steps", [])],
            "provenance": payload.get("provenance"),
            "answer": payload.get("answer"),
            "trace_summary": payload.get("trace_summary", []),
            "error": payload.get("error"),
            "error_category": payload.get("error_category"),
            "error_code": payload.get("error_code"),
            "failure": payload.get("failure"),
            "clarification": payload.get("clarification"),
            "result": payload.get("result"),
            "degradation": _degradation_summary(payload),
            "retry_count": payload.get("retry_count", 0),
            "replan_events": payload.get("replan_events") or [],
            "geojson_ref": payload.get("geojson_ref"),
            "artifact_ref": path.as_posix(),
            "execution_record": execution_record,
        }
        path.write_text(json.dumps(artifact, ensure_ascii=True, indent=2), encoding="utf-8")
        return path.as_posix()

    def write_action(self, payload: Dict) -> str:
        """Persist one Domain Action execution for replay and recovery."""
        execution_id = payload.get("action_execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError("action payload must include action_execution_id")
        if len(execution_id) > 128 or Path(execution_id).name != execution_id:
            raise ValueError("action_execution_id must be a safe file name")
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / ("action-" + execution_id + ".json")
        execution_record = build_execution_record(
            {**payload, "artifact_ref": path.as_posix()}, kind="action"
        )
        artifact = {
            "artifact_schema_version": "spatial-agent.action-artifact.v1",
            "action_execution_id": execution_id,
            "action_id": payload.get("action_id"),
            "domain_id": payload.get("domain_id"),
            "runtime_context": payload.get("runtime_context"),
            "idempotency_key": payload.get("idempotency_key"),
            "input_fingerprint": payload.get("input_fingerprint"),
            "status": payload.get("status"),
            "action_execution": payload.get("action_execution"),
            "action_result": payload.get("action_result"),
            "result": payload.get("result"),
            "trace_summary": payload.get("trace_summary", []),
            "error": payload.get("error"),
            "error_code": payload.get("error_code"),
            "action_error_code": payload.get("action_error_code"),
            "artifact_ref": path.as_posix(),
            "execution_record": execution_record,
        }
        path.write_text(json.dumps(artifact, ensure_ascii=True, indent=2), encoding="utf-8")
        return path.as_posix()

    def find_action_by_idempotency_key(
        self, key: str, domain_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Find the newest bounded action record for an explicit idempotency key."""
        if not isinstance(key, str) or not key or len(key) > 128 or Path(key).name != key:
            return None
        if not self._root.exists():
            return None
        paths = sorted(
            self._root.glob("action-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in paths[:10000]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (
                payload.get("artifact_schema_version") == "spatial-agent.action-artifact.v1"
                and payload.get("idempotency_key") == key
                and (
                    not domain_id
                    or payload.get("domain_id", "gis") == domain_id
                )
            ):
                payload.setdefault("artifact_ref", path.as_posix())
                return payload
        return None

    def read_run(self, run_id: str, domain_id: Optional[str] = None) -> Optional[Dict]:
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
        if domain_id and payload.get("domain_id", "gis") != domain_id:
            return None
        return payload

    def read_action(
        self, execution_id: str, domain_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Read a persisted Domain Action without re-executing it."""
        if not isinstance(execution_id, str) or not execution_id:
            return None
        if len(execution_id) > 128 or Path(execution_id).name != execution_id:
            return None
        path = self._root / ("action-" + execution_id + ".json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        payload.setdefault("action_execution_id", execution_id)
        if domain_id and payload.get("domain_id", "gis") != domain_id:
            return None
        return payload

    def list_actions(
        self, limit: int = 20, domain_id: Optional[str] = None
    ) -> List[Dict]:
        """List bounded action evidence without exposing action payloads."""
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self._root.exists():
            return []
        records = []
        paths = sorted(
            self._root.glob("action-*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("artifact_schema_version") != "spatial-agent.action-artifact.v1":
                continue
            if domain_id and payload.get("domain_id", "gis") != domain_id:
                continue
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            records.append({
                "action_execution_id": payload.get("action_execution_id"),
                "action_id": payload.get("action_id"),
                "domain_id": payload.get("domain_id"),
                "status": payload.get("status"),
                "result_type": result.get("type"),
                "action_error_code": payload.get("action_error_code"),
                "action_execution": payload.get("action_execution"),
                "artifact_ref": path.as_posix(),
                "execution_record": payload.get("execution_record")
                or build_execution_record(payload, kind="action"),
                "modified_at": path.stat().st_mtime,
            })
            if len(records) >= limit:
                break
        return records

    def list_runs(self, limit: int = 20, domain_id: Optional[str] = None) -> List[Dict]:
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
            if payload.get("artifact_schema_version") == "spatial-agent.action-artifact.v1":
                continue
            if domain_id and payload.get("domain_id", "gis") != domain_id:
                continue
            records.append({
                "run_id": payload.get("run_id"),
                "domain_id": payload.get("domain_id", "gis"),
                "status": payload.get("status"),
                "request": payload.get("request"),
                "answer": payload.get("answer"),
                "error": payload.get("error"),
                "artifact_ref": path.as_posix(),
                "execution_record": payload.get("execution_record")
                or build_execution_record(payload, kind="run"),
                "modified_at": path.stat().st_mtime,
            })
            if len(records) >= limit:
                break
        return records

    def metrics(self, domain_id: Optional[str] = None) -> Dict:
        records = self.list_runs(limit=10000, domain_id=domain_id)
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

    def action_metrics(self, domain_id: Optional[str] = None) -> Dict:
        """Return bounded action artifact counters without loading raw results."""
        count = 0
        status_counts = {}
        error_counts = {}
        durations = []
        if self._root.exists():
            paths = sorted(
                self._root.glob("action-*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )[:10000]
            for path in paths:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if payload.get("artifact_schema_version") != "spatial-agent.action-artifact.v1":
                    continue
                if domain_id and payload.get("domain_id", "gis") != domain_id:
                    continue
                count += 1
                status = str(payload.get("status") or "UNKNOWN")[:32]
                status_counts[status] = status_counts.get(status, 0) + 1
                code = payload.get("action_error_code")
                if code:
                    code = str(code)[:96]
                    error_counts[code] = error_counts.get(code, 0) + 1
                duration = (payload.get("action_execution") or {}).get("duration_ms")
                if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                    durations.append(float(duration))
        return {
            "count": count,
            "status_counts": status_counts,
            "error_counts": error_counts,
            "duration_ms": _duration_summary(durations),
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
        "error_category": step.get("error_category"),
        "error_code": step.get("error_code"),
        "retryable": step.get("retryable"),
        "governance": step.get("governance"),
        "result": result_summary,
        "error": step.get("error"),
    }


def _degradation_summary(payload):
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("degradation"), dict):
        return result["degradation"]
    degradation = payload.get("degradation")
    if isinstance(degradation, dict):
        return degradation
    return None


def _duration_summary(values):
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(sum(values) / len(values), 3),
    }
