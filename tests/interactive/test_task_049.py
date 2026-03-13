from __future__ import annotations

import unittest

from tests.interactive.runtime_control_bundle import (
    InteractiveRuntimeControlBundleBroken,
    build_runtime_control_milestone_bundle,
)


class Task049SupervisorControlMilestoneReproductionTests(unittest.TestCase):
    def test_runtime_control_bundle_green(self) -> None:
        bundle = build_runtime_control_milestone_bundle()

        self.assertEqual(bundle.start_operation, "resume")
        self.assertEqual(bundle.stop_operation, "cancel")
        self.assertEqual(bundle.claimed_lock_status, "claimed")
        self.assertEqual(bundle.released_lock_status, "released")
        self.assertEqual(
            bundle.event_kinds,
            ("command", "tool_fallback", "agent_message"),
        )
        self.assertEqual(
            bundle.validated_action_types,
            ("prompt_submit", "cancel_interrupt", "waiting_response"),
        )

    def test_runtime_control_bundle_broken(self) -> None:
        with self.assertRaises(InteractiveRuntimeControlBundleBroken) as error:
            build_runtime_control_milestone_bundle(force_actor_mismatch=True)

        self.assertIn("not allowed", str(error.exception))


if __name__ == "__main__":
    unittest.main()
