"""Session identity helpers shared by the service facade."""

from typing import Any, Dict


def validate_session_id(session_id: str) -> None:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")


def memory_session_display_name(session_id: str) -> str:
    if session_id.startswith("conversation-"):
        suffix = session_id[len("conversation-"):]
        if suffix.isdigit():
            return "对话" + suffix
    return session_id


def dedupe_run_records(records):
    seen = set()
    result = []
    for record in records:
        run_id = record.get("run_id")
        if run_id in seen:
            continue
        seen.add(run_id)
        result.append(record)
    return result


def attach_history_lineage(records):
    """Attach only navigational evidence indexes to compact history records."""
    from result_contract import build_history_lineage

    enriched = []
    for record in records or []:
        item = dict(record or {})
        item["lineage"] = build_history_lineage(item)
        enriched.append(item)
    return enriched


def runtime_key(planner: str, backend: str) -> tuple:
    if planner not in ("rule", "openai"):
        raise ValueError("planner must be one of: rule, openai")
    if backend not in ("memory", "local"):
        raise ValueError("backend must be one of: memory, local")
    return planner, backend


def async_job_payload(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the persisted submission limited to arguments accepted by run()."""
    return {
        "request": kwargs.get("request", ""),
        "session_id": kwargs.get("session_id", "default"),
        "planner": kwargs.get("planner", "rule"),
        "backend": kwargs.get("backend", "memory"),
        "domain_id": kwargs.get("domain_id"),
        "runtime_context": kwargs.get("runtime_context"),
        "export_artifact": bool(kwargs.get("export_artifact", False)),
        "export_geojson": bool(kwargs.get("export_geojson", False)),
        "geojson_max_features": kwargs.get("geojson_max_features", 100),
        "timeout_seconds": kwargs.get("timeout_seconds"),
        "spatial_context": kwargs.get("spatial_context"),
        "workflow": kwargs.get("workflow"),
        "preview_fingerprint": kwargs.get("preview_fingerprint"),
        "require_confirmation": bool(kwargs.get("require_confirmation", False)),
        "decision_id": kwargs.get("decision_id"),
        "decision_version": kwargs.get("decision_version"),
    }
