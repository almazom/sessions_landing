from __future__ import annotations

import unittest

from tests.interactive.replay_store_bundle import (
    InteractiveReplayStoreBundleBroken,
    build_replay_store_milestone_bundle,
)


class Task048ReplayStoreMilestoneReproductionTests(unittest.TestCase):
    def test_replay_store_bundle_green(self) -> None:
        bundle = build_replay_store_milestone_bundle()

        self.assertEqual(bundle.tail_item_count, 3)
        self.assertTrue(bundle.replay_history_complete)
        self.assertEqual(bundle.runtime_status, "active")
        self.assertEqual(bundle.handoff_phase, "live_attach_ready")
        self.assertEqual(bundle.store_record_count, 1)
        self.assertEqual(bundle.gc_removed_count, 0)
        self.assertIn("evt-0006", bundle.history_boundary_event_id)

    def test_replay_store_bundle_broken(self) -> None:
        with self.assertRaises(InteractiveReplayStoreBundleBroken) as error:
            build_replay_store_milestone_bundle(force_gc_release=True)

        self.assertIn("store GC removed all records", str(error.exception))


if __name__ == "__main__":
    unittest.main()
