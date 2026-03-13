from __future__ import annotations

from dataclasses import dataclass

from backend.api.interactive_actions import (
    build_cancel_interrupt_action,
    build_prompt_submit_action,
    build_waiting_response_action,
    validate_inbound_action,
)
from backend.api.interactive_handoff import build_replay_to_live_handoff
from backend.api.interactive_identity import resolve_runtime_identity_from_artifact_route
from backend.api.interactive_replay import (
    add_history_complete_marker,
    build_replay_event_snapshot,
)
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_store import build_operational_store_snapshot
from backend.api.interactive_supervisor import (
    start_supervisor_resume_flow,
    stop_supervisor_flow,
)
from backend.api.session_artifacts import build_session_route
from .event_stream_contract import (
    InteractiveEventStreamContractBroken,
    build_event_stream_contract_snapshot,
)
from .fixtures import codex_fixture_path


class InteractiveRuntimeControlBundleBroken(RuntimeError):
    """Raised when the supervisor/control milestone bundle is incomplete."""


@dataclass(frozen=True)
class InteractiveRuntimeControlMilestoneBundle:
    start_operation: str
    stop_operation: str
    claimed_lock_status: str
    released_lock_status: str
    event_kinds: tuple[str, ...]
    validated_action_types: tuple[str, ...]


def _released_supervisor() -> dict[str, str]:
    return {
        "owner_id": "interactive-supervisor-001",
        "lease_id": "lease-fixture-001",
        "lock_status": "released",
        "heartbeat_at": "2026-03-13T12:40:20Z",
        "lock_expires_at": "2026-03-13T12:45:20Z",
    }


def build_runtime_control_milestone_bundle(
    *,
    force_actor_mismatch: bool = False,
    include_unknown_event: bool = False,
) -> InteractiveRuntimeControlMilestoneBundle:
    artifact_path = codex_fixture_path()
    route = build_session_route(
        "codex",
        str(artifact_path),
        "sess-fixture-codex-001",
    )

    try:
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
        replay_snapshot = add_history_complete_marker(
            build_replay_event_snapshot(artifact_path)
        )
        handoff = build_replay_to_live_handoff(
            replay_snapshot=replay_snapshot,
            runtime_identity=runtime_identity,
            runtime_status=runtime_status,
        )
        store_snapshot = build_operational_store_snapshot(
            route=route,
            runtime_identity=runtime_identity["runtime"],
            runtime_status=runtime_status,
            supervisor=_released_supervisor(),
            updated_at="2026-03-13T12:40:20Z",
        )
        started_plan = start_supervisor_resume_flow(
            handoff=handoff,
            store_record=store_snapshot["records"][0],
            owner_id="interactive-supervisor-001",
            lease_id="lease-fixture-002",
            heartbeat_at="2026-03-13T12:41:20Z",
            lock_expires_at="2026-03-13T12:46:20Z",
        )
        stopped_plan = stop_supervisor_flow(
            started_plan,
            owner_id="interactive-supervisor-001",
            stopped_at="2026-03-13T12:42:20Z",
            reason="cancelled_by_user",
        )
        event_snapshot = build_event_stream_contract_snapshot(
            include_unknown_event=include_unknown_event
        )
        authenticated_actor_id = (
            "interactive-supervisor-999"
            if force_actor_mismatch
            else "interactive-supervisor-001"
        )
        validated_actions = [
            validate_inbound_action(
                action=build_prompt_submit_action(
                    thread_id=runtime_identity["runtime"]["thread_id"],
                    supervisor_owner_id="interactive-supervisor-001",
                    text="Continue from the browser.",
                    client_event_id="browser-event-020",
                ),
                authenticated_actor_id=authenticated_actor_id,
                expected_thread_id=runtime_identity["runtime"]["thread_id"],
                expected_supervisor_owner_id="interactive-supervisor-001",
            ),
            validate_inbound_action(
                action=build_cancel_interrupt_action(
                    thread_id=runtime_identity["runtime"]["thread_id"],
                    supervisor_owner_id="interactive-supervisor-001",
                    mode="cancel",
                    client_event_id="browser-event-021",
                ),
                authenticated_actor_id=authenticated_actor_id,
                expected_thread_id=runtime_identity["runtime"]["thread_id"],
                expected_supervisor_owner_id="interactive-supervisor-001",
            ),
            validate_inbound_action(
                action=build_waiting_response_action(
                    thread_id=runtime_identity["runtime"]["thread_id"],
                    supervisor_owner_id="interactive-supervisor-001",
                    wait_reason="approval",
                    response="approve",
                    client_event_id="browser-event-022",
                ),
                authenticated_actor_id=authenticated_actor_id,
                expected_thread_id=runtime_identity["runtime"]["thread_id"],
                expected_supervisor_owner_id="interactive-supervisor-001",
            ),
        ]
    except (
        FileNotFoundError,
        LookupError,
        PermissionError,
        RuntimeError,
        ValueError,
        InteractiveEventStreamContractBroken,
    ) as error:
        raise InteractiveRuntimeControlBundleBroken(str(error)) from error

    if started_plan["supervisor"]["lock_status"] != "claimed":
        raise InteractiveRuntimeControlBundleBroken(
            "supervisor lifecycle never claimed the lock"
        )
    if stopped_plan["supervisor"]["lock_status"] != "released":
        raise InteractiveRuntimeControlBundleBroken(
            "supervisor lifecycle never released the lock"
        )

    return InteractiveRuntimeControlMilestoneBundle(
        start_operation=str(started_plan["operation"]),
        stop_operation=str(stopped_plan["operation"]),
        claimed_lock_status=str(started_plan["supervisor"]["lock_status"]),
        released_lock_status=str(stopped_plan["supervisor"]["lock_status"]),
        event_kinds=tuple(event_snapshot["ordered_kinds"]),
        validated_action_types=tuple(
            str(action["action_type"]) for action in validated_actions
        ),
    )
