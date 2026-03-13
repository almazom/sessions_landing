from __future__ import annotations

from typing import Any

from backend.api.interactive_events import (
    build_tool_fallback_event,
    normalize_thread_event,
)


class InteractiveEventStreamContractBroken(RuntimeError):
    """Raised when the normalized event stream contract is broken."""


EXPECTED_ORDERED_KINDS = ["command", "tool_fallback", "agent_message"]


def _source_events(*, include_unknown_event: bool) -> list[dict[str, Any]]:
    events = [
        {
            "type": "item.completed",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "command": "pytest -q",
                "aggregated_output": "2 passed",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "tool-1",
                "type": "mcp_tool_call",
                "server": "custom",
                "tool": "weird_tool",
                "arguments": {"path": "/tmp/demo"},
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "msg-1",
                "type": "agent_message",
                "text": "Build succeeded.",
            },
        },
    ]
    if include_unknown_event:
        events.append(
            {
                "type": "item.completed",
                "item": {"id": "mystery-1", "type": "mystery_item"},
            }
        )
    return events


def build_event_stream_contract_snapshot(
    *,
    include_unknown_event: bool = False,
) -> dict[str, object]:
    try:
        normalized_events = [
            normalize_thread_event(event)
            for event in _source_events(include_unknown_event=include_unknown_event)
        ]
    except ValueError as error:
        raise InteractiveEventStreamContractBroken(str(error)) from error

    browser_events = []
    for event in normalized_events:
        if event["kind"] == "tool_call":
            browser_events.append(build_tool_fallback_event(event))
            continue
        browser_events.append(event)

    ordered_kinds = [str(event["kind"]) for event in browser_events]
    if ordered_kinds != EXPECTED_ORDERED_KINDS:
        raise InteractiveEventStreamContractBroken("normalized event order drifted")

    return {
        "event_count": len(browser_events),
        "ordered_kinds": ordered_kinds,
        "completed_count": sum(
            1 for event in browser_events if event["status"] == "completed"
        ),
        "has_fallback_event": any(event["kind"] == "tool_fallback" for event in browser_events),
    }
