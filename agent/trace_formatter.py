from typing import Any, Dict, List

from .models import AgentRunResult, RunStatus, StepRun


def format_trace(result: AgentRunResult) -> List[str]:
    """Build a compact, user-readable trace from an Agent run."""

    lines = ["Received request: " + result.request]
    if result.resolved_request and result.resolved_request != result.request:
        lines.append("Resolved request: " + result.resolved_request)

    if result.status == RunStatus.NEEDS_CLARIFICATION:
        lines.append("Planning stopped: " + str(result.error))
        lines.append("Waiting for user clarification.")
        return lines

    if result.status == RunStatus.REJECTED:
        lines.append("Request rejected: " + str(result.error))
        return lines

    if result.status == RunStatus.FAILED:
        lines.append("Run failed: " + str(result.error))
        for step in result.steps:
            lines.append(_format_step(step))
        _append_replanning_trace(lines, result)
        return lines

    if result.status == RunStatus.CANCELLED:
        lines.append("Run cancelled: " + str(result.error))
        for step in result.steps:
            lines.append(_format_step(step))
        _append_replanning_trace(lines, result)
        return lines

    if result.status == RunStatus.TIMED_OUT:
        lines.append("Run timed out: " + str(result.error))
        for step in result.steps:
            lines.append(_format_step(step))
        _append_replanning_trace(lines, result)
        return lines

    if result.plan:
        lines.append("Planned goal: " + result.plan.goal)

    for step in result.steps:
        lines.append(_format_step(step))

    _append_replanning_trace(lines, result)
    if result.answer:
        lines.append("Final answer: " + result.answer)
    return lines


def _append_replanning_trace(lines: List[str], result: AgentRunResult) -> None:
    """Expose bounded replanning evidence in the human-readable trace."""
    for event in result.replan_events[:8]:
        if not isinstance(event, dict):
            continue
        failed_step = str(event.get("failed_step_id") or "unknown")[:96]
        failed_tool = str(event.get("failed_tool") or "unknown")[:96]
        replacement_ids = [
            str(item)[:96]
            for item in (event.get("replanned_step_ids") or [])[:24]
        ]
        replacement = ", ".join(replacement_ids) if replacement_ids else "无替代步骤"
        phase = "planning" if event.get("phase") == "planning" else "execution"
        lines.append(
            "Adaptive replan ({}): step {} ({}) failed; replacement steps: {}.".format(
                phase, failed_step, failed_tool, replacement
            )
        )


def _format_step(step: StepRun) -> str:
    base = "Tool " + step.tool + "(" + _format_args(step.args) + ") " + step.status.lower()
    if step.error:
        return base + ": " + step.error
    if not step.result:
        return base + "."

    details = _result_details(step.result)
    if details:
        return base + ", " + details + "."
    return base + "."


def _format_args(args: Dict[str, Any]) -> str:
    if "dataset" in args:
        return str(args["dataset"])
    if "left_dataset" in args and "right_dataset" in args:
        return str(args["left_dataset"]) + " -> " + str(args["right_dataset"])
    return ", ".join(sorted(args.keys()))


def _result_details(result: Dict[str, Any]) -> str:
    parts = []
    if "count" in result:
        parts.append("returned " + str(result["count"]) + " result(s)")
    if "file_count" in result:
        parts.append("file_count=" + str(result["file_count"]))
    if "admin_name" in result:
        parts.append("admin_name=" + str(result["admin_name"]))
    statistics = result.get("statistics", {})
    if isinstance(statistics, dict) and statistics.get("mean") is not None:
        parts.append("mean=" + str(statistics["mean"]))
    metrics = result.get("metrics", {})
    if isinstance(metrics, dict) and "probed_files" in metrics:
        parts.append("probed_files=" + str(metrics["probed_files"]))
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and "width" in metadata and "height" in metadata:
        parts.append("size=" + str(metadata["width"]) + "x" + str(metadata["height"]))
    if "result_ref" in result:
        parts.append("result_ref=" + str(result["result_ref"]))
    if "crs" in result and result["crs"]:
        parts.append("crs=" + str(result["crs"]))
    if "sample_names" in result and result["sample_names"]:
        parts.append("sample_names=" + ", ".join(map(str, result["sample_names"])))
    return "; ".join(parts)
