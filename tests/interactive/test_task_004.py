from __future__ import annotations

import unittest
from pathlib import Path

from backend.parsers.base import SessionStatus
from tests.interactive.backend_harness import (
    InteractiveHarnessFixtureNotFound,
    build_interactive_backend_harness,
)
from tests.interactive.fixtures import codex_fixture_path


class Task004BackendHarnessTests(unittest.TestCase):
    def test_green_fixture_backed_backend_harness(self) -> None:
        harness = build_interactive_backend_harness()

        self.assertEqual(harness.harness, "codex")
        self.assertEqual(harness.artifact_path, codex_fixture_path())
        self.assertEqual(harness.summary.session_id, "sess-fixture-codex-001")
        self.assertEqual(harness.summary.status, SessionStatus.COMPLETED)
        self.assertEqual(harness.route["id"], codex_fixture_path().name)
        self.assertEqual(harness.route["href"], f"/sessions/codex/{codex_fixture_path().name}")
        self.assertEqual(harness.runtime_identity["runtime"]["thread_id"], "thread-fixture-codex-001")
        self.assertEqual(
            harness.artifact_hash["sha256"],
            "321a90865f6b304780dc9d90ba69cb5cb94ff04e6a3d24f2f664e6edd3d548de",
        )

    def test_red_missing_backend_harness_fixture(self) -> None:
        missing_path = Path("/tmp/interactive-task-check/missing-rollout.jsonl")
        with self.assertRaises(InteractiveHarnessFixtureNotFound):
            build_interactive_backend_harness(artifact_path=missing_path)


if __name__ == "__main__":
    unittest.main()
