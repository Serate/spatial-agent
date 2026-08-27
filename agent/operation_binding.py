"""Domain-neutral binding between analysis operations and result profiles.

An analysis operation is planner vocabulary, while a workflow and a Result
profile are owned by a Domain Pack.  This module only defines the small
compatibility contract between them.  It never selects a tool or authorizes
execution; the canonical TaskPlan and ToolRegistry gates remain authoritative.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent.data_kinds import SUPPORTED_DATA_KINDS


OPERATION_BINDING_SCHEMA_VERSION = "spatial-agent.operation-binding.v1"
_MAX_ITEMS = 16

# These are deliberately broad semantic envelopes.  A Domain still declares
# the concrete result types and the result registry supplies their profiles.
# The binding is invalid when a declared operation has no compatible profile;
# it does not infer an operation from a tool name.
OPERATION_OUTPUT_KINDS: dict[str, frozenset[str]] = {
    "query": frozenset(SUPPORTED_DATA_KINDS) - {"unknown"},
    "filter": frozenset({"vector", "raster", "metrics", "composite"}),
    "aggregate": frozenset({"vector", "raster", "metrics", "timeseries", "composite"}),
    "trend": frozenset({"timeseries", "metrics", "composite"}),
    "compare": frozenset({"metrics", "timeseries", "composite"}),
    "spatial_operation": frozenset({"vector", "raster", "composite"}),
    "evidence": frozenset({"document_evidence"}),
}


def inspect_operation_binding(
    capability: Mapping[str, Any],
    *,
    workflow_ids: Sequence[str] = (),
    result_profiles: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect one capability's operation/workflow/profile closure.

    The return value is a safe receipt suitable for catalog evidence.  It is
    intentionally explicit about ``unknown`` versus ``invalid`` so callers
    can keep diagnostics visible without allowing either state to execute.
    """

    source = capability if isinstance(capability, Mapping) else {}
    operations = _strings(source.get("analysis_operations"))
    workflows = _strings(workflow_ids)
    result_types = _strings(source.get("result_types"))
    profiles = result_profiles if isinstance(result_profiles, Mapping) else None
    base: dict[str, Any] = {
        "schema_version": OPERATION_BINDING_SCHEMA_VERSION,
        "operations": operations[:_MAX_ITEMS],
        "workflow_ids": workflows[:_MAX_ITEMS],
        "result_types": result_types[:_MAX_ITEMS],
        "output_profiles": [],
        "bindings": [],
    }

    if not operations:
        if not source.get("tools") and set(result_types).issubset({"direct_answer"}):
            base.update({"status": "not_applicable", "reason_code": "answer_only_capability"})
            return base
        # Older/custom Domain Packs may not have adopted the operation
        # vocabulary yet. Keep them compatible, but do not claim that their
        # operation/profile closure is ready until they publish one.
        base.update({"status": "not_declared", "reason_code": "operation_declaration_unavailable"})
        return base
    if not workflows:
        base.update({"status": "invalid", "reason_code": "workflow_unbound"})
        return base
    if len(workflows) != 1:
        base.update({"status": "invalid", "reason_code": "workflow_binding_ambiguous"})
        return base
    if profiles is None:
        base.update({"status": "unknown", "reason_code": "result_profiles_unknown"})
        return base

    output_profiles: list[dict[str, Any]] = []
    missing_profiles: list[str] = []
    for result_type in result_types:
        raw = profiles.get(result_type)
        profile = _profile(result_type, raw)
        if profile is None:
            missing_profiles.append(result_type)
            continue
        output_profiles.append(profile)
    base["output_profiles"] = output_profiles[:_MAX_ITEMS]
    if missing_profiles:
        base["missing_result_profiles"] = missing_profiles[:_MAX_ITEMS]
        base.update({"status": "invalid", "reason_code": "result_profile_missing"})
        return base

    invalid_operations: list[str] = []
    for operation in operations:
        allowed = sorted(OPERATION_OUTPUT_KINDS.get(operation, ()))
        compatible = [
            profile["result_type"]
            for profile in output_profiles
            if set(profile["kinds"]) & set(allowed)
        ]
        binding = {
            "operation": operation,
            "allowed_output_kinds": allowed,
            "result_types": compatible[:_MAX_ITEMS],
            "valid": bool(compatible),
        }
        base["bindings"].append(binding)
        if not compatible:
            invalid_operations.append(operation)
    if invalid_operations:
        base["invalid_operations"] = invalid_operations[:_MAX_ITEMS]
        base.update({"status": "invalid", "reason_code": "operation_result_profile_mismatch"})
        return base

    base.update({"status": "ready", "reason_code": "operation_binding_valid"})
    return base


def _profile(result_type: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    raw_kinds = value.get("kinds")
    if isinstance(raw_kinds, str):
        raw_kinds = [raw_kinds]
    if not isinstance(raw_kinds, (list, tuple)):
        return None
    kinds = []
    for item in raw_kinds[:8]:
        kind = str(item or "").strip()
        if kind in SUPPORTED_DATA_KINDS and kind not in kinds:
            kinds.append(kind)
    if not kinds or "unknown" in kinds:
        return None
    primary = str(value.get("primary") or kinds[0]).strip()
    if primary not in kinds:
        primary = kinds[0]
    return {
        "result_type": str(result_type)[:96],
        "schema_version": str(value.get("schema_version") or "spatial-agent.data-profile.v1")[:96],
        "primary": primary,
        "kinds": kinds,
    }


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()[:96]
        if text and text not in result:
            result.append(text)
    return result[:_MAX_ITEMS]


__all__ = [
    "OPERATION_BINDING_SCHEMA_VERSION",
    "OPERATION_OUTPUT_KINDS",
    "inspect_operation_binding",
]
