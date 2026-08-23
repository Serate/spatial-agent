"""One migration and validation seam for nested result contracts.

Result envelopes are consumed by synchronous, asynchronous, artifact and
Console entry points.  Keeping version checks in those consumers separately
made it easy for one path to silently accept a future workspace or view
shape.  This module owns the small, domain-neutral nested boundary.

Missing versions are the only legacy compatibility case.  An unknown
version is never interpreted as the current shape; callers may turn the
bounded error into an unavailable view during artifact recovery.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.contract_versions import (
    RESULT_ENVELOPE_SCHEMA_VERSION,
    VIEW_SCHEMA_VERSION,
    VIEWS_SCHEMA_VERSION,
    WORKSPACE_SCHEMA_VERSION,
)
from agent.artifact_reference import normalize_artifact_reference
from agent.conversation_turn import normalize_conversation_turn


class NestedSchemaError(ValueError):
    """A nested result contract cannot be safely interpreted."""

    code = "nested_schema_invalid"

    def __init__(self, message: str, *, path: str, reason_code: str):
        super().__init__(message)
        self.path = str(path)[:160]
        self.reason_code = str(reason_code)[:96]


def normalize_result_contract(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate and minimally migrate a result envelope's nested sections."""

    result = _mapping(value, path="result")
    result = dict(result)
    result["schema_version"] = _version(
        result.get("schema_version"),
        RESULT_ENVELOPE_SCHEMA_VERSION,
        path="result.schema_version",
        allow_legacy=allow_legacy,
    )
    workspace = result.get("workspace")
    if workspace is None and allow_legacy:
        workspace = {"schema_version": WORKSPACE_SCHEMA_VERSION, "panels": [], "view_specs": []}
    result["workspace"] = normalize_workspace(workspace, allow_legacy=allow_legacy)
    views = result.get("views")
    if views is None and allow_legacy:
        views = {"schema_version": VIEWS_SCHEMA_VERSION, "panels": {}}
    result["views"] = normalize_views(views, allow_legacy=allow_legacy)
    result["conversation_turn"] = normalize_conversation_turn(
        result.get("conversation_turn")
    )
    _normalize_artifact_references(result)
    return result


def _normalize_artifact_references(result: dict[str, Any]) -> None:
    """Keep persisted artifact locators safe and portable across recovery."""

    artifacts = result.get("artifacts")
    if isinstance(artifacts, Mapping):
        normalized_artifacts = dict(artifacts)
        for key in ("run", "geometry"):
            if key in normalized_artifacts:
                normalized_artifacts[key] = normalize_artifact_reference(
                    normalized_artifacts.get(key)
                )
        result["artifacts"] = normalized_artifacts

    geometry = result.get("geometry")
    if isinstance(geometry, Mapping) and "reference" in geometry:
        normalized_geometry = dict(geometry)
        normalized_geometry["reference"] = normalize_artifact_reference(
            geometry.get("reference")
        )
        result["geometry"] = normalized_geometry

    references = result.get("references")
    if isinstance(references, list):
        normalized_references = []
        for item in references[:32]:
            if not isinstance(item, Mapping):
                continue
            reference = dict(item)
            if "artifact_reference" in reference:
                reference["artifact_reference"] = normalize_artifact_reference(
                    reference.get("artifact_reference")
                )
            normalized_references.append(reference)
        result["references"] = normalized_references


