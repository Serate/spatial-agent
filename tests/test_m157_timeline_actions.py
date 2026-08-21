"""M157: execution timeline exposes only lifecycle-approved actions."""

import unittest

from agent.execution_timeline import build_execution_timeline, normalize_execution_timeline


class M157TimelineActionTests(unittest.TestCase):
    def test_clarification_timeline_carries_allowlisted_actions(self):
        timeline = build_execution_timeline({
            "status": "NEEDS_CLARIFICATION",
            "error": "private provider payload must not be copied",
            "plan_evidence": {"available": False},
        })
        lifecycle = timeline["events"][-1]
        self.assertEqual(lifecycle["kind"], "lifecycle")
        self.assertEqual(lifecycle["allowed_actions"], ["clarify", "cancel"])
        self.assertNotIn("private", str(timeline))

    def test_unknown_timeline_action_shape_is_bounded(self):
        normalized = normalize_execution_timeline({
            "schema_version": "spatial-agent.execution-timeline.v1",
            "available": True,
            "events": [{
                "kind": "lifecycle",
                "allowed_actions": ["clarify", "cancel", "delete-all-data"],
            }],
        })
        self.assertEqual(
            normalized["events"][0]["allowed_actions"],
            ["clarify", "cancel"],
        )


if __name__ == "__main__":
    unittest.main()
