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


def normalize_thread_event(event: Dict[str, Any]) -> Dict[str, Any]:
    event_type = str(event.get("type") or "")
    item = event.get("item")
    if event_type not in EVENT_STATUS_BY_TYPE:
        raise ValueError(
            f"interactive event normalization does not support event type: {event_type}"
        )
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
