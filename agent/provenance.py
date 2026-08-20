from typing import Any, Dict, List

from agent.result_registry import ResultContractRegistry, default_result_registry
from agent.runtime_context import runtime_context_fingerprint


PROVENANCE_SCHEMA_VERSION = "spatial-agent.provenance.v1"


def build_provenance(
    payload: Dict[str, Any],
    *,
    registry: ResultContractRegistry | None = None,
) -> Dict[str, Any]:
    """Build a bounded, secret-free description of how a run was produced."""
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    plan_steps = {
        item.get("id"): item
        for item in plan.get("steps", [])
        if isinstance(item, dict) and item.get("id")
    }
    planning = payload.get("plan_evidence") if isinstance(payload.get("plan_evidence"), dict) else {}
    registry = registry or default_result_registry()
    entries: List[Dict[str, Any]] = []
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        planned = plan_steps.get(step.get("id"), {})
        entries.append(
            {
                "id": step.get("id"),
                "tool": step.get("tool"),
                "status": step.get("status"),
                "depends_on": list(step.get("depends_on") or planned.get("depends_on") or []),
                "input_bindings": _find_bindings(planned.get("args", {})),
                "result_ref": result.get("result_ref"),
                "result_summary": registry.project_provenance(
                    result,
                    _result_summary(result),
                ),
            }
        )
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "domain_id": str(planning.get("domain_id") or "unknown")[:80],
        "run_id": payload.get("run_id"),
        "execution_policy": "fail_fast",
        "steps": entries,
    }
    context_fingerprint = runtime_context_fingerprint(payload.get("runtime_context"))
    if context_fingerprint:
        provenance["runtime_context_fingerprint"] = context_fingerprint
    return provenance


def _find_bindings(value: Any) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    if isinstance(value, dict):
        if set(value) == {"$from", "path"}:
            found.append({"source_step": value["$from"], "path": value["path"]})
        else:
            for item in value.values():
                found.extend(_find_bindings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_bindings(item))
    return found


def _result_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    summary = {}
    for key in (
        "count",
        "file_count",
    ):
        if key in result and isinstance(result[key], (str, int, float, bool, list)):
            summary[key] = result[key]
    # Domain-neutral evidence for custom tools.  Only bounded counters are
    # copied automatically; arbitrary text and raw tool payloads stay out of
    # provenance unless a Domain Pack explicitly projects them.
    for key, value in result.items():
        if (
            isinstance(key, str)
            and key.endswith("_count")
            and len(key) <= 64
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            summary[key] = value
    statistics = result.get("statistics")
    if isinstance(statistics, dict):
        for key in (
            "minimum",
            "maximum",
            "mean",
            "standard_deviation",
            "valid_pixel_count",
            "nodata_ratio",
        ):
            if key in statistics and isinstance(statistics[key], (int, float)):
                summary[key] = statistics[key]
    return summary
