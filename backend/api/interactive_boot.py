"""Helpers for serializing the initial interactive route boot payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .interactive_artifact_hash import build_artifact_hash_snapshot
from .interactive_identity import (
    InteractiveIdentityMismatch,
    InteractiveIdentityNotFound,
    InteractiveIdentityStale,
    resolve_runtime_identity_from_artifact_route,
)
from .interactive_replay import add_history_complete_marker, build_replay_event_snapshot
from .interactive_tail import build_interactive_tail_snapshot
from .session_artifacts import (
    build_interactive_session_capability,
    build_session_route,
)


class InteractiveBootPayloadUnavailable(RuntimeError):
    """Raised when the interactive boot payload cannot be produced honestly."""


def build_interactive_boot_payload(
    session: Dict[str, Any],
    artifact_path: str | Path,
) -> Dict[str, Any]:
    resolved_artifact_path = Path(artifact_path).expanduser().resolve()
    harness = str(session.get("agent_type") or session.get("provider") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    route = build_session_route(harness, str(resolved_artifact_path), session_id)
    artifact_snapshot = build_artifact_hash_snapshot(resolved_artifact_path)
    tail_snapshot = build_interactive_tail_snapshot(
        resolved_artifact_path,
        harness=harness,
    )
    replay_snapshot = add_history_complete_marker(
        build_replay_event_snapshot(resolved_artifact_path)
    )
    interactive_session = build_interactive_session_capability(session, route)
    runtime_identity: Dict[str, Any] | None = None

    if interactive_session["available"]:
        runtime_mapping = resolve_runtime_identity_from_artifact_route(
            harness=harness,
            artifact_route_id=route["id"],
            artifact_session_id=session_id,
        )
        runtime_identity = runtime_mapping["runtime"]
    else:
        try:
            runtime_mapping = resolve_runtime_identity_from_artifact_route(
                harness=harness,
                artifact_route_id=route["id"],
                artifact_session_id=session_id,
            )
        except (InteractiveIdentityNotFound, InteractiveIdentityMismatch, InteractiveIdentityStale):
            runtime_mapping = None

        if runtime_mapping is not None:
            runtime_identity = runtime_mapping["runtime"]

    return {
        "version": 1,
        "route": {
            "harness": route["harness"],
            "route_id": route["id"],
            "session_href": route["href"],
            "interactive_href": interactive_session["href"],
        },
        "session": {
            "session_id": session_id,
            "agent_name": str(session.get("agent_name") or ""),
            "cwd": str(session.get("cwd") or ""),
            "status": str(session.get("status") or ""),
            "resume_supported": bool(session.get("resume_supported")),
        },
        "interactive_session": interactive_session,
        "runtime_identity": runtime_identity,
        "artifact": artifact_snapshot,
        "tail": tail_snapshot,
        "replay": replay_snapshot,
    }
