"""Contracts for the shared HTTP route metadata seam."""

from __future__ import annotations

import unittest

from agent.application.http_routes import resolve_route


class HTTPRouteMetadataTests(unittest.TestCase):
    def test_root_and_resource_routes_share_semantic_actions(self):
        cases = (
            ("GET", "/capabilities", "capabilities", None),
            ("GET", "/runs/run-1", "run", "run-1"),
            ("GET", "/runs/run-1/events", "run_events", "run-1"),
            ("POST", "/runs", "run", None),
            ("POST", "/runs/run-1/retry", "retry", "run-1"),
            ("POST", "/workflows/demo/validate", "workflow_validate", None),
        )
        for method, path, action, resource_id in cases:
            with self.subTest(method=method, path=path):
                match = resolve_route(method, path)
                self.assertIsNotNone(match)
                self.assertEqual(match.action, action)
                self.assertEqual(match.resource_id, resource_id)

        self.assertEqual(
            resolve_route("POST", "/workflows/demo/validate").template_id,
            "demo",
        )

    def test_unknown_and_wrong_method_routes_fail_closed(self):
        self.assertIsNone(resolve_route("GET", "/runs/run-1/retry"))
        self.assertIsNone(resolve_route("POST", "/not-a-route"))
        self.assertIsNone(resolve_route("DELETE", "/runs/run-1"))


if __name__ == "__main__":
    unittest.main()
