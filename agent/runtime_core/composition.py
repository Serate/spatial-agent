"""Domain-neutral validation for bounded Composite input references.

Components may depend on another component's public result, but the reference
must be explicit, ordered, and type-compatible with the producer declaration.
This module only validates metadata; it never reads a result or dispatches a
tool.  Execution remains owned by the existing Composite coordinator and
Domain Runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from agent.data_kinds import SUPPORTED_DATA_KINDS, normalize_data_profile


COMPOSITION_SCHEMA_VERSION = "spatial-agent.composition.v1"
_MAX_INPUTS = 8
_MAX_TEXT = 160
_ALLOWED_INPUT_FIELDS = {"name", "source", "accepted_kinds", "required"}
_ALLOWED_SOURCE_FIELDS = {"component_id", "path"}
_COMPONENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
_RESULT_PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class CompositionError(ValueError):
    """A component input reference cannot cross the composition boundary."""

    def __init__(self, message: str, *, code: str = "composition_invalid") -> None:
        self.code = str(code)[:96]
        super().__init__(str(message)[:320])


def normalize_component_inputs(value: Any) -> list[dict[str, Any]]:
    """Normalize the public component-to-component input reference list."""

    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_INPUTS:
        raise CompositionError(
            "component inputs must be a bounded array", code="composition_inputs_invalid"
        )
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) - _ALLOWED_INPUT_FIELDS:
            raise CompositionError(
                "component input contains unsupported fields",
                code="composition_input_field_invalid",
            )
        name = _text(raw.get("name"), _MAX_TEXT)
        if not name or name in names:
            raise CompositionError(
                "component input names must be unique and non-empty",
                code="composition_input_name_invalid",
            )
        source = raw.get("source")
        if not isinstance(source, Mapping) or set(source) - _ALLOWED_SOURCE_FIELDS:
            raise CompositionError(
                "component input source is invalid",
                code="composition_input_source_invalid",
            )
        component_id = _component_id(source.get("component_id"))
        path = _text(source.get("path"), _MAX_TEXT)
        if not component_id or not path or not _is_public_result_path(path):
            raise CompositionError(
                "component input source must point to a public result path",
                code="composition_input_source_invalid",
            )
        kinds = _kinds(raw.get("accepted_kinds"))
        if not kinds:
            raise CompositionError(
                "component input accepted_kinds is required",
                code="composition_input_types_missing",
            )
        names.add(name)
        result.append(
            {
                "name": name,
                "source": {"component_id": component_id, "path": path},
                "accepted_kinds": kinds,
                "required": _required_flag(raw, "required"),
            }
        )
    return result


def validate_component_composition(
    components: Sequence[Mapping[str, Any]],
    *,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Validate dependencies and optional producer/consumer data profiles."""

    if not isinstance(components, (list, tuple)):
        raise CompositionError("components must be a sequence")
    positions = {
        str(item.get("component_id")).strip().lower(): index
        for index, item in enumerate(components)
        if isinstance(item, Mapping) and item.get("component_id")
    }
    if len(positions) != len(components):
        raise CompositionError(
            "component ids must be unique and non-empty",
            code="composition_component_identity_invalid",
        )
    for index, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise CompositionError("component must be an object", code="composition_component_invalid")
        component_id = _text(component.get("component_id"), 48)
        normalized_component_id = component_id.lower()
        if not _COMPONENT_ID_PATTERN.fullmatch(normalized_component_id):
            raise CompositionError(
                "component id is invalid", code="composition_component_identity_invalid"
            )
        dependencies = component.get("depends_on") or []
        if not isinstance(dependencies, list):
            raise CompositionError("component dependencies are invalid", code="composition_dependencies_invalid")
        normalized_dependencies: list[str] = []
        for dependency in dependencies:
            dependency_id = _component_id(dependency)
            if dependency_id == normalized_component_id or dependency_id in normalized_dependencies:
                raise CompositionError(
                    "component dependencies must be unique and non-self-referential",
                    code="composition_dependencies_invalid",
                )
            if dependency_id not in positions:
                raise CompositionError(
                    "component dependency does not exist",
                    code="composition_dependency_missing",
                )
            if positions[dependency_id] >= index:
                raise CompositionError(
                    "component dependency must run earlier",
                    code="composition_dependency_order_invalid",
                )
            normalized_dependencies.append(dependency_id)
        for item in normalize_component_inputs(component.get("inputs")):
            source_id = item["source"]["component_id"]
            if source_id not in positions:
                raise CompositionError(
                    "component input source does not exist",
                    code="composition_input_source_missing",
                )
            if source_id not in dependencies:
                raise CompositionError(
                    "component input source must be declared as a dependency",
                    code="composition_input_dependency_missing",
                )
            if positions[source_id] >= index:
                raise CompositionError(
                    "component input source must run earlier",
                    code="composition_input_order_invalid",
                )
            producer_kinds = _producer_kinds(components, source_id, context)
            if producer_kinds and not producer_kinds.intersection(item["accepted_kinds"]):
                raise CompositionError(
                    "component input data profile is incompatible with its source",
                    code="composition_input_type_mismatch",
                )


def project_component_inputs(value: Any) -> list[dict[str, Any]]:
    """Return a bounded safe projection for plans, evidence, and recovery."""

    try:
        return normalize_component_inputs(value)
    except CompositionError:
        return []


