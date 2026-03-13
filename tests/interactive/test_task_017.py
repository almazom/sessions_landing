from __future__ import annotations

import unittest

from backend.api.interactive_replay import (
    add_history_complete_marker,
    build_replay_event_snapshot,
)


class Task017HistoryCompleteMarkerTests(unittest.TestCase):
    def test_green_adds_history_complete_marker(self) -> None:
        snapshot = build_replay_event_snapshot(
            "tests/fixtures/interactive/codex/rollout-interactive-fixture.jsonl"
        )
        marked = add_history_complete_marker(snapshot)

        self.assertTrue(marked["history_complete"])
        self.assertEqual(marked["items"][-1]["event_type"], "history_complete")
        self.assertEqual(marked["items"][-1]["payload"]["status"], "complete")
        self.assertEqual(marked["items"][-2]["event_type"], "task_complete")

    def test_red_rejects_snapshot_without_items(self) -> None:
        with self.assertRaises(ValueError):
            add_history_complete_marker({"items": [], "history_complete": False})


if __name__ == "__main__":
    unittest.main()
