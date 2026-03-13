from __future__ import annotations

import unittest
from pathlib import Path

from backend.api.interactive_replay import build_replay_event_snapshot
from tests.interactive.fixtures import codex_fixture_path


class Task016ReplayEventSnapshotTests(unittest.TestCase):
    def test_green_builds_replay_event_snapshot(self) -> None:
        snapshot = build_replay_event_snapshot(codex_fixture_path())

        self.assertEqual(
            [item["event_type"] for item in snapshot["items"]],
            [
                "user_message",
                "tool_call",
                "tool_call",
                "tool_call",
                "task_complete",
            ],
        )
        self.assertEqual(snapshot["items"][0]["event_id"], "evt-0001")
        self.assertIn(
            "Build deterministic fixture",
            snapshot["items"][0]["payload"]["text"],
        )
        self.assertEqual(snapshot["items"][-1]["payload"]["status"], "completed")
        self.assertFalse(snapshot["history_complete"])

    def test_red_missing_artifact_fails_honestly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            build_replay_event_snapshot(
                Path("/tmp/interactive-task-check/missing-rollout.jsonl")
            )


if __name__ == "__main__":
    unittest.main()
