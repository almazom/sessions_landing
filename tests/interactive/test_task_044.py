from __future__ import annotations

import unittest

from backend.api.interactive_artifact_hash import build_artifact_hash_snapshot
from tests.interactive.fixtures import codex_fixture_path
from tests.interactive.interactive_resilience_states import build_interactive_resilience_states_snapshot
from tests.interactive.interactive_route_integration import build_interactive_route_integration_snapshot
from tests.interactive.route_security_bundle import (
    InteractiveRouteSecurityMilestoneBundleBroken,
    build_route_security_milestone_bundle,
)


class Task044LocalFailureAndImmutabilityProofTests(unittest.TestCase):
    def test_green_local_failure_and_immutability_proof(self) -> None:
        before_hash = build_artifact_hash_snapshot(codex_fixture_path())
        bundle = build_route_security_milestone_bundle()
        after_hash = build_artifact_hash_snapshot(codex_fixture_path())
        resilience_snapshot = build_interactive_resilience_states_snapshot()

        self.assertEqual(bundle.ownership_status_code, 403)
        self.assertEqual(bundle.prompt_disposition, "enqueue")
        self.assertEqual(bundle.control_disposition, "dispatch_now")
        self.assertIn("interactive_lifecycle_phase_supervisor_ready_total", bundle.observability_counter_keys)
        self.assertEqual(before_hash["sha256"], after_hash["sha256"])
        self.assertEqual(before_hash["byte_size"], after_hash["byte_size"])
        self.assertIn("Session is busy", resilience_snapshot.state_markers)
        self.assertIn("Initialization failed", resilience_snapshot.shell_markers)

        blocked_snapshot = build_interactive_route_integration_snapshot(resume_supported=False)
        self.assertFalse(blocked_snapshot.available)
        self.assertEqual(blocked_snapshot.thread_id, "thread-fixture-codex-001")

    def test_red_local_failure_and_immutability_proof(self) -> None:
        with self.assertRaises(InteractiveRouteSecurityMilestoneBundleBroken):
            build_route_security_milestone_bundle(force_cross_origin=True)


if __name__ == "__main__":
    unittest.main()
