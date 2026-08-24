"""GIS-owned seam for vector/raster provider implementations.

This module deliberately exposes a small import surface for the GIS Domain.
The implementation now lives beside the Domain Pack; old ``agent.*`` module
names are compatibility facades that delegate here.
"""

from .dataset_catalog import DatasetCatalog
from .spatial_backend import (
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
