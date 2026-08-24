"""Canonical GIS adapter seams with lazy exports to avoid import cycles."""

__all__ = [
    "DatasetCatalog",
    "GeoPackageBackend",
    "HybridSpatialBackend",
    "InMemorySpatialBackend",
    "SpatialToolAdapter",
]


def __getattr__(name):
    if name in __all__:
        from .spatial import __dict__ as spatial_exports

        return spatial_exports[name]
    raise AttributeError(name)
