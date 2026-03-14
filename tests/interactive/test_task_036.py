from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.interactive_live_state import (
    InteractiveLiveStateBroken,
    build_interactive_live_state_snapshot,
)


class Task036LiveTimelineComposerStateTests(unittest.TestCase):
    def test_green_builds_live_timeline_and_composer_state(self) -> None:
        snapshot = build_interactive_live_state_snapshot()

        self.assertEqual(
            snapshot.state_helper_path,
            Path("/home/pets/zoo/agents_sessions_dashboard/frontend/lib/interactive-state.ts"),
        )
        self.assertEqual(
            snapshot.shell_component_path,
            Path("/home/pets/zoo/agents_sessions_dashboard/frontend/components/InteractiveSessionShell.tsx"),
        )
        self.assertEqual(snapshot.phases, ["ready", "blocked"])
        self.assertEqual(
            snapshot.state_markers,
            [
                "buildInteractiveRouteState",
                "Live timeline",
                "textarea",
                "Send prompt",
                "composer.enabled",
            ],
        )
        self.assertTrue(snapshot.has_composer_form)

    def test_red_missing_state_helper_fails_honestly(self) -> None:
        missing_helper = Path("/tmp/interactive-task-check/missing-interactive-state.ts")
        with self.assertRaises(InteractiveLiveStateBroken):
            build_interactive_live_state_snapshot(state_helper_path=missing_helper)


if __name__ == "__main__":
    unittest.main()
