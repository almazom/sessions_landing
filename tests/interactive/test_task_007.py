from __future__ import annotations

import unittest
from pathlib import Path

from tests.interactive.transport_probe import (
    InteractiveTransportProbeNotReady,
    run_transport_probe,
)


class Task007TransportProbeTests(unittest.TestCase):
    def test_green_reports_fixture_backed_transport_verdicts(self) -> None:
        probe = run_transport_probe()

        self.assertEqual(probe.session_id, "sess-fixture-codex-001")
        self.assertEqual(probe.primary_transport, "codex_app_server")
        self.assertEqual(set(probe.verdicts), {"codex_app_server", "codex_exec_jsonl", "codex_sdk_ts"})

        app_server = probe.verdicts["codex_app_server"]
        self.assertEqual(app_server.probe_support, "supported")
        self.assertFalse(app_server.direct_browser_transport)
        self.assertEqual(app_server.runtime_requirement, "live_app_server")
        self.assertIn("fixture identity", app_server.summary)

        raw_exec = probe.verdicts["codex_exec_jsonl"]
        self.assertEqual(raw_exec.probe_support, "supported")
        self.assertFalse(raw_exec.direct_browser_transport)
        self.assertEqual(raw_exec.runtime_requirement, "local_cli_process")
        self.assertIn("artifact + thread id", raw_exec.summary)

        sdk = probe.verdicts["codex_sdk_ts"]
        self.assertEqual(sdk.probe_support, "supported")
        self.assertFalse(sdk.direct_browser_transport)
        self.assertEqual(sdk.runtime_requirement, "node_wrapper_process")
        self.assertIn("Node sidecar", sdk.summary)

    def test_red_missing_fixture_fails_honestly(self) -> None:
        with self.assertRaises(InteractiveTransportProbeNotReady):
            run_transport_probe(artifact_path=Path("/tmp/interactive-task-check/missing-rollout.jsonl"))


if __name__ == "__main__":
    unittest.main()