def normalize_workspace(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate/migrate ``result.workspace`` without interpreting domain data."""

    workspace = dict(_mapping(value, path="result.workspace"))
    workspace["schema_version"] = _version(
        workspace.get("schema_version"),
        WORKSPACE_SCHEMA_VERSION,
        path="result.workspace.schema_version",
        allow_legacy=allow_legacy,
    )
    panels = workspace.get("panels", [])
    if not isinstance(panels, list):
        raise NestedSchemaError(
            "workspace.panels must be a list",
            path="result.workspace.panels",
            reason_code="workspace_panels_invalid",
        )
    workspace["panels"] = [str(item)[:64] for item in panels[:20] if isinstance(item, (str, int))]
    specs = workspace.get("view_specs", [])
    if not isinstance(specs, list):
        raise NestedSchemaError(
            "workspace.view_specs must be a list",
            path="result.workspace.view_specs",
            reason_code="workspace_view_specs_invalid",
        )
    workspace["view_specs"] = [
        normalize_view_spec(item, index=index, allow_legacy=allow_legacy)
        for index, item in enumerate(specs[:20])
    ]
    return workspace


def normalize_view_spec(value: Any, *, index: int = 0, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate one renderer declaration nested in a workspace."""

    path = f"result.workspace.view_specs[{index}]"
    spec = dict(_mapping(value, path=path))
    view_id = str(spec.get("id") or "").strip()
    if not view_id:
        raise NestedSchemaError(
            "view spec id is required",
            path=path + ".id",
            reason_code="view_spec_id_missing",
        )
    spec["id"] = view_id[:64]
    spec["renderer"] = str(spec.get("renderer") or "generic")[:64]
    spec["schema_version"] = _version(
        spec.get("schema_version"),
        VIEW_SCHEMA_VERSION,
        path=path + ".schema_version",
        allow_legacy=allow_legacy,
    )
    if spec.get("title") is not None:
        spec["title"] = str(spec["title"])[:120]
    return spec


def normalize_views(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate/migrate ``result.views`` and every nested panel model."""

    views = dict(_mapping(value, path="result.views"))
    views["schema_version"] = _version(
        views.get("schema_version"),
        VIEWS_SCHEMA_VERSION,
        path="result.views.schema_version",
        allow_legacy=allow_legacy,
    )
    panels = views.get("panels", {})
    if not isinstance(panels, Mapping):
        raise NestedSchemaError(
            "views.panels must be an object",
            path="result.views.panels",
            reason_code="views_panels_invalid",
        )
    normalized: dict[str, Any] = {}
    for panel_id, panel in list(panels.items())[:20]:
        normalized[str(panel_id)[:64]] = normalize_panel(
            panel,
            panel_id=str(panel_id),
            allow_legacy=allow_legacy,
        )
    views["panels"] = normalized
    return views


def normalize_panel(value: Any, *, panel_id: str = "panel", allow_legacy: bool = True) -> dict[str, Any]:
    """Validate one view panel and stamp the known panel schema on legacy data."""

    path = f"result.views.panels[{panel_id[:64]}]"
    panel = dict(_mapping(value, path=path))
    kind = str(panel.get("kind") or "").strip()
    if not kind:
        raise NestedSchemaError(
            "view panel kind is required",
            path=path + ".kind",
            reason_code="view_panel_kind_missing",
        )
    panel["kind"] = kind[:96]
    panel["schema_version"] = _version(
        panel.get("schema_version"),
        VIEW_SCHEMA_VERSION,
        path=path + ".schema_version",
        allow_legacy=allow_legacy,
    )
    if panel.get("view_id") is not None:
        panel["view_id"] = str(panel["view_id"])[:64]
    if panel.get("state") is not None:
        panel["state"] = str(panel["state"])[:32]
    return panel


def validate_async_nested_sections(value: Any, *, allow_legacy: bool = True) -> dict[str, Any]:
    """Validate the workspace/views subset carried by async evidence.

    Async evidence is a projection, not a full result envelope, so it is
    validated by wrapping its two nested sections in the same seam.
    """

    evidence = _mapping(value, path="async_result_evidence")
    workspace = normalize_workspace(evidence.get("workspace") or {}, allow_legacy=allow_legacy)
    views = normalize_views(evidence.get("views") or {}, allow_legacy=allow_legacy)
    return {"workspace": workspace, "views": views}


def unavailable_nested_view(*, result_type: Any = "unknown", reason_code: str = "nested_schema_invalid") -> dict[str, Any]:
    """Return a bounded result-shaped fallback for recovery consumers."""

    reason = str(reason_code or "nested_schema_invalid")[:96]
    return {
        "schema_version": RESULT_ENVELOPE_SCHEMA_VERSION,
        "type": str(result_type or "unknown")[:96],
        "workspace": {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "result_type": str(result_type or "unknown")[:96],
            "panels": ["generic"],
            "view_specs": [{
                "id": "generic",
                "renderer": "generic",
                "title": "结构化结果",
                "schema_version": VIEW_SCHEMA_VERSION,
            }],
        },
        "views": {
            "schema_version": VIEWS_SCHEMA_VERSION,
            "panels": {
                "generic": {
                    "schema_version": VIEW_SCHEMA_VERSION,
                    "kind": "unavailable",
                    "state": "unavailable",
                    "view_id": "generic",
                    "reason": reason,
                    "artifact_available": False,
                }
            },
        },
    }


def _mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NestedSchemaError(
            f"{path} must be an object",
            path=path,
            reason_code="nested_object_required",
        )
    return value


def _version(value: Any, expected: str, *, path: str, allow_legacy: bool) -> str:
    if value is None or value == "":
        if allow_legacy:
            return expected
        raise NestedSchemaError(
            f"{path} is missing",
            path=path,
            reason_code="nested_schema_version_missing",
        )
    version = str(value)[:96]
    if version != expected:
        raise NestedSchemaError(
            f"unknown schema version at {path}",
            path=path,
            reason_code="nested_schema_unknown_version",
        )
    return expected


__all__ = [
    "NestedSchemaError",
    "normalize_result_contract",
    "normalize_workspace",
    "normalize_views",
    "normalize_panel",
    "normalize_view_spec",
    "validate_async_nested_sections",
    "unavailable_nested_view",
]
