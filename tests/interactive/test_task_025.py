from __future__ import annotations

import unittest

from backend.api.interactive_handoff import build_replay_to_live_handoff
from backend.api.interactive_identity import resolve_runtime_identity_from_artifact_route
from backend.api.interactive_replay import (
    add_history_complete_marker,
    build_replay_event_snapshot,
)
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import build_operational_store_snapshot
from backend.api.interactive_supervisor import start_supervisor_resume_flow
from backend.api.session_artifacts import build_session_route
from tests.interactive.fixtures import codex_fixture_path


class Task025SupervisorStartResumeFlowTests(unittest.TestCase):
    @staticmethod
    def _supervisor(*, owner_id: str, lock_status: str) -> dict[str, str]:
        return {
            "owner_id": owner_id,
            "lease_id": "lease-fixture-001",
            "lock_status": lock_status,
            "heartbeat_at": "2026-03-13T12:11:10Z",
            "lock_expires_at": "2026-03-13T12:16:10Z",
        }

    @staticmethod
    def _context(
        *,
        runtime_status_name: str,
        lock_status: str,
        owner_id: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
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
        transport_state = (
            "reconnecting"
            if runtime_status_name == "reconnect"
            else "connected"
        )
        status_payload = build_interactive_runtime_status(
            thread_id=runtime_identity["runtime"]["thread_id"],
            session_id=runtime_identity["runtime"]["session_id"],
            raw_status={"type": "active", "active_flags": []},
            source=(
                "recovered"
                if runtime_status_name == "reconnect"
                else "live_notification"
            ),
            transport_state=transport_state,
            reconnect_reason=(
                "transport_drop"
                if runtime_status_name == "reconnect"
                else None
            ),
        )
        handoff = build_replay_to_live_handoff(
            replay_snapshot=add_history_complete_marker(
                build_replay_event_snapshot(artifact_path)
            ),
            runtime_identity=runtime_identity,
            runtime_status=status_payload,
        )
        store_snapshot = build_operational_store_snapshot(
            route=route,
            runtime_identity=runtime_identity["runtime"],
            runtime_status=status_payload,
            supervisor=Task025SupervisorStartResumeFlowTests._supervisor(
                owner_id=owner_id,
                lock_status=lock_status,
            ),
            updated_at="2026-03-13T12:11:10Z",
        )
        return handoff, store_snapshot["records"][0]

    def test_green_builds_supervisor_resume_plan(self) -> None:
        handoff, record = self._context(
            runtime_status_name="active",
            lock_status="released",
            owner_id="interactive-supervisor-001",
        )

        plan = start_supervisor_resume_flow(
            handoff=handoff,
            store_record=record,
            owner_id="interactive-supervisor-001",
            lease_id="lease-fixture-002",
            heartbeat_at="2026-03-13T12:12:10Z",
            lock_expires_at="2026-03-13T12:17:10Z",
        )

        self.assertEqual(plan["operation"], "resume")
        self.assertEqual(plan["phase"], "supervisor_ready")
        self.assertEqual(plan["supervisor"]["lock_status"], "claimed")
        self.assertEqual(plan["supervisor"]["lease_id"], "lease-fixture-002")
        self.assertEqual(
            plan["live_attach"]["attach_strategy"],
            "after_history_complete",
        )

    def test_red_rejects_supervisor_start_when_other_owner_holds_lock(self) -> None:
        handoff, record = self._context(
            runtime_status_name="active",
            lock_status="claimed",
            owner_id="interactive-supervisor-001",
        )

        with self.assertRaises(PermissionError):
            start_supervisor_resume_flow(
                handoff=handoff,
                store_record=record,
                owner_id="interactive-supervisor-002",
                lease_id="lease-fixture-999",
                heartbeat_at="2026-03-13T12:12:10Z",
                lock_expires_at="2026-03-13T12:17:10Z",
            )


if __name__ == "__main__":
    unittest.main()
