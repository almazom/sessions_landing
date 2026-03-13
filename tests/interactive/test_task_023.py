from __future__ import annotations

import unittest

from backend.api.interactive_store import (
    build_operational_store_snapshot,
    prune_operational_store_snapshot,
)


class Task023OperationalStoreGcTests(unittest.TestCase):
    @staticmethod
    def _record(*, route_id: str, status: str, lock_status: str) -> dict[str, object]:
        return build_operational_store_snapshot(
            route={"harness": "codex", "route_id": route_id},
            runtime_identity={
                "thread_id": f"thread-{route_id}",
                "session_id": f"session-{route_id}",
                "transport": "codex_exec_json",
                "source": "operational_live",
            },
            runtime_status={
                "version": 1,
                "thread_id": f"thread-{route_id}",
                "session_id": f"session-{route_id}",
                "status": status,
                "label": status.title(),
                "detail": f"{status} state",
                "source": "live_notification",
                "transport_state": "connected",
                "can_send_input": status == "idle",
                "can_resume_stream": status in {"idle", "reconnect"},
                "raw_status": {
                    "type": "idle" if status == "idle" else "active",
                    "active_flags": [],
                },
                "wait_reason": None,
                "reconnect_hint": None,
                "observed_at": "2026-03-13T11:56:20Z",
            },
            supervisor={
                "owner_id": f"owner-{route_id}",
                "lease_id": f"lease-{route_id}",
                "lock_status": lock_status,
                "heartbeat_at": "2026-03-13T11:56:20Z",
                "lock_expires_at": "2026-03-13T12:01:20Z",
            },
            updated_at="2026-03-13T11:56:20Z",
        )["records"][0]

    def test_green_prunes_stale_records_and_reports_gc_summary(self) -> None:
        snapshot = {
            "version": 1,
            "updated_at": "2026-03-13T11:56:20Z",
            "records": [
                self._record(route_id="active-route", status="active", lock_status="claimed"),
                self._record(route_id="expired-route", status="idle", lock_status="expired"),
                self._record(route_id="released-route", status="idle", lock_status="released"),
            ],
        }

        pruned = prune_operational_store_snapshot(snapshot)

        self.assertEqual(len(pruned["records"]), 1)
        self.assertEqual(pruned["records"][0]["route"]["route_id"], "active-route")
        self.assertEqual(
            pruned["gc_summary"],
            {
                "removed_route_ids": ["expired-route", "released-route"],
                "removed_count": 2,
                "kept_count": 1,
            },
        )

    def test_red_rejects_snapshot_without_records(self) -> None:
        with self.assertRaises(ValueError):
            prune_operational_store_snapshot(
                {
                    "version": 1,
                    "updated_at": "2026-03-13T11:56:20Z",
                    "records": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