def resolve_component_input_handoff(
    component: Mapping[str, Any],
    completed_results: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve typed public inputs from completed component results.

    The Composite coordinator uses this as an execution seam, not as a
    second planner.  Only paths already accepted by
    :func:`normalize_component_inputs` are traversed; values are bounded and
    private/geometry-heavy fields are omitted before a Domain service sees
    them.
    """

    if not isinstance(component, Mapping):
        raise CompositionError(
            "component is required for input resolution",
            code="composition_component_invalid",
        )
    inputs = normalize_component_inputs(component.get("inputs"))
    if not inputs:
        return {
            "schema_version": COMPOSITION_SCHEMA_VERSION,
            "state": "not_required",
            "items": [],
        }
    if not isinstance(completed_results, Mapping):
        raise CompositionError(
            "completed component results are required",
            code="composition_input_results_missing",
        )

    items: list[dict[str, Any]] = []
    for item in inputs:
        source = item["source"]
        source_id = source["component_id"]
        child = completed_results.get(source_id)
        if not isinstance(child, Mapping):
            raise CompositionError(
                "component input source is not complete",
                code="composition_input_source_incomplete",
            )
        nested = child.get("result") if isinstance(child.get("result"), Mapping) else child
        status = str(child.get("status") or nested.get("status") or "").upper()
        if status != "COMPLETED":
            raise CompositionError(
                "component input source is not complete",
                code="composition_input_source_incomplete",
            )
        profile = _runtime_input_profile(nested)
        accepted = set(item["accepted_kinds"])
        if not accepted.intersection(profile["kinds"]):
            raise CompositionError(
                "component input source data profile is incompatible",
                code="composition_input_runtime_type_mismatch",
            )
        value = _resolve_public_input_path(child, source["path"])
        if value is _MISSING:
            raise CompositionError(
                "component input result path is unavailable",
                code="composition_input_result_missing",
            )
        items.append(
            {
                "name": item["name"],
                "source": dict(source),
                "accepted_kinds": list(item["accepted_kinds"]),
                "data_profile": profile,
                "value": _project_input_value(value),
                "required": bool(item["required"]),
            }
        )
    return {
        "schema_version": COMPOSITION_SCHEMA_VERSION,
        "state": "ready",
        "items": items[:_MAX_INPUTS],
    }


def _producer_kinds(
    components: Sequence[Mapping[str, Any]],
    component_id: str,
    context: Mapping[str, Any] | None,
) -> set[str]:
    source = next(
        (
            item
            for item in components
            if isinstance(item, Mapping)
            and str(item.get("component_id") or "").strip().lower() == component_id.lower()
        ),
        None,
    )
    if not isinstance(source, Mapping) or not isinstance(context, Mapping):
        return set()
    domain_id = str(source.get("domain_id") or "")
    capability_id = str(source.get("capability_id") or "")
    for item in context.get("capability_index") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("domain_id")) != domain_id or str(item.get("capability_id")) != capability_id:
            continue
        kinds: set[str] = set()
        for profile in item.get("output_profiles") or []:
            if isinstance(profile, Mapping):
                kinds.update(_kinds(profile.get("kinds")))
        return kinds
    return set()


def _kinds(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in list(values)[:8]:
        kind = str(item or "").strip()
        if kind not in SUPPORTED_DATA_KINDS:
            raise CompositionError("unsupported component input data kind", code="composition_input_type_invalid")
        if kind not in result:
            result.append(kind)
    return result


def _component_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip().lower()
    return candidate if _COMPONENT_ID_PATTERN.fullmatch(candidate) else ""


def _is_public_result_path(value: str) -> bool:
    parts = value.split(".")
    return (
        1 <= len(parts) <= 8
        and parts[0] == "result"
        and all(_RESULT_PATH_PATTERN.fullmatch(part) for part in parts)
    )


def _required_flag(value: Mapping[str, Any], key: str) -> bool:
    if key not in value:
        return True
    raw = value.get(key)
    if not isinstance(raw, bool):
        raise CompositionError(
            "component input required must be boolean",
            code="composition_input_required_invalid",
        )
    return raw


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


_MISSING = object()
_PRIVATE_INPUT_KEYS = {
    "api_key",
    "authorization",
    "credentials",
    "password",
    "prompt",
    "messages",
    "geometry",
    "coordinates",
    "features",
    "geojson",
    "file_path",
    "source_path",
    "token",
}


def _runtime_input_profile(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    try:
        return normalize_data_profile(source.get("data_profile"), allow_legacy=True)
    except Exception:
        return {"schema_version": "spatial-agent.data-profile.v1", "primary": "unknown", "kinds": ["unknown"]}


def _resolve_public_input_path(child: Mapping[str, Any], path: str) -> Any:
    parts = str(path).split(".")
    if not parts or parts[0] != "result":
        return _MISSING
    current: Any = child.get("result") if isinstance(child.get("result"), Mapping) else child
    for part in parts[1:]:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _project_input_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:640]
    if isinstance(value, Mapping):
        return {
            str(key)[:96]: _project_input_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
            if str(key).lower() not in _PRIVATE_INPUT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_project_input_value(item, depth=depth + 1) for item in list(value)[:32]]
    return str(value)[:240]


__all__ = [
    "COMPOSITION_SCHEMA_VERSION",
    "CompositionError",
    "normalize_component_inputs",
    "project_component_inputs",
    "resolve_component_input_handoff",
    "validate_component_composition",
]
