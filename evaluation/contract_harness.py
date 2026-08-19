"""Cross-entry result contract harness.

The harness deliberately exposes a small interface to acceptance tests:
normalize a public result, compare two normalized results, and report bounded
field differences.  The implementation hides the compatibility envelope
paths so CLI, HTTP, artifact, and recovery tests do not each invent their own
contract projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence


@dataclass(frozen=True)
class CrossEntryContract:
    """Stable, JSON-safe projection of a completed public run result."""

    values: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.values)

    def differences(self, other: "CrossEntryContract") -> List[str]:
        return _differences(self.values, other.values)

    def equivalent_to(self, other: "CrossEntryContract") -> bool:
        return not self.differences(other)


def normalize_result(payload: Mapping[str, Any]) -> CrossEntryContract:
    """Project one public result onto fields that must survive entry changes.

    The projection intentionally excludes run ids, file paths, timestamps and
    other transport-specific values.  It includes request/planning evidence,
    execution governance, user answer, views and artifact availability—the
    fields that prove the same Agent Runtime contract was used.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("result payload must be a mapping")
    if not isinstance(payload.get("result"), Mapping):
        raise ValueError("result envelope is missing")
    result = _mapping(payload.get("result"))
    if not result.get("type"):
        raise ValueError("result envelope type is missing")
    planning = _mapping(result.get("planning"))
    lineage = _mapping(result.get("lineage"))
    artifact = _mapping(lineage.get("artifact"))
    views = _mapping(result.get("views"))
    panels = _mapping(views.get("panels"))
    workspace = _mapping(result.get("workspace"))
    plan_identity = _mapping(planning.get("plan_identity"))
    context = _mapping(payload.get("context_evidence"))
    section_names = context.get("section_names")
    section_names = section_names if isinstance(section_names, list) else []
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    return CrossEntryContract(
        {
            "status": payload.get("status"),
            "result_type": result.get("type"),
            "result_title": result.get("title"),
            "answer": payload.get("answer", ""),
            "planning_source": planning.get("source"),
            "plan_identity_version": plan_identity.get("version"),
            "selected_capability": planning.get("selected_capability_id"),
            "capability_candidates": planning.get("capability_candidate_ids"),
            "capability_catalog_available": planning.get("capability_catalog_available"),
            "capability_catalog_ids": planning.get("capability_catalog_ids"),
            "request_facts": result.get("request_facts"),
            "execution_policy": planning.get("execution_policy"),
            "step_governance": [
                step.get("governance")
                for step in steps
                if isinstance(step, dict)
            ],
            "capability_catalog_environment": planning.get("capability_catalog_environment"),
            "capability_catalog_tool_schema_count": planning.get(
                "capability_catalog_tool_schema_count"
            ),
            "context_has_capability_discovery": "capability_discovery"
            in section_names,
            "context_has_capability_catalog": "capability_catalog"
            in section_names,
            "exact_templates": planning.get("exact_template_ids"),
            "matched_templates": planning.get("matched_template_ids"),
            "step_tools": [
                step.get("tool")
                for step in steps
                if isinstance(step, dict)
            ],
            "step_statuses": [
                step.get("status")
                for step in steps
                if isinstance(step, dict)
            ],
            "trace_step_count": len(payload.get("trace_summary") or []),
            "artifact_available": artifact.get("available"),
            "workspace_panels": workspace.get("panels", []),
            "views_schema": views.get("schema_version"),
            "view_panels": sorted(str(key) for key in panels),
            "view_kinds": {
                str(key): _mapping(value).get("kind")
                for key, value in sorted(panels.items(), key=lambda item: str(item[0]))
            },
        }
    )


def compare_results(
    payloads: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return bounded differences across two or more public result payloads."""

    if len(payloads) < 2:
        raise ValueError("at least two result payloads are required")
    baseline = normalize_result(payloads[0])
    differences: List[str] = []
    for index, payload in enumerate(payloads[1:], start=1):
        for path in baseline.differences(normalize_result(payload)):
            differences.append(f"entry[0] vs entry[{index}]: {path}")
    return differences[:100]


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _differences(left: Any, right: Any, path: str = "$") -> List[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        differences: List[str] = []
        for key in sorted(set(left) | set(right), key=str):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                differences.append(child)
            else:
                differences.extend(_differences(left[key], right[key], child))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        if len(left) != len(right):
            differences.append(f"{path}.length")
        for index, (left_value, right_value) in enumerate(zip(left, right)):
            differences.extend(_differences(left_value, right_value, f"{path}[{index}]"))
        return differences
    return [] if left == right else [path]
