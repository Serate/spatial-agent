"""Domain-neutral result type metadata registry.

The result envelope owns the stable shape, while a Domain Pack owns the
labels and workspace registration for its result types.  The default registry
is loaded lazily from the GIS pack for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ResultTypeSpec:
    """Bounded metadata needed to route a result to a workspace."""

    title: str | None = None
    panels: tuple[str, ...] = ()


class ResultContractRegistry:
    """Immutable result metadata supplied by a Domain Pack."""

    def __init__(
        self,
        specs: Mapping[str, ResultTypeSpec] | None = None,
        *,
        fallback_title: str = "运行结果",
    ) -> None:
        self._specs = {
            str(key): value
            for key, value in (specs or {}).items()
            if str(key) and isinstance(value, ResultTypeSpec)
        }
        self._fallback_title = str(fallback_title or "运行结果")[:120]

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

    def as_context(self) -> dict[str, object]:
        """Expose only JSON-safe metadata for capability/evidence consumers."""
        return {
            "result_types": [
                {
                    "type": result_type,
                    "title": spec.title,
                    "panels": list(spec.panels),
                }
                for result_type, spec in self._specs.items()
            ],
            "fallback_title": self._fallback_title,
        }


def default_result_registry() -> ResultContractRegistry:
    """Load the legacy GIS result metadata without importing GIS eagerly."""
    from domains.gis.result_registry import GIS_RESULT_REGISTRY

    return GIS_RESULT_REGISTRY
