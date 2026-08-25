"""Compact contracts for the M262 architecture convergence seams."""

from __future__ import annotations

import inspect
import unittest

from agent.application.http_transport import (
    decode_json_body,
    encode_json_body,
    parse_request_target,
    query_value,
)
from agent.runtime_core.run_lifecycle import RuntimeRunLifecycle
from scripts.architecture_check import (
    COMPAT_FACADES,
    COMPAT_SHIMS,
    PUBLIC_MODULES,
    build_report,
)


class M262ArchitectureConvergenceTests(unittest.TestCase):
    def test_lifecycle_has_explicit_stages_behind_small_public_method(self):
        stage_names = (
            "_resolve",
            "_clarify",
            "_plan",
            "_validate_and_repair",
            "_execute",
            "_answer",
            "_evidence_and_finalize",
        )
        for name in stage_names:
            self.assertTrue(callable(getattr(RuntimeRunLifecycle, name)))
        source = inspect.getsource(RuntimeRunLifecycle.run)
        self.assertLess(len(source.splitlines()), 90)

    def test_guard_and_transport_contracts_are_domain_neutral(self):
        report = build_report()
        self.assertEqual(report["status"], "ok")
        self.assertFalse(PUBLIC_MODULES & (COMPAT_SHIMS | COMPAT_FACADES))
        parsed = parse_request_target("/runs?planner=rule&planner=model")
        self.assertEqual(query_value(parsed, "planner"), "rule")
        self.assertEqual(decode_json_body(encode_json_body({"ok": True})), {"ok": True})


if __name__ == "__main__":
    unittest.main()
