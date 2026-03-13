from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.playwright_skeleton import (
    InteractivePlaywrightSkeletonNotFound,
    build_interactive_playwright_skeleton,
)


class Task005PlaywrightSkeletonTests(unittest.TestCase):
    def test_green_builds_fixture_backed_playwright_skeleton(self) -> None:
        skeleton = build_interactive_playwright_skeleton()

        self.assertEqual(
            skeleton.spec_path,
            Path("/home/pets/zoo/agents_sessions_dashboard/frontend/e2e/interactive-session.spec.ts"),
        )
        self.assertEqual(
            skeleton.config_path,
            Path("/home/pets/zoo/agents_sessions_dashboard/frontend/playwright.config.ts"),
        )
        self.assertEqual(skeleton.fixture_artifact_id, "rollout-interactive-fixture.jsonl")
        self.assertEqual(
            skeleton.detail_route,
            "/sessions/codex/rollout-interactive-fixture.jsonl",
        )
        self.assertEqual(
            skeleton.interactive_route,
            "/sessions/codex/rollout-interactive-fixture.jsonl/interactive",
        )
        self.assertEqual(
            skeleton.scenario_names,
            [
                "tail snapshot shows last messages",
                "detail CTA opens interactive route",
                "interactive prompt roundtrip",
            ],
        )
        self.assertEqual(
            skeleton.command,
            "cd frontend && npx playwright test e2e/interactive-session.spec.ts",
        )

    def test_red_missing_playwright_spec_fails_honestly(self) -> None:
        missing_path = Path("/tmp/interactive-task-check/missing-interactive-session.spec.ts")
        with self.assertRaises(InteractivePlaywrightSkeletonNotFound):
            build_interactive_playwright_skeleton(spec_path=missing_path)


if __name__ == "__main__":
    unittest.main()
