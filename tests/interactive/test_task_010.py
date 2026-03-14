from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.api.interactive_identity import (
    InteractiveIdentityNotFound,
    resolve_runtime_identity_from_artifact_route,
)
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import (
    build_operational_store_snapshot,
    save_operational_store_snapshot,
)
from backend.api.session_artifacts import build_session_route
from tests.interactive.fixtures import codex_fixture_path


class Task010IdentityResolverHappyPathTests(unittest.TestCase):
    def test_green_resolves_runtime_identity_from_artifact_route(self) -> None:
        resolved = resolve_runtime_identity_from_artifact_route(
            harness="codex",
            artifact_route_id="rollout-interactive-fixture.jsonl",
        )

        self.assertEqual(resolved["artifact"]["harness"], "codex")
        self.assertEqual(resolved["artifact"]["route_id"], "rollout-interactive-fixture.jsonl")
        self.assertEqual(resolved["artifact"]["session_id"], "sess-fixture-codex-001")
        self.assertEqual(resolved["runtime"]["thread_id"], "thread-fixture-codex-001")
        self.assertEqual(resolved["runtime"]["transport"], "codex_exec_json")
        self.assertEqual(resolved["runtime"]["source"], "fixture")

    def test_red_missing_artifact_route_raises_not_found(self) -> None:
        with self.assertRaises(InteractiveIdentityNotFound):
            resolve_runtime_identity_from_artifact_route(
                harness="codex",
                artifact_route_id="missing-rollout.jsonl",
            )

    def test_green_prefers_operational_store_mapping_for_live_runtime(self) -> None:
        artifact_path = codex_fixture_path()
        route = build_session_route(
            "codex",
            str(artifact_path),
            "019ce72f-7e29-7150-8777-1462772b40fc",
        )
        runtime_status = build_interactive_runtime_status(
            thread_id="019ce72f-7e29-7150-8777-1462772b40fc",
            session_id="019ce72f-7e29-7150-8777-1462772b40fc",
            raw_status={"type": "notLoaded", "active_flags": []},
            source="boot",
            transport_state="reconnecting",
            reconnect_reason="resume_after_boot",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "operational-store.json"
            save_operational_store_snapshot(
                store_path,
                build_operational_store_snapshot(
                    route=route,
                    runtime_identity={
                        "thread_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "transport": "codex_app_server",
                        "source": "operational_live",
                    },
                    runtime_status=runtime_status,
                    supervisor={
                        "owner_id": "agent-nexus-resume",
                        "lease_id": "resume-019ce72f",
                        "lock_status": "claimed",
                        "heartbeat_at": "2026-03-14T08:00:00Z",
                        "lock_expires_at": "2026-03-14T08:05:00Z",
                    },
                    updated_at="2026-03-14T08:00:00Z",
                ),
            )

            resolved = resolve_runtime_identity_from_artifact_route(
                harness="codex",
                artifact_route_id=route["id"],
                artifact_session_id="019ce72f-7e29-7150-8777-1462772b40fc",
                operational_store_path=store_path,
            )

        self.assertEqual(resolved["runtime"]["thread_id"], "019ce72f-7e29-7150-8777-1462772b40fc")
        self.assertEqual(resolved["runtime"]["transport"], "codex_app_server")
        self.assertEqual(resolved["runtime"]["source"], "operational_live")


if __name__ == "__main__":
    unittest.main()
