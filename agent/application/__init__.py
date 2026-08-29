"""Canonical application use-case seams.

The package keeps its public class names available through lazy attributes so
importing one low-level Application support module does not eagerly import all
use cases.  This preserves the package-level compatibility surface while
keeping the support modules independently importable.
"""

from importlib import import_module

_EXPORTS = {
    "RunApplication": ".run",
    "ActionApplication": ".actions",
    "DecisionApplication": ".decisions",
    "InteractionApplication": ".interactions",
    "SessionApplication": ".sessions",
}

__all__ = [
    "RunApplication",
    "ActionApplication",
    "DecisionApplication",
    "InteractionApplication",
    "SessionApplication",
]


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
