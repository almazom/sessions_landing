from __future__ import annotations

from dataclasses import dataclass

from backend.api.interactive_handoff import build_replay_to_live_handoff
from backend.api.interactive_identity import resolve_runtime_identity_from_artifact_route
from backend.api.interactive_replay import (
    add_history_complete_marker,
    build_replay_event_snapshot,
)
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import (
    build_operational_store_snapshot,
    prune_operational_store_snapshot,
)
from backend.api.interactive_tail import build_interactive_tail_snapshot
from backend.api.session_artifacts import build_session_route
from .fixtures import codex_fixture_path


class InteractiveReplayStoreBundleBroken(RuntimeError):
    """Raised when the replay/store milestone bundle is incomplete."""


@dataclass(frozen=True)
class InteractiveReplayStoreMilestoneBundle:
    tail_item_count: int
    replay_history_complete: bool
    history_boundary_event_id: str
    runtime_status: str
    handoff_phase: str
    store_record_count: int
    gc_removed_count: int


def _supervisor_payload(*, force_gc_release: bool) -> dict[str, str]:
    return {
        "owner_id": "interactive-supervisor-001",
        "lease_id": "lease-fixture-001",
        "lock_status": "released" if force_gc_release else "claimed",
        "heartbeat_at": "2026-03-13T12:01:10Z",
        "lock_expires_at": "2026-03-13T12:06:10Z",
    }


def build_replay_store_milestone_bundle(
    *,
    force_gc_release: bool = False,
) -> InteractiveReplayStoreMilestoneBundle:
    artifact_path = codex_fixture_path()
    route = build_session_route(
        "codex",
        str(artifact_path),
        "sess-fixture-codex-001",
    )

    try:
        tail_snapshot = build_interactive_tail_snapshot(artifact_path)
        replay_snapshot = add_history_complete_marker(
            build_replay_event_snapshot(artifact_path)
        )
        runtime_identity_mapping = resolve_runtime_identity_from_artifact_route(
            harness="codex",
            artifact_route_id=route["id"],
            artifact_session_id="sess-fixture-codex-001",
        )
        runtime_status = build_interactive_runtime_status(
            thread_id=runtime_identity_mapping["runtime"]["thread_id"],
            session_id=runtime_identity_mapping["runtime"]["session_id"],
            raw_status={"type": "active", "active_flags": []},
            source="live_notification",
            transport_state="connected",
        )
        handoff = build_replay_to_live_handoff(
            replay_snapshot=replay_snapshot,
            runtime_identity=runtime_identity_mapping,
            runtime_status=runtime_status,
        )
        store_snapshot = build_operational_store_snapshot(
            route=route,
            runtime_identity=runtime_identity_mapping["runtime"],
            runtime_status=runtime_status,
            supervisor=_supervisor_payload(force_gc_release=force_gc_release),
            updated_at="2026-03-13T12:01:10Z",
        )
        gc_snapshot = prune_operational_store_snapshot(store_snapshot)
    except (FileNotFoundError, LookupError, RuntimeError, ValueError) as error:
        raise InteractiveReplayStoreBundleBroken(str(error)) from error

    if not replay_snapshot["history_complete"]:
        raise InteractiveReplayStoreBundleBroken(
            "replay milestone is missing history_complete"
        )
    if not gc_snapshot["records"]:
        raise InteractiveReplayStoreBundleBroken("store GC removed all records")

    return InteractiveReplayStoreMilestoneBundle(
        tail_item_count=len(tail_snapshot["items"]),
        replay_history_complete=replay_snapshot["history_complete"],
        history_boundary_event_id=str(handoff["history_boundary_event_id"]),
        runtime_status=str(runtime_status["status"]),
        handoff_phase=str(handoff["phase"]),
        store_record_count=len(gc_snapshot["records"]),
        gc_removed_count=int(gc_snapshot["gc_summary"]["removed_count"]),
    )
