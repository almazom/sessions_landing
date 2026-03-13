from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.interactive_resilience_states import (
    InteractiveResilienceStatesBroken,
    build_interactive_resilience_states_snapshot,
)


class Task037ReconnectBusyErrorUiStateTests(unittest.TestCase):
    def test_green_builds_reconnect_busy_init_failure_and_degraded_states(self) -> None:
        snapshot = build_interactive_resilience_states_snapshot()

        self.assertEqual(
            snapshot.state_markers,
            [
                "Reconnecting to runtime",
                "Session is busy",
                "Degraded snapshot",
                "runtime_identity.source === 'recovered'",
                "!payload.replay.history_complete",
            ],
        )
        self.assertEqual(
            snapshot.shell_markers,
            [
                "Initialization failed",
                "Interactive bootstrap could not start for this session",
                "routeState.alerts.map",
                "alertToneClasses",
            ],
        )

    def test_red_missing_resilience_state_helper_fails_honestly(self) -> None:
        missing_helper = Path("/tmp/interactive-task-check/missing-interactive-resilience-state.ts")
        with self.assertRaises(InteractiveResilienceStatesBroken):
            build_interactive_resilience_states_snapshot(state_helper_path=missing_helper)


if __name__ == "__main__":
    unittest.main()
