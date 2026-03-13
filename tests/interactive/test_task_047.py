from __future__ import annotations

import unittest

from tests.interactive.transport_boot_bundle import (
    InteractiveTransportBootBundleBroken,
    build_transport_boot_milestone_bundle,
)


class Task047TransportBootMilestoneReproductionTests(unittest.TestCase):
    def test_transport_identity_boot_green(self) -> None:
        bundle = build_transport_boot_milestone_bundle()

        self.assertEqual(bundle.primary_transport, "codex_app_server")
        self.assertEqual(bundle.sdk_sidecar_status, "adopt_with_scope")
        self.assertEqual(bundle.boot_payload_transport, "codex_app_server")
        self.assertEqual(bundle.runtime_identity_transport, "codex_exec_json")
        self.assertTrue(bundle.runtime_identity_valid)
        self.assertTrue(bundle.boot_payload_valid)
        self.assertIn("codex_sdk_ts", bundle.transport_keys)
        self.assertTrue(bundle.sdk_rejects_browser_transport)

    def test_transport_identity_boot_broken(self) -> None:
        with self.assertRaises(InteractiveTransportBootBundleBroken) as error:
            build_transport_boot_milestone_bundle(
                reference_overrides={
                    "local-codex-sdk-readme": "/tmp/interactive-task-check/missing-codex-sdk-readme.md",
                }
            )

        self.assertIn("missing", str(error.exception))


if __name__ == "__main__":
    unittest.main()
