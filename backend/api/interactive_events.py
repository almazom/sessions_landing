"""Helpers for normalizing Codex thread events into browser-friendly events."""

from __future__ import annotations

from typing import Any, Dict


ITEM_KIND_BY_TYPE = {
    "agent_message": "agent_message",
    "command_execution": "command",
    "file_change": "file_change",
    "mcp_tool_call": "tool_call",
    "web_search": "web_search",
    "todo_list": "todo_list",
    "reasoning": "reasoning",
    "error": "error",
}

EVENT_STATUS_BY_TYPE = {
    "item.started": "started",
    "item.updated": "updated",
    "item.completed": "completed",
    "thread.started": "started",
    "turn.started": "started",
    "turn.completed": "completed",
}


def _require_supported_item_type(item: Dict[str, Any]) -> str:
    item_type = str(item.get("type") or "")
    if item_type not in ITEM_KIND_BY_TYPE:
        raise ValueError(
            f"interactive event normalization does not support item type: {item_type}"
        )
    return item_type


def _normalize_todo_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    todo_items = item.get("items") or []
    completed_count = sum(1 for todo in todo_items if todo.get("completed"))
    return {
        "items": todo_items,
        "completed_count": completed_count,
        "total_count": len(todo_items),
    }


def _payload_for_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item_type = _require_supported_item_type(item)
    if item_type == "command_execution":
        return {
            "command": str(item.get("command") or ""),
            "aggregated_output": str(item.get("aggregated_output") or ""),
            "exit_code": item.get("exit_code"),
        }
    if item_type == "agent_message":
        return {"text": str(item.get("text") or "")}
    if item_type == "todo_list":
        return _normalize_todo_payload(item)
    if item_type == "file_change":
        return {
            "changes": item.get("changes") or [],
            "status": item.get("status"),
        }
    if item_type == "mcp_tool_call":
        return {
            "server": str(item.get("server") or ""),
            "tool": str(item.get("tool") or ""),
            "arguments": item.get("arguments"),
            "result": item.get("result"),
            "error": item.get("error"),
        }
    if item_type == "web_search":
        return {"query": str(item.get("query") or "")}
    if item_type == "reasoning":
        return {"text": str(item.get("text") or "")}
    if item_type == "error":
        return {"message": str(item.get("message") or "")}
    raise ValueError(
        f"interactive event normalization does not support item type: {item_type}"
    )


def _summary_for_item(item: Dict[str, Any]) -> str:
    item_type = _require_supported_item_type(item)
    if item_type == "command_execution":
        return str(item.get("command") or "")
    if item_type == "agent_message":
        return str(item.get("text") or "")
    if item_type == "todo_list":
        return f"todo items: {len(item.get('items') or [])}"
    if item_type == "file_change":
        return f"file changes: {len(item.get('changes') or [])}"
    if item_type == "mcp_tool_call":
        return str(item.get("tool") or "")
    if item_type == "web_search":
        return str(item.get("query") or "")
    if item_type == "reasoning":
        return str(item.get("text") or "")
    if item_type == "error":
        return str(item.get("message") or "")
    raise ValueError(
        f"interactive event normalization does not support item type: {item_type}"
    )


def normalize_thread_event(event: Any) -> Dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("interactive event normalization requires object payloads")

    event_type = str(event.get("type") or "")
    if event_type not in EVENT_STATUS_BY_TYPE:
        raise ValueError(
            f"interactive event normalization does not support event type: {event_type}"
        )

    if event_type == "thread.started":
        thread_id = str(event.get("thread_id") or "")
        return {
            "event_id": thread_id or "thread-started",
            "kind": "thread",
            "status": "started",
            "summary": "Thread started",
            "payload": {"thread_id": thread_id},
            "source_event_type": event_type,
        }

    if event_type == "turn.started":
        return {
            "event_id": "turn-started",
            "kind": "turn",
            "status": "started",
            "summary": "Turn started",
            "payload": {},
            "source_event_type": event_type,
        }

    if event_type == "turn.completed":
        usage = event.get("usage") or {}
        return {
            "event_id": "turn-completed",
            "kind": "turn",
            "status": "completed",
            "summary": "Turn completed",
            "payload": {"usage": usage},
            "source_event_type": event_type,
        }

    item = event.get("item")
    if not isinstance(item, dict):
        raise ValueError("interactive event normalization requires event item payload")

    item_type = _require_supported_item_type(item)
    kind = ITEM_KIND_BY_TYPE[item_type]

    payload = _payload_for_item(item)
    if item_type == "command_execution":
        status = str(item.get("status") or EVENT_STATUS_BY_TYPE[event_type])
    else:
        status = EVENT_STATUS_BY_TYPE[event_type]

    return {
        "event_id": str(item.get("id") or ""),
        "kind": kind,
        "status": status,
        "summary": _summary_for_item(item),
        "payload": payload,
        "source_event_type": event_type,
    }


def build_tool_fallback_event(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("kind") != "tool_call":
        raise ValueError(
            "interactive tool fallback requires a normalized tool_call event"
        )

    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("interactive tool fallback requires tool payload details")

    tool_name = str(payload.get("tool") or event.get("summary") or "unknown_tool")
    details = _tool_fallback_details(payload, tool_name=tool_name)
    return {
        "event_id": str(event.get("event_id") or ""),
        "kind": "tool_fallback",
        "status": str(event.get("status") or "updated"),
        "summary": f"Tool call: {tool_name}",
        "payload": {
            "display_mode": "fallback",
            "details": details,
        },
        "source_event_type": str(event.get("source_event_type") or ""),
    }


def _tool_fallback_details(
    payload: Dict[str, Any],
    *,
    tool_name: str,
) -> Dict[str, Any]:
    details = {
        "server": str(payload.get("server") or ""),
        "tool": tool_name,
        "arguments": payload.get("arguments"),
        "error": payload.get("error"),
        "result": payload.get("result"),
    }
    return details
