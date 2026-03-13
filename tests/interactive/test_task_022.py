from __future__ import annotations

import unittest
from pathlib import Path

from backend.api.interactive_identity import resolve_runtime_identity_from_artifact_route
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import (
    build_operational_store_snapshot,
    load_operational_store_snapshot,
    save_operational_store_snapshot,
)
from backend.api.session_artifacts import build_session_route
from tests.interactive.fixtures import codex_fixture_path
from tests.interactive.operational_store_schema import (
    load_operational_store_schema,
    validate_operational_store_payload_against_schema,
)


class Task022CrashRecoveryStoreFlowTests(unittest.TestCase):
    @staticmethod
    def _snapshot() -> dict[str, object]:
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
        return build_operational_store_snapshot(
            route=route,
            runtime_identity=runtime_identity["runtime"],
            runtime_status=runtime_status,
            supervisor={
                "owner_id": "interactive-supervisor-001",
                "lease_id": "lease-fixture-001",
                "lock_status": "claimed",
                "heartbeat_at": "2026-03-13T11:50:40Z",
                "lock_expires_at": "2026-03-13T11:55:40Z",
            },
            updated_at="2026-03-13T11:50:40Z",
        )

    def test_green_persists_and_recovers_operational_store_snapshot(self) -> None:
        schema = load_operational_store_schema()
        snapshot_path = Path("tmp/interactive-task-check/operational-store.json")
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        save_operational_store_snapshot(snapshot_path, self._snapshot())
        recovered = load_operational_store_snapshot(snapshot_path)

        self.assertTrue(validate_operational_store_payload_against_schema(recovered, schema))
        self.assertEqual(
            recovered["records"][0]["supervisor"]["owner_id"],
            "interactive-supervisor-001",
        )
        self.assertEqual(recovered["records"][0]["runtime_status"]["status"], "active")

    def test_red_rejects_corrupted_store_snapshot(self) -> None:
        snapshot_path = Path("tmp/interactive-task-check/corrupted-operational-store.json")
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text("{not json}", encoding="utf-8")

        with self.assertRaises(ValueError):
            load_operational_store_snapshot(snapshot_path)


if __name__ == "__main__":
    unittest.main()
