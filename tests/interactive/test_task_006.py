from __future__ import annotations

import unittest

from tests.interactive.transport_matrix import (
    InteractiveTransportMatrixReferenceNotFound,
    build_codex_transport_matrix,
)


class Task006CodexTransportMatrixTests(unittest.TestCase):
    def test_green_builds_codex_transport_matrix(self) -> None:
        matrix = build_codex_transport_matrix()

        self.assertEqual(matrix.primary_transport, "codex_app_server")
        self.assertEqual(set(matrix.entries), {"codex_app_server", "codex_exec_jsonl", "codex_sdk_ts"})

        app_server = matrix.entries["codex_app_server"]
        self.assertEqual(app_server.continuation_fit, "primary_backend_protocol")
        self.assertFalse(app_server.direct_browser_transport)
        self.assertTrue(app_server.supports_resume)
        self.assertTrue(app_server.supports_live_status)
        self.assertIn("typed channels", app_server.transport)

        raw_exec = matrix.entries["codex_exec_jsonl"]
        self.assertEqual(raw_exec.continuation_fit, "node_sidecar_stream")
        self.assertFalse(raw_exec.direct_browser_transport)
        self.assertTrue(raw_exec.supports_resume)
        self.assertFalse(raw_exec.supports_live_status)
        self.assertIn("stdin/stdout JSONL", raw_exec.transport)

        sdk = matrix.entries["codex_sdk_ts"]
        self.assertEqual(sdk.continuation_fit, "node_sidecar_wrapper")
        self.assertFalse(sdk.direct_browser_transport)
        self.assertTrue(sdk.supports_resume)
        self.assertFalse(sdk.supports_live_status)
        self.assertIn("wraps codex exec", sdk.role)

        self.assertEqual(matrix.kimi_reference.history_complete_method, "history_complete")
        self.assertEqual(matrix.kimi_reference.live_attach_transport, "websocket_replay_then_live")

    def test_red_missing_reference_input_fails_honestly(self) -> None:
        with self.assertRaises(InteractiveTransportMatrixReferenceNotFound):
            build_codex_transport_matrix(
                reference_overrides={
                    "local-codex-app-server-readme": "/tmp/interactive-task-check/missing-app-server-readme.md",
                }
            )


if __name__ == "__main__":
    unittest.main()
