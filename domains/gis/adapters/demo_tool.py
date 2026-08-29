"""GIS-owned deterministic demo Tool Adapter."""

from .spatial_backend import InMemorySpatialBackend, SpatialToolAdapter


class DemoSpatialAdapter(SpatialToolAdapter):
    """Backward-compatible deterministic adapter used by offline examples."""

    def __init__(self):
        super().__init__(InMemorySpatialBackend())


__all__ = ["DemoSpatialAdapter"]
