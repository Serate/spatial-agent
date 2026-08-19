"""GIS domain pack used by the demo and real local spatial backends.

The public pack is loaded lazily.  The catalog is also imported by the
generic capability module, so eager package initialization would create a
cycle through ``domains.gis.domain``.
"""

from typing import Any

__all__ = ["GIS_DOMAIN_PACK", "GisDomainPack"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .domain import GIS_DOMAIN_PACK, GisDomainPack

        return {
            "GIS_DOMAIN_PACK": GIS_DOMAIN_PACK,
            "GisDomainPack": GisDomainPack,
        }[name]
    raise AttributeError(name)
