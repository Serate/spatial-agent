from typing import Any, Dict, List


def build_provenance(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a bounded, secret-free description of how a run was produced."""
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    plan_steps = {
        item.get("id"): item
        for item in plan.get("steps", [])
        if isinstance(item, dict) and item.get("id")
    }
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
                "result_summary": _result_summary(result),
            }
        )
    return {
        "run_id": payload.get("run_id"),
        "execution_policy": "fail_fast",
        "steps": entries,
    }


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
        "admin_name",
        "crs",
        "first_name",
        "matched_files",
    ):
        if key in result and isinstance(result[key], (str, int, float, bool, list)):
            summary[key] = result[key]
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
