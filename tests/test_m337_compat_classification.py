"""Compact contracts for M337 compatibility classification guards."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import architecture_check


class M337CompatibilityClassificationTests(unittest.TestCase):
    def test_current_manifest_is_immutable_and_reported(self):
        report = architecture_check.build_report()

        self.assertEqual(report["status"], "ok")
        self.assertIsInstance(architecture_check.COMPAT_SHIMS, frozenset)
        self.assertIsInstance(architecture_check.COMPAT_FACADES, frozenset)
        self.assertIsInstance(architecture_check.PUBLIC_MODULES, frozenset)
        self.assertIsInstance(architecture_check.COMPAT_MODULES, frozenset)
        self.assertEqual(
            report["metrics"]["classification_schema_version"],
            architecture_check.CLASSIFICATION_SCHEMA_VERSION,
        )
        classification = report["metrics"]["module_classification"]
        self.assertEqual(classification["agent/answer_composer.py"], "shim")
        self.assertEqual(classification["agent/planner.py"], "facade")
        self.assertEqual(classification["agent/domain_contract.py"], "public")

    def test_missing_public_module_has_stable_error_code(self):
        report = self._isolated_report(public={"agent/missing.py"})

        self.assertIn("public_module_missing", self._error_codes(report))

    def test_public_compatibility_overlap_has_stable_error_code(self):
        report = self._isolated_report(
            public={"agent/shared.py"},
            shims={"agent/shared.py"},
        )

        self.assertIn("public_module_marked_compat", self._error_codes(report))

    def test_public_directory_is_not_accepted_as_python_module(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "agent" / "directory.py").mkdir(parents=True)
            report = self._isolated_report(
                root=root,
                public={"agent/directory.py"},
            )

        self.assertIn("public_module_not_file", self._error_codes(report))

    def test_shim_with_function_is_not_a_forwarder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "bad_shim.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                '"""Bad shim."""\n\n'
                "from agent.canonical import Thing\n\n"
                "def helper():\n    return Thing\n",
                encoding="utf-8",
            )
            report = self._isolated_report(
                root=root,
                shims={"agent/bad_shim.py"},
            )

        self.assertIn("compat_shim_not_forwarder", self._error_codes(report))

    def test_shim_without_forwarding_import_is_not_a_forwarder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "empty_shim.py"
            path.parent.mkdir(parents=True)
            path.write_text('"""Empty shim."""\n', encoding="utf-8")
            report = self._isolated_report(
                root=root,
                shims={"agent/empty_shim.py"},
            )

        self.assertIn("compat_shim_not_forwarder", self._error_codes(report))

    def test_oversized_shim_has_stable_error_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "large_shim.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                '"""Large shim."""\n\n'
                "from agent.canonical import Thing\n"
                + "# padding\n" * architecture_check.COMPAT_SHIM_MAX_LINES,
                encoding="utf-8",
            )
            report = self._isolated_report(
                root=root,
                shims={"agent/large_shim.py"},
            )

        self.assertIn("compat_shim_too_large", self._error_codes(report))

    def test_facade_is_not_restricted_to_shim_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "agent" / "facade.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                '"""Compatibility facade."""\n\n'
                "def adapt(value):\n    return value\n",
                encoding="utf-8",
            )
            report = self._isolated_report(
                root=root,
                facades={"agent/facade.py"},
            )

        self.assertNotIn("compat_shim_not_forwarder", self._error_codes(report))

    @staticmethod
    def _error_codes(report):
        return {error.get("code") for error in report["errors"]}

    @staticmethod
    def _isolated_report(*, root=None, public=None, shims=None, facades=None):
        root = root or Path(tempfile.mkdtemp())
        public = frozenset(public or ())
        shims = frozenset(shims or ())
        facades = frozenset(facades or ())
        with patch.multiple(
            architecture_check,
            ROOT=root,
            PUBLIC_MODULES=public,
            COMPAT_SHIMS=shims,
            COMPAT_FACADES=facades,
            COMPAT_MODULES=public | shims | facades,
        ):
            return architecture_check.build_report()


if __name__ == "__main__":
    unittest.main()
