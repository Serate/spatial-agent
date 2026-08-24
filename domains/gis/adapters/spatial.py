"""GIS-owned seam for vector/raster provider implementations.

This module deliberately exposes a small import surface.  The first slice
delegates to the historical implementation so old imports remain valid; a
later slice can move the implementation here without changing
``GisDomainPack.tool_provider``.
"""

from agent.dataset_catalog import DatasetCatalog
from agent.spatial_backend import (
    GeoPackageBackend,
    HybridSpatialBackend,
    InMemorySpatialBackend,
    SpatialToolAdapter,
)

__all__ = [
    "DatasetCatalog",
    "GeoPackageBackend",
    "HybridSpatialBackend",
    "InMemorySpatialBackend",
    "SpatialToolAdapter",
]
