"""Helpers for serializing the initial interactive route boot payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .interactive_artifact_hash import build_artifact_hash_snapshot
from .interactive_identity import resolve_runtime_identity_from_artifact_route
from .session_artifacts import (
    build_interactive_session_capability,
    build_session_route,
)


class InteractiveBootPayloadUnavailable(RuntimeError):
    """Raised when the interactive boot payload cannot be produced honestly."""


def _build_tail_placeholder() -> Dict[str, Any]:
    return {
        "items": [],
        "summary_hint": None,
        "has_more_before": False,
    }


def _build_replay_placeholder() -> Dict[str, Any]:
    return {
        "items": [],
        "history_complete": False,
    }


def build_interactive_boot_payload(
    session: Dict[str, Any],
    artifact_path: str | Path,
) -> Dict[str, Any]:
    resolved_artifact_path = Path(artifact_path).expanduser().resolve()
    harness = str(session.get("agent_type") or session.get("provider") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    route = build_session_route(harness, str(resolved_artifact_path), session_id)
    interactive_session = build_interactive_session_capability(session, route)

    if not interactive_session["available"]:
        raise InteractiveBootPayloadUnavailable(interactive_session["detail"])

    runtime_mapping = resolve_runtime_identity_from_artifact_route(
        harness=harness,
        artifact_route_id=route["id"],
        artifact_session_id=session_id,
    )
    artifact_snapshot = build_artifact_hash_snapshot(resolved_artifact_path)

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
        "runtime_identity": runtime_mapping["runtime"],
        "artifact": artifact_snapshot,
        "tail": _build_tail_placeholder(),
        "replay": _build_replay_placeholder(),
    }
