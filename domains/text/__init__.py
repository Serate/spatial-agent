"""Small non-GIS Domain Pack used to prove the Runtime seam."""

from .domain import TEXT_DOMAIN_PACK, TextDomainPack
from .runtime import build_text_runtime

__all__ = ["TEXT_DOMAIN_PACK", "TextDomainPack", "build_text_runtime"]
