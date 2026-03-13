from __future__ import annotations

import unittest

from backend.api.interactive_identity import resolve_runtime_identity_from_artifact_route
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import build_operational_store_snapshot
from backend.api.session_artifacts import build_session_route
from tests.interactive.fixtures import codex_fixture_path
from tests.interactive.operational_store_schema import (
    load_operational_store_sample,
    load_operational_store_schema,
    validate_operational_store_payload_against_schema,
)


class Task021OperationalStoreSchemaTests(unittest.TestCase):
    @staticmethod
    def _supervisor_payload(*, lock_status: str) -> dict[str, str]:
        return {
            "owner_id": "interactive-supervisor-001",
            "lease_id": "lease-fixture-001",
            "lock_status": lock_status,
            "heartbeat_at": "2026-03-13T11:44:00Z",
            "lock_expires_at": "2026-03-13T11:49:00Z",
        }

    @staticmethod
    def _runtime_context() -> tuple[dict[str, object], dict[str, object]]:
        artifact_path = codex_fixture_path()
        route = build_session_route(
            "codex",
            str(artifact_path),
            "sess-fixture-codex-001",
        )
        runtime_identity = resolve_runtime_identity_from_artifact_route(
            harness="codex",
            artifact_route_id=route["id"],
            artifact_session_id="sess-fixture-codex-001",
        )
        runtime_status = build_interactive_runtime_status(
            thread_id=runtime_identity["runtime"]["thread_id"],
            session_id=runtime_identity["runtime"]["session_id"],
            raw_status={"type": "active", "active_flags": []},
            source="live_notification",
            transport_state="connected",
        )
        return route, {
            "runtime_identity": runtime_identity["runtime"],
            "runtime_status": runtime_status,
        }

    def test_green_defines_operational_store_schema_for_runtime_state(self) -> None:
        schema = load_operational_store_schema()
        sample = load_operational_store_sample()
        self.assertTrue(validate_operational_store_payload_against_schema(sample, schema))

        route, runtime_context = self._runtime_context()
        payload = build_operational_store_snapshot(
            route=route,
            runtime_identity=runtime_context["runtime_identity"],
            runtime_status=runtime_context["runtime_status"],
            supervisor=self._supervisor_payload(lock_status="claimed"),
            updated_at="2026-03-13T11:44:00Z",
        )

        self.assertTrue(validate_operational_store_payload_against_schema(payload, schema))
        self.assertEqual(
            payload["records"][0]["route"]["route_id"],
            "rollout-interactive-fixture.jsonl",
        )
        self.assertEqual(payload["records"][0]["supervisor"]["lock_status"], "claimed")
        self.assertEqual(payload["records"][0]["runtime_status"]["status"], "active")

    def test_red_rejects_invalid_supervisor_lock_status(self) -> None:
        route, runtime_context = self._runtime_context()

        with self.assertRaises(ValueError):
            build_operational_store_snapshot(
                route=route,
                runtime_identity=runtime_context["runtime_identity"],
                runtime_status=runtime_context["runtime_status"],
                supervisor=self._supervisor_payload(lock_status="mystery"),
                updated_at="2026-03-13T11:44:00Z",
            )


if __name__ == "__main__":
    unittest.main()
