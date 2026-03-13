from __future__ import annotations

import unittest

from tests.interactive.event_stream_contract import (
    InteractiveEventStreamContractBroken,
    build_event_stream_contract_snapshot,
)


class Task029EventStreamContractTests(unittest.TestCase):
    def test_green_event_stream_contract_holds_for_normalized_sequence(self) -> None:
        snapshot = build_event_stream_contract_snapshot()

        self.assertEqual(snapshot["event_count"], 3)
        self.assertEqual(
            snapshot["ordered_kinds"],
            ["command", "tool_fallback", "agent_message"],
        )
        self.assertEqual(snapshot["completed_count"], 3)
        self.assertTrue(snapshot["has_fallback_event"])

    def test_red_event_stream_contract_fails_on_unsupported_event(self) -> None:
        with self.assertRaises(InteractiveEventStreamContractBroken):
            build_event_stream_contract_snapshot(include_unknown_event=True)


if __name__ == "__main__":
    unittest.main()
