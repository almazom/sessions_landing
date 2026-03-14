from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.api.interactive_tail import build_interactive_tail_snapshot
from tests.interactive.fixtures import codex_fixture_path


class Task015TailSnapshotExtractionTests(unittest.TestCase):
    def test_green_extracts_tail_snapshot_from_fixture_artifact(self) -> None:
        snapshot = build_interactive_tail_snapshot(codex_fixture_path())

        self.assertEqual(len(snapshot["items"]), 3)
        self.assertEqual(snapshot["items"][0]["kind"], "message")
        self.assertEqual(snapshot["items"][0]["role"], "user")
        self.assertIn("Build deterministic fixture", snapshot["items"][0]["text"])
        self.assertEqual(snapshot["items"][1]["kind"], "status_hint")
        self.assertIn("task_complete", snapshot["items"][1]["text"])
        self.assertEqual(snapshot["items"][2]["kind"], "identity_hint")
        self.assertIn("thread-fixture-codex-001", snapshot["items"][2]["text"])
        self.assertIn("exec_command", snapshot["summary_hint"])
        self.assertTrue(snapshot["has_more_before"])

    def test_red_missing_artifact_fails_honestly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            build_interactive_tail_snapshot(
                Path("/tmp/interactive-task-check/missing-rollout.jsonl")
            )

    def test_green_keeps_tail_snapshot_honest_without_runtime_mapping(self) -> None:
        with patch(
            "backend.api.interactive_tail.resolve_runtime_identity_from_artifact_route",
            side_effect=LookupError("missing mapping"),
        ):
            snapshot = build_interactive_tail_snapshot(codex_fixture_path())

        self.assertEqual(snapshot["items"][2]["kind"], "identity_hint")
        self.assertIn("no live runtime mapping yet", snapshot["items"][2]["text"])


if __name__ == "__main__":
    unittest.main()
