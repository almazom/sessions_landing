"""Helpers for extracting a compact replay event snapshot from a session artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _normalize_record(record: Dict[str, Any], event_index: int) -> Dict[str, Any] | None:
    record_type = record.get("type")
    payload = record.get("payload") or {}

    if record_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
        content = payload.get("content") or []
        text = ""
        for item in content:
            if item.get("type") == "input_text":
                text = str(item.get("text") or "")
                break
        if text:
            return {
                "event_id": f"evt-{event_index:04d}",
                "event_type": "user_message",
                "payload": {
                    "text": text,
                    "timestamp": record.get("timestamp"),
                },
            }

    if record_type == "response_item" and payload.get("type") == "function_call":
        return {
            "event_id": f"evt-{event_index:04d}",
            "event_type": "tool_call",
            "payload": {
                "tool_name": str(payload.get("name") or ""),
                "timestamp": record.get("timestamp"),
            },
        }

    if record_type == "event_msg" and payload.get("type") == "task_complete":
        return {
            "event_id": f"evt-{event_index:04d}",
            "event_type": "task_complete",
            "payload": {
                "status": "completed",
                "timestamp": record.get("timestamp"),
            },
        }

    return None


def build_replay_event_snapshot(
    artifact_path: str | Path,
    *,
    event_limit: int = 5,
) -> Dict[str, Any]:
    resolved_artifact_path = Path(artifact_path).expanduser().resolve()
    events: List[Dict[str, Any]] = []

    with resolved_artifact_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            normalized = _normalize_record(record, len(events) + 1)
            if normalized is not None:
                events.append(normalized)

    return {
        "items": events[:event_limit],
        "history_complete": False,
    }
