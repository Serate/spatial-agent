"""Canonical GIS adapter seams.

The first migration slice keeps the existing implementations in their
backwards-compatible modules while making the GIS Domain the only active
owner of the adapter import path.  The implementations can move behind this
seam later without changing the Domain Pack or Runtime Factory.
"""

from .spatial import (
    DatasetCatalog,
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
