import json
from pathlib import Path
from typing import Dict, List, Optional

from agent.execution_contract import build_execution_record
from agent.action_lifecycle import project_action_lifecycle
from agent.runtime_context import normalize_runtime_context
from agent.contract_versions import (
    ACTION_ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_MIGRATION_SCHEMA_VERSION,
    RUN_ARTIFACT_SCHEMA_VERSION,
)
from agent.service_async import normalize_async_result_evidence
from agent.nested_schema import NestedSchemaError, normalize_result_contract, unavailable_nested_view
from agent.evidence_registry import (
    EVIDENCE_REGISTRY_SCHEMA_VERSION,
    build_evidence_registry,
    normalize_evidence_registry,
    project_evidence_registry_completeness,
)
from agent.recovery_action import normalize_action_receipt


def _safe_run_id(run_id: object) -> str | None:
    """Return a filename-safe run id without relying on host path semantics."""
    if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
        return None
    normalized = run_id.replace("\\", "/")
    if normalized != run_id or "/" in normalized or run_id in {".", ".."}:
        return None
    if Path(run_id).name != run_id:
        return None
    return run_id


def _execution_timeline_from_payload(payload: Dict) -> object:
    value = payload.get("execution_timeline")
    if value is not None:
        return value
    nested = payload.get("result")
    return nested.get("execution_timeline") if isinstance(nested, dict) else None


def _evidence_registry_from_payload(payload: Dict) -> object:
    value = payload.get("evidence_registry")
    if value is not None:
        return value
    nested = payload.get("result")
    return nested.get("evidence_registry") if isinstance(nested, dict) else None


