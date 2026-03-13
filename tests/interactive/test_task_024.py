from __future__ import annotations

import unittest

from backend.api.interactive_store import (
    acquire_operational_store_lock,
    build_operational_store_snapshot,
    release_operational_store_lock,
)


class Task024OwnershipLockRulesTests(unittest.TestCase):
    @staticmethod
    def _route() -> dict[str, str]:
        return {
            "harness": "codex",
            "route_id": "rollout-interactive-fixture.jsonl",
        }

    @staticmethod
    def _record(*, owner_id: str, lease_id: str, lock_status: str) -> dict[str, object]:
        return build_operational_store_snapshot(
            route=Task024OwnershipLockRulesTests._route(),
            runtime_identity={
                "thread_id": "thread-fixture-codex-001",
                "session_id": "sess-fixture-codex-001",
                "transport": "codex_exec_json",
                "source": "operational_live",
            },
            runtime_status={
                "version": 1,
                "thread_id": "thread-fixture-codex-001",
                "session_id": "sess-fixture-codex-001",
                "status": "active",
                "label": "Active",
                "detail": "active state",
                "source": "live_notification",
                "transport_state": "connected",
                "can_send_input": False,
                "can_resume_stream": False,
                "raw_status": {"type": "active", "active_flags": []},
                "wait_reason": None,
                "reconnect_hint": None,
                "observed_at": "2026-03-13T12:05:10Z",
            },
            supervisor={
                "owner_id": owner_id,
                "lease_id": lease_id,
                "lock_status": lock_status,
                "heartbeat_at": "2026-03-13T12:05:10Z",
                "lock_expires_at": "2026-03-13T12:10:10Z",
            },
            updated_at="2026-03-13T12:05:10Z",
        )["records"][0]

    def test_green_enforces_single_owner_claim_and_owner_release(self) -> None:
        record = self._record(
            owner_id="interactive-supervisor-001",
            lease_id="lease-fixture-001",
            lock_status="released",
        )

        claimed = acquire_operational_store_lock(
            record,
            owner_id="interactive-supervisor-001",
            lease_id="lease-fixture-002",
            heartbeat_at="2026-03-13T12:06:10Z",
            lock_expires_at="2026-03-13T12:11:10Z",
        )
        self.assertEqual(claimed["supervisor"]["lock_status"], "claimed")
        self.assertEqual(claimed["supervisor"]["lease_id"], "lease-fixture-002")

        released = release_operational_store_lock(
            claimed,
            owner_id="interactive-supervisor-001",
            released_at="2026-03-13T12:07:10Z",
        )
        self.assertEqual(released["supervisor"]["lock_status"], "released")
        self.assertEqual(released["supervisor"]["heartbeat_at"], "2026-03-13T12:07:10Z")

    def test_red_rejects_claim_from_competing_owner(self) -> None:
        record = self._record(
            owner_id="interactive-supervisor-001",
            lease_id="lease-fixture-001",
            lock_status="claimed",
        )

        with self.assertRaises(PermissionError):
            acquire_operational_store_lock(
                record,
                owner_id="interactive-supervisor-002",
                lease_id="lease-fixture-999",
                heartbeat_at="2026-03-13T12:06:10Z",
                lock_expires_at="2026-03-13T12:11:10Z",
            )


if __name__ == "__main__":
    unittest.main()
