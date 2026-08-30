from __future__ import annotations

import threading
import unittest

from agent.runtime_core.progress import ProgressCoordinator
from agent.runtime_core.run_budget import RunBudget


class M332ProgressTests(unittest.TestCase):
    def test_stage_order_and_manual_heartbeat_use_safe_timing_data(self):
        clock = lambda: 0.0
        events = []
        budget = RunBudget.from_values(total_seconds=20, clock=clock)
        progress = ProgressCoordinator(
            "run-1",
            budget,
            emit=lambda *event: events.append(event),
        )

        progress.start_phase("plan", status="PLANNING", message="开始规划")
        progress.begin_attempt()
        progress.heartbeat_once()
        progress.finish_phase(message="规划完成")
        progress.close()

        self.assertEqual(
            [event[2] for event in events],
            ["stage_started", "stage_progress", "heartbeat", "stage_completed"],
        )
        self.assertEqual(events[0][1], "plan")
        heartbeat_data = events[2][5]
        self.assertEqual(heartbeat_data["heartbeat_count"], 1)
        self.assertIn("phase_elapsed_ms", heartbeat_data)
        self.assertNotIn("prompt", heartbeat_data)

    def test_close_stops_background_heartbeat(self):
        events = []
        budget = RunBudget.from_values(total_seconds=20)
        progress = ProgressCoordinator(
            "run-2",
            budget,
            emit=lambda *event: events.append(event),
            heartbeat_seconds=0.25,
        )
        progress.start_phase("execute", status="EXECUTING", message="开始执行")
        progress.close()
        count = len([event for event in events if event[2] == "heartbeat"])
        threading.Event().wait(0.35)
        self.assertEqual(
            progress._heartbeat_thread,
            None,
        )
        self.assertEqual(
            count,
            len([event for event in events if event[2] == "heartbeat"]),
        )


if __name__ == "__main__":
    unittest.main()