class ArtifactStore:
    """Writes small run artifacts for demos, handoff, and downstream clients."""

    def __init__(self, root: str = "outputs/runs", *, legacy_domain_id: str = "gis"):
        self._root = Path(root)
        normalized_domain = str(legacy_domain_id or "").strip()
        if not normalized_domain or len(normalized_domain) > 80:
            raise ValueError("legacy_domain_id must be a non-empty bounded value")
        self._legacy_domain_id = normalized_domain

    def _payload_domain(self, payload: Dict) -> str:
        value = payload.get("domain_id")
        normalized = str(value or "").strip()
        return normalized[:80] if normalized else self._legacy_domain_id

    def write_run(self, payload: Dict) -> str:
        run_id = payload.get("run_id")
        run_id = _safe_run_id(run_id)
        if run_id is None:
            raise ValueError("payload must include a safe run_id")
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / (run_id + ".json")
        execution_record = build_execution_record(
            {**payload, "artifact_ref": path.as_posix()}, kind="run"
        )
        artifact = {
            "artifact_schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
            "artifact_migration": payload.get("artifact_migration"),
            "run_id": run_id,
            "status": payload.get("status"),
            "request": payload.get("request"),
            "resolved_request": payload.get("resolved_request"),
            "request_facts": payload.get("request_facts"),
            "session_id": payload.get("session_id"),
            "domain_id": self._payload_domain(payload),
            "runtime_context": normalize_runtime_context(payload.get("runtime_context")),
            "spatial_context": payload.get("spatial_context"),
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
            "execution_timeline": _execution_timeline_from_payload(payload),
            "evidence_registry": _evidence_registry_from_payload(payload),
            "decision_evidence": payload.get("decision_evidence"),
            "decision_record": payload.get("_decision_record"),
            "interaction_receipt": payload.get("interaction_receipt"),
            "action_receipt": payload.get("action_receipt"),
            "lifecycle": project_action_lifecycle(payload),
            "geojson_ref": payload.get("geojson_ref"),
            "artifact_ref": path.as_posix(),
            "execution_record": execution_record,
        }
        # Async polling evidence is deliberately stored as a bounded
        # projection, never as the full observation/request.  The internal
        # marker lets artifact-only recovery distinguish an async run from a
        # normal synchronous artifact, including when the evidence field is
        # absent in a legacy or partially-written file.
        async_observation = payload.get("async_observability")
        async_requested = bool(
            payload.get("_async_requested")
            or payload.get("async_requested")
            or isinstance(async_observation, dict)
        )
        if async_requested:
            artifact["async_requested"] = True
            evidence = (
                async_observation.get("result_evidence")
                if isinstance(async_observation, dict)
                else None
            )
            if evidence is not None:
                artifact["async_result_evidence"] = normalize_async_result_evidence(
                    evidence,
                    status=payload.get("status"),
                    artifact_ref=path.as_posix(),
                )
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
            "artifact_schema_version": ACTION_ARTIFACT_SCHEMA_VERSION,
            "action_execution_id": execution_id,
            "action_id": payload.get("action_id"),
            "domain_id": self._payload_domain(payload),
            "runtime_context": normalize_runtime_context(payload.get("runtime_context")),
            "idempotency_key": payload.get("idempotency_key"),
            "input_fingerprint": payload.get("input_fingerprint"),
            "status": payload.get("status"),
            "action_execution": payload.get("action_execution"),
            "action_result": payload.get("action_result"),
            "lifecycle": project_action_lifecycle(payload),
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
                payload.get("artifact_schema_version") == ACTION_ARTIFACT_SCHEMA_VERSION
                and payload.get("idempotency_key") == key
                and (
                    not domain_id
                    or self._payload_domain(payload) == domain_id
                )
            ):
                payload.setdefault("artifact_ref", path.as_posix())
                return payload
        return None

    def migrate_run(
        self, run_id: str, domain_id: Optional[str] = None
    ) -> Optional[str]:
        """Migrate one compatible legacy run and rebuild its evidence index.

        Legacy artifacts are intentionally readable without mutation.  A
        caller that owns a persistence migration can opt into an explicit,
        bounded rewrite.  A current-but-incomplete Evidence Registry is
        rebuilt from the persisted result contract.  Future/unknown artifact
        or registry versions are never rewritten because the current process
        cannot prove their semantics.
        """
        safe_id = _safe_run_id(run_id)
        if safe_id is None:
            return None
        path = self._root / (safe_id + ".json")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        schema = raw.get("artifact_schema_version")
        if schema not in (None, RUN_ARTIFACT_SCHEMA_VERSION):
            return None
        payload = self.read_run(safe_id, domain_id=domain_id)
        if payload is None:
            return None
        raw_registry = _evidence_registry_from_payload(payload)
        rebuilt_evidence = False
        if isinstance(raw_registry, dict) and raw_registry.get("schema_version") == EVIDENCE_REGISTRY_SCHEMA_VERSION:
            completeness = project_evidence_registry_completeness(raw_registry)
            if not completeness.get("passed") and completeness.get("missing_entry_ids"):
                result = payload.get("result")
                if not isinstance(result, dict):
                    return None
                rebuilt_registry = build_evidence_registry(
                    {"result": result, "status": payload.get("status")}
                )
                rebuilt_completeness = project_evidence_registry_completeness(
                    rebuilt_registry
                )
                if not rebuilt_completeness.get("passed"):
                    return None
                payload["evidence_registry"] = rebuilt_registry
                payload["result"] = {**result, "evidence_registry": rebuilt_registry}
                rebuilt_evidence = True
        if schema == RUN_ARTIFACT_SCHEMA_VERSION and not rebuilt_evidence:
            return path.as_posix()
        payload["artifact_migration"] = {
            "schema_version": ARTIFACT_MIGRATION_SCHEMA_VERSION,
            "source_schema_version": "legacy-unversioned" if schema is None else schema,
            "target_schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
            "mode": "explicit_rewrite_with_evidence_rebuild" if rebuilt_evidence else "explicit_rewrite",
            "evidence_registry": {
                "rebuilt": rebuilt_evidence,
                "schema_version": EVIDENCE_REGISTRY_SCHEMA_VERSION if rebuilt_evidence else None,
            },
        }
        return self.write_run(payload)

    def read_run(self, run_id: str, domain_id: Optional[str] = None) -> Optional[Dict]:
        """Read a single persisted run artifact, or None when it is missing.

        Used by the service to serve a degraded run detail (answer, trace,
        provenance, context) from the durable artifact after the in-memory
        store has been lost, without re-invoking the model.
        """
        run_id = _safe_run_id(run_id)
        if run_id is None:
            return None
        path = self._root / (run_id + ".json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        schema = payload.get("artifact_schema_version")
        # Artifacts written before M147 had no run-artifact schema field and
        # remain readable. Unknown versions are not silently interpreted as
        # current data, which keeps future migrations explicit.
        if schema not in (None, RUN_ARTIFACT_SCHEMA_VERSION):
            return None
        payload.setdefault("run_id", run_id)
        if domain_id and self._payload_domain(payload) != domain_id:
            return None
        # Keep the durable artifact readable while preventing a future nested
        # result shape from crossing the recovery boundary.  The service can
        # turn this bounded marker into the normal unavailable view.
        nested_result = payload.get("result")
        if isinstance(nested_result, dict):
            try:
                payload["result"] = normalize_result_contract(nested_result)
            except NestedSchemaError as exc:
                payload["result"] = unavailable_nested_view(
                    result_type=payload.get("result_type") or nested_result.get("type"),
                    reason_code=exc.reason_code,
                )
                payload["nested_schema_warning"] = exc.reason_code
        nested_evidence = payload.get("async_result_evidence")
        if isinstance(nested_evidence, dict):
            payload["async_result_evidence"] = normalize_async_result_evidence(
                nested_evidence,
                status=payload.get("status"),
                artifact_ref=payload.get("artifact_ref"),
            )
        return payload

    def find_decision(
        self, decision_id: str, domain_id: Optional[str] = None
    ) -> Optional[Dict]:
        """Find a bounded decision embedded in a run artifact.

        This is intentionally a fallback for artifact-only recovery. Normal
        services use the DecisionStore, while this scan allows a restarted
        stateless viewer to recover a pending decision without trusting an
        external path or executing the run.
        """
        if not isinstance(decision_id, str) or not decision_id or len(decision_id) > 160:
            return None
        if not self._root.exists():
            return None
        paths = sorted(
            self._root.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in paths[:10000]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("artifact_schema_version") == ACTION_ARTIFACT_SCHEMA_VERSION:
                continue
            if domain_id and self._payload_domain(payload) != domain_id:
                continue
            record = payload.get("decision_record")
            evidence = payload.get("decision_evidence")
            candidate = record if isinstance(record, dict) else None
            if candidate is None and isinstance(evidence, dict):
                candidate = {
                    "schema_version": evidence.get("schema_version"),
                    "decision_id": evidence.get("decision_id"),
                    "subject": {"kind": "run", "id": payload.get("run_id")},
                    "domain_id": self._payload_domain(payload),
                    "session_id": payload.get("session_id"),
                    "decision_kind": "plan_confirmation",
                    "status": evidence.get("status", "PENDING"),
                    "prompt": "是否批准执行当前计划？",
                    "options": ["approve", "reject"],
                    "selected_choice": None,
                    "subject_fingerprint": evidence.get("plan_fingerprint"),
                    "version": evidence.get("version", 1),
                    "created_at": 0,
                }
            if isinstance(candidate, dict) and candidate.get("decision_id") == decision_id:
                candidate = dict(candidate)
                candidate["artifact_ref"] = path.as_posix()
                candidate["run_id"] = payload.get("run_id")
                candidate["runtime_context"] = payload.get("runtime_context")
                candidate["plan"] = payload.get("plan")
                candidate["steps"] = payload.get("steps") or []
                return candidate
        return None

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
        if payload.get("artifact_schema_version") != ACTION_ARTIFACT_SCHEMA_VERSION:
            return None
        payload.setdefault("action_execution_id", execution_id)
        if domain_id and self._payload_domain(payload) != domain_id:
            return None
        nested_result = payload.get("result")
        if isinstance(nested_result, dict):
            try:
                payload["result"] = normalize_result_contract(nested_result)
            except NestedSchemaError as exc:
                payload["result"] = unavailable_nested_view(
                    result_type=payload.get("result_type") or nested_result.get("type"),
                    reason_code=exc.reason_code,
                )
                payload["nested_schema_warning"] = exc.reason_code
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
            if payload.get("artifact_schema_version") != ACTION_ARTIFACT_SCHEMA_VERSION:
                continue
            if domain_id and self._payload_domain(payload) != domain_id:
                continue
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            records.append({
                "action_execution_id": payload.get("action_execution_id"),
                "action_id": payload.get("action_id"),
                "domain_id": self._payload_domain(payload),
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
            if payload.get("artifact_schema_version") == ACTION_ARTIFACT_SCHEMA_VERSION:
                continue
            if payload.get("artifact_schema_version") not in (
                None,
                RUN_ARTIFACT_SCHEMA_VERSION,
            ):
                continue
            if domain_id and self._payload_domain(payload) != domain_id:
                continue
            record = {
                "run_id": payload.get("run_id"),
                "domain_id": self._payload_domain(payload),
                "status": payload.get("status"),
                "request": payload.get("request"),
                "answer": payload.get("answer"),
                "error": payload.get("error"),
                "evidence_registry": normalize_evidence_registry(
                    _evidence_registry_from_payload(payload)
                ),
                "artifact_ref": path.as_posix(),
                "execution_record": payload.get("execution_record")
                or build_execution_record(payload, kind="run"),
                "modified_at": path.stat().st_mtime,
            }
            if payload.get("action_receipt") is not None:
                record["action_receipt"] = normalize_action_receipt(
                    payload.get("action_receipt")
                )
            records.append(record)
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
                if payload.get("artifact_schema_version") != ACTION_ARTIFACT_SCHEMA_VERSION:
                    continue
                if domain_id and self._payload_domain(payload) != domain_id:
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
        "steps": [
            {
                "id": step.get("id"),
                "tool": step.get("tool"),
                "args": _bounded_value(step.get("args", {})),
                "depends_on": list(step.get("depends_on") or [])[:32],
            }
            for step in (plan.get("steps") or [])[:64]
            if isinstance(step, dict)
        ],
    }


def _bounded_value(value, depth=0):
    if depth > 3:
        return None
    if isinstance(value, dict):
        return {
            str(key)[:64]: _bounded_value(item, depth + 1)
            for key, item in list(value.items())[:32]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_value(item, depth + 1) for item in list(value)[:32]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:240]
    return str(value)[:240]


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
