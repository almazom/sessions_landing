from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.fixtures_bundle import (
    InteractiveFixtureBundleBroken,
    build_fixture_milestone_bundle,
)


class Task046FixtureMilestoneReproductionTests(unittest.TestCase):
    def test_fixtures_bundle_green(self) -> None:
        bundle = build_fixture_milestone_bundle()

        self.assertEqual(bundle.harness, "codex")
        self.assertEqual(bundle.fixture_artifact_id, "rollout-interactive-fixture.jsonl")
        self.assertEqual(bundle.runtime_thread_id, "thread-fixture-codex-001")
        self.assertEqual(
            bundle.artifact_sha256,
            "321a90865f6b304780dc9d90ba69cb5cb94ff04e6a3d24f2f664e6edd3d548de",
        )
        self.assertEqual(
            bundle.interactive_route,
            "/sessions/codex/rollout-interactive-fixture.jsonl/interactive",
        )
        self.assertEqual(
            bundle.scenario_names,
            [
                "tail snapshot shows last messages",
                "detail CTA opens interactive route",
                "interactive prompt roundtrip",
            ],
        )
        self.assertEqual(
            bundle.playwright_command,
            "cd frontend && npx playwright test e2e/interactive-session.spec.ts",
        )

    def test_fixtures_bundle_broken(self) -> None:
        missing_spec = Path("/tmp/interactive-task-check/missing-interactive-session.spec.ts")
        with self.assertRaises(InteractiveFixtureBundleBroken) as error:
            build_fixture_milestone_bundle(spec_path=missing_spec)

        self.assertIn("interactive Playwright spec is missing", str(error.exception))


if __name__ == "__main__":
    unittest.main()
