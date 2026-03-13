from __future__ import annotations

import unittest

from backend.api.interactive_boot import (
    InteractiveBootPayloadUnavailable,
    build_interactive_boot_payload,
)
from tests.interactive.boot_payload_schema import (
    load_boot_payload_schema,
    validate_boot_payload_against_schema,
)
from tests.interactive.fixtures import codex_fixture_path


class Task014BootPayloadSerializerTests(unittest.TestCase):
    @staticmethod
    def _session_payload(*, resume_supported: bool, status: str) -> dict[str, object]:
        return {
            "session_id": "sess-fixture-codex-001",
            "agent_type": "codex",
            "agent_name": "Codex",
            "cwd": "/home/pets/zoo/agents_sessions_dashboard",
            "status": status,
            "resume_supported": resume_supported,
        }

    def test_green_serializes_fixture_backed_boot_payload(self) -> None:
        payload = build_interactive_boot_payload(
            self._session_payload(resume_supported=True, status="active"),
            codex_fixture_path(),
        )

        schema = load_boot_payload_schema()
        self.assertTrue(validate_boot_payload_against_schema(payload, schema))
        self.assertEqual(payload["route"]["route_id"], "rollout-interactive-fixture.jsonl")
        self.assertEqual(payload["interactive_session"]["transport"], "codex_app_server")
        self.assertEqual(payload["runtime_identity"]["thread_id"], "thread-fixture-codex-001")
        self.assertEqual(
            payload["tail"],
            {
                "items": [],
                "summary_hint": None,
                "has_more_before": False,
            },
        )
        self.assertEqual(
            payload["replay"],
            {
                "items": [],
                "history_complete": False,
            },
        )

    def test_red_fails_honestly_when_interactive_mode_is_disabled(self) -> None:
        with self.assertRaises(InteractiveBootPayloadUnavailable) as error:
            build_interactive_boot_payload(
                self._session_payload(resume_supported=False, status="idle"),
                codex_fixture_path(),
            )

        self.assertIn("disabled", str(error.exception))


if __name__ == "__main__":
    unittest.main()
