"""Helpers for extracting a small honest tail snapshot from a session artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from backend.parsers import PARSER_REGISTRY

from .interactive_identity import (
    InteractiveIdentityMismatch,
    InteractiveIdentityNotFound,
    InteractiveIdentityStale,
    resolve_runtime_identity_from_artifact_route,
)
from .session_artifacts import build_session_route


def _summary_hint(tool_calls: List[str], status: str) -> str:
    observed_tools = ", ".join(sorted(tool_calls)) if tool_calls else "no tools"
    return f"Observed tools: {observed_tools}. Session status: {status}."


def build_interactive_tail_snapshot(
    artifact_path: str | Path,
    *,
    harness: str = "codex",
    tail_item_limit: int = 3,
) -> Dict[str, Any]:
    parser_cls = PARSER_REGISTRY.get(harness)
    if parser_cls is None:
        raise ValueError(f"interactive tail snapshot does not support harness: {harness}")

    resolved_artifact_path = Path(artifact_path).expanduser().resolve()
    summary = parser_cls().parse_file(resolved_artifact_path)
    route = build_session_route(harness, str(resolved_artifact_path), summary.session_id)
    try:
        runtime_mapping = resolve_runtime_identity_from_artifact_route(
            harness=harness,
            artifact_route_id=route["id"],
            artifact_session_id=summary.session_id,
        )
    except (
        InteractiveIdentityNotFound,
        InteractiveIdentityMismatch,
        InteractiveIdentityStale,
        LookupError,
    ):
        runtime_mapping = None

    items: List[Dict[str, Any]] = []
    if summary.last_user_message:
        items.append(
            {
                "kind": "message",
                "role": "user",
                "text": summary.last_user_message,
                "timestamp": summary.timestamp_start,
            }
        )

    if summary.timeline:
        latest_event = summary.timeline[-1]
        items.append(
            {
                "kind": "status_hint",
                "role": None,
                "text": f"Latest observed event: {latest_event.event_type}.",
                "timestamp": latest_event.timestamp,
            }
        )

    items.append(
        {
            "kind": "identity_hint",
            "role": None,
            "text": (
                f"Session {summary.session_id} maps to thread "
                f"{runtime_mapping['runtime']['thread_id']}."
                if runtime_mapping is not None
                else (
                    f"Session {summary.session_id} has no live runtime mapping yet; "
                    "interactive continuation stays blocked until resume support is wired."
                )
            ),
            "timestamp": summary.timestamp_end,
        }
    )

    total_signal_count = (
        max(summary.user_message_count, 0)
        + len(summary.tool_calls)
        + len(summary.timeline)
    )
    selected_items = items[-tail_item_limit:]

    return {
        "items": selected_items,
        "summary_hint": _summary_hint(summary.tool_calls, summary.status.value),
        "has_more_before": total_signal_count > len(selected_items),
    }
