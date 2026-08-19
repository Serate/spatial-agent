"""Backward-compatible import for the GIS Domain Pack answer composer.

New Runtime construction resolves the composer from the selected Domain Pack.
This shim keeps older integrations and fixtures that import the historical
module path working while the implementation lives with GIS.
"""

from domains.gis.composer import AnswerComposer

__all__ = ["AnswerComposer"]
