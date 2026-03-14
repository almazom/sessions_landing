from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.interactive_route_integration import (
    InteractiveRouteIntegrationBroken,
    build_interactive_route_integration_snapshot,
)


class Task038InteractiveRouteIntegrationTests(unittest.TestCase):
    def test_green_connects_backend_boot_and_frontend_route_shell(self) -> None:
        snapshot = build_interactive_route_integration_snapshot()

        self.assertEqual(
            snapshot.backend_path,
            "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive",
        )
        self.assertEqual(
            snapshot.interactive_href,
            "/sessions/codex/rollout-interactive-fixture.jsonl/interactive",
        )
        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.transport, "codex_app_server")
        self.assertEqual(snapshot.thread_id, "thread-fixture-codex-001")
        self.assertEqual(snapshot.page_snapshot.route_suffix, "/interactive")
        self.assertEqual(
            snapshot.page_snapshot.section_headings,
            [
                "Route state",
                "Tail snapshot",
                "Replay stream",
                "Composer state",
            ],
        )
        self.assertEqual(snapshot.live_state_snapshot.phases, ["ready", "blocked"])
        self.assertEqual(
            snapshot.resilience_snapshot.state_markers,
            [
                "Reconnecting to runtime",
                "Session is busy",
                "Degraded snapshot",
                "runtime_identity?.source === 'recovered'",
                "!payload.replay.history_complete",
            ],
        )

    def test_red_surfaces_blocked_interactive_route_input(self) -> None:
        snapshot = build_interactive_route_integration_snapshot(resume_supported=False)

        self.assertFalse(snapshot.available)
        self.assertEqual(snapshot.interactive_href, "/sessions/codex/rollout-interactive-fixture.jsonl/interactive")
        self.assertEqual(snapshot.transport, "codex_app_server")
        self.assertEqual(snapshot.thread_id, "thread-fixture-codex-001")

    def test_red_missing_page_shell_breaks_bundle_honestly(self) -> None:
        missing_page = Path("/tmp/interactive-task-check/missing-interactive-page.tsx")
        with self.assertRaises(InteractiveRouteIntegrationBroken) as error:
            build_interactive_route_integration_snapshot(page_path=missing_page)

        self.assertIn("interactive route page is missing", str(error.exception))


if __name__ == "__main__":
    unittest.main()
