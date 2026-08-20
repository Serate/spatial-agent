"""Keep top-level-aware unittest discovery focused on the compact gate.

The repository retains milestone tests as explicit diagnostic assets, but
loading all of them on every local discovery run makes feedback needlessly
slow.  ``unittest discover -s tests -t .`` calls this hook for package
discovery, so the active suite is deliberately small and stable.  The
explicit top-level directory is important: without it, unittest treats
``tests`` as a flat search root and bypasses this package hook.
"""

from importlib import import_module
import unittest


ACTIVE_MODULES = ("test_dev_gate", "test_http_contract")


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    for name in ACTIVE_MODULES:
        module = import_module(f"{__name__}.{name}")
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
