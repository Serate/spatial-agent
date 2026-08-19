"""Pluggable sources of tool definitions and implementations.

The runtime keeps validation and dispatch policy in ``ToolRegistry``. A
provider only supplies a bounded definition catalogue and performs the
provider-specific invocation. This is the seam for native tools today and
MCP/HTTP providers later; it is deliberately not an MCP dependency.
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol


class NativeToolAdapter(Protocol):
    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class ToolProvider(Protocol):
    """Small provider interface consumed by the ToolRegistry."""

    @property
    def provider_id(self) -> str:
        ...

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        ...

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class NativeToolProvider:
    """Provider for in-process adapters and repository tool definitions."""

    def __init__(self, definitions: Mapping[str, Mapping[str, Any]], adapter: NativeToolAdapter):
        self._definitions = deepcopy(dict(definitions))
        self._adapter = adapter

    @property
    def provider_id(self) -> str:
        return "native"

    @classmethod
    def from_json(cls, path: str, adapter: NativeToolAdapter) -> "NativeToolProvider":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = {tool["name"]: tool for tool in payload["tools"]}
        return cls(definitions, adapter)

    def definitions(self) -> Mapping[str, Mapping[str, Any]]:
        """Return a copy so a Registry cannot mutate provider state."""
        return deepcopy(self._definitions)

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._adapter.invoke(name, arguments)

    def export_result(self, result_ref: str, max_features: int = 100) -> Dict[str, Any]:
        exporter = getattr(self._adapter, "export_result", None)
        if not callable(exporter):
            raise AttributeError("native adapter does not support result export")
        return exporter(result_ref, max_features=max_features)
