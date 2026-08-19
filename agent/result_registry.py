"""Domain-neutral result type metadata registry.

The result envelope owns the stable shape, while a Domain Pack owns the
labels and workspace registration for its result types.  The default registry
is loaded lazily from the GIS pack for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ViewSpec:
    """Bounded renderer metadata supplied by a Domain Pack."""

    view_id: str
    renderer: str = "generic"
    title: str | None = None
    schema_version: str = "spatial-agent.view.v1"

    def as_dict(self) -> dict[str, str]:
        return {
            "id": str(self.view_id)[:48],
            "renderer": str(self.renderer or "generic")[:48],
            "title": str(self.title)[:120] if self.title else "",
            "schema_version": str(self.schema_version or "spatial-agent.view.v1")[:80],
        }


@dataclass(frozen=True)
class ResultTypeSpec:
    """Bounded metadata needed to route a result to a workspace."""

    title: str | None = None
    panels: tuple[str, ...] = ()
    requires_geometry: bool = False
    view_specs: tuple[ViewSpec, ...] = ()


class ResultContractRegistry:
    """Immutable result metadata supplied by a Domain Pack."""

    def __init__(
        self,
        specs: Mapping[str, ResultTypeSpec] | None = None,
        *,
        fallback_title: str = "运行结果",
        view_builder: Callable[..., Mapping[str, Any]] | None = None,
        provenance_projector: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        self._specs = {
            str(key): value
            for key, value in (specs or {}).items()
            if str(key) and isinstance(value, ResultTypeSpec)
        }
        self._fallback_title = str(fallback_title or "运行结果")[:120]
        self._view_builder = view_builder
        self._provenance_projector = provenance_projector

    def spec(self, result_type: str) -> ResultTypeSpec | None:
        return self._specs.get(str(result_type or ""))

    def title_for(self, result_type: str) -> str:
        spec = self.spec(result_type)
        return str(spec.title)[:120] if spec and spec.title else self._fallback_title

    def panels_for(self, result_type: str) -> tuple[str, ...]:
        spec = self.spec(result_type)
        if spec is None:
            return ()
        return tuple(str(item)[:40] for item in spec.panels if str(item))[:12]

    def is_registered(self, result_type: str) -> bool:
        return self.spec(result_type) is not None

    def requires_geometry(self, result_type: str) -> bool:
        spec = self.spec(result_type)
        return bool(spec and spec.requires_geometry)

    def view_specs_for(self, result_type: str) -> list[dict[str, str]]:
        spec = self.spec(result_type)
        if spec is None:
            return []
        return [item.as_dict() for item in spec.view_specs[:12] if isinstance(item, ViewSpec)]

    def build_views(
        self,
        result_type: str,
        *,
        steps: list[Any],
        geometry_evidence: Mapping[str, Any],
        geojson_ref: Any = None,
        workspace: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build views through the selected domain, with generic empty views."""
        if not callable(self._view_builder):
            return {"schema_version": "spatial-agent.views.v1", "panels": {}}
        value = self._view_builder(
            result_type,
            steps=steps,
            geometry_evidence=geometry_evidence,
            geojson_ref=geojson_ref,
            workspace=workspace,
        )
        if isinstance(value, Mapping):
            return dict(value)
        return {"schema_version": "spatial-agent.views.v1", "panels": {}}

    def project_provenance(
        self,
        result: Mapping[str, Any],
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Project bounded domain evidence into a generic provenance summary."""
        if not callable(self._provenance_projector):
            return dict(summary)
        value = self._provenance_projector(result, dict(summary))
        return dict(value) if isinstance(value, Mapping) else dict(summary)

    def as_context(self) -> dict[str, object]:
        """Expose only JSON-safe metadata for capability/evidence consumers."""
        return {
            "result_types": [
                {
                    "type": result_type,
                    "title": spec.title,
                    "panels": list(spec.panels),
                    "requires_geometry": spec.requires_geometry,
                    "view_specs": [
                        item.as_dict()
                        for item in spec.view_specs[:12]
                        if isinstance(item, ViewSpec)
                    ],
                }
                for result_type, spec in self._specs.items()
            ],
            "fallback_title": self._fallback_title,
        }


def default_result_registry() -> ResultContractRegistry:
    """Load the legacy GIS result metadata without importing GIS eagerly."""
    from domains.gis.result_registry import GIS_RESULT_REGISTRY

    return GIS_RESULT_REGISTRY
