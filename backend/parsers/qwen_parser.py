"""Parser for Qwen Code session logs.

Format: JSONL with sessionId, type, cwd, message, gitBranch
Location: ~/.qwen/projects/{path}/chats/{uuid}.jsonl
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import (
    SessionParser, SessionSummary, SessionStatus, AgentType
)


class QwenParser(SessionParser):
    """Parser for Qwen Code session logs."""

    AGENT_TYPE = AgentType.QWEN
    WATCH_PATHS = ["~/.qwen/projects"]

    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Qwen session JSONL file."""
        events = []
        user_messages = []
        tool_calls = []
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        timestamp_start = None
        timestamp_end = None
        session_id = file_path.stem  # UUID from filename
        cwd = ""
        git_branch = None
        model = ""

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type", "")
                    timestamp = entry.get("timestamp", "")

                    if not timestamp_start:
                        timestamp_start = timestamp
                    timestamp_end = timestamp

                    # Extract session info from first entry
                    if not cwd:
                        cwd = entry.get("cwd", "")
                    if not git_branch:
                        git_branch = entry.get("gitBranch")

                    # Extract user message
                    if entry_type == "user":
                        message = entry.get("message", {})
                        content = message.get("content", "")
                        if isinstance(content, str):
                            self.collect_user_message(user_messages, content)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    self.collect_user_message(user_messages, item.get("text", ""))
                                    break

                        events.append({
                            "type": "user_message",
                            "timestamp": timestamp,
                            "description": "User message",
                            "icon": "💬",
                        })

                    # Extract assistant response
                    elif entry_type == "assistant":
                        message = entry.get("message", {})
                        model = message.get("model", model)
                        parts = message.get("parts", [])

                        for part in parts:
                            # Thinking
                            if part.get("thought"):
                                events.append({
                                    "type": "thinking",
                                    "timestamp": timestamp,
                                    "description": "Thinking...",
                                    "icon": "🧠",
                                })
                            # Tool calls
                            elif "functionCall" in part:
                                func = part["functionCall"]
                                func_name = func.get("name", "")
                                if func_name:
                                    tool_calls.append(func_name)
                                    events.append({
                                        "type": "tool_call",
                                        "timestamp": timestamp,
                                        "description": f"Tool: {func_name}",
                                        "icon": self._get_tool_icon(func_name),
                                    })

                        # Token usage
                        usage = message.get("usageMetadata", {})
                        if usage:
                            token_usage["input_tokens"] += usage.get("promptTokenCount", 0)
                            token_usage["output_tokens"] += usage.get("candidatesTokenCount", 0)
                            token_usage["total_tokens"] += usage.get("totalTokenCount", 0)

                    # Extract tool results
                    elif entry_type == "tool_result":
                        message = entry.get("message", {})
                        parts = message.get("parts", [])
                        for part in parts:
                            if "functionResponse" in part:
                                events.append({
                                    "type": "tool_result",
                                    "timestamp": timestamp,
                                    "description": "Tool result received",
                                    "icon": "✅",
                                })

                    # System events with telemetry
                    elif entry_type == "system":
                        subtype = entry.get("subtype", "")
                        if subtype == "ui_telemetry":
                            payload = entry.get("systemPayload", {})
                            ui_event = payload.get("uiEvent", {})
                            event_name = ui_event.get("event.name", "")

                            if "tool_call" in event_name:
                                func_name = ui_event.get("function_name", "")
                                if func_name and func_name not in tool_calls:
                                    tool_calls.append(func_name)

                except json.JSONDecodeError:
                    continue

        status = self._detect_status(events, timestamp_end)
        timeline = self.build_timeline(events)
        user_summary = self.build_user_message_summary(user_messages)

        agent_name = f"Qwen ({model})" if model else "Qwen"

        return SessionSummary(
            session_id=session_id,
            agent_type=self.AGENT_TYPE,
            agent_name=agent_name,
            cwd=cwd,
            timestamp_start=timestamp_start or "",
            timestamp_end=timestamp_end,
            status=status,
            user_intent=user_summary["user_intent"],
            first_user_message=user_summary["first_user_message"],
            last_user_message=user_summary["last_user_message"],
            user_messages=user_summary["user_messages"],
            user_message_count=user_summary["user_message_count"],
            intent_evolution=user_summary["intent_evolution"],
            timeline=timeline,
            tool_calls=list(set(tool_calls)),
            token_usage=token_usage,
            files_modified=[],
            git_branch=git_branch,
            plan_steps=[],
            source_file=str(file_path),
        )

    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single JSONL line for incremental updates."""
        try:
            entry = json.loads(line)
            entry_type = entry.get("type", "")
            timestamp = entry.get("timestamp", "")

            if entry_type == "user":
                message = entry.get("message", {})
                content = message.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content[:150]
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")[:150]
                            break
                return {
                    "type": "user_message",
                    "timestamp": timestamp,
                    "text": text,
                }

            elif entry_type == "assistant":
                message = entry.get("message", {})
                parts = message.get("parts", [])
                for part in parts:
                    if "functionCall" in part:
                        return {
                            "type": "tool_call",
                            "timestamp": timestamp,
                            "function": part["functionCall"].get("name"),
                        }
                    if part.get("thought"):
                        return {
                            "type": "thinking",
                            "timestamp": timestamp,
                        }

            elif entry_type == "tool_result":
                return {
                    "type": "tool_result",
                    "timestamp": timestamp,
                }

            return None

        except json.JSONDecodeError:
            return None

    def _get_tool_icon(self, tool_name: str) -> str:
        """Get icon for tool type."""
        icons = {
            "read_file": "📖",
            "write_file": "💾",
            "edit_file": "📝",
            "shell": "🛠️",
            "search": "🔍",
            "list_directory": "📁",
        }
        return icons.get(tool_name, "🔧")

    def _detect_status(self, events: List[Dict], last_timestamp: str) -> SessionStatus:
        """Detect session status."""
        if events:
            return SessionStatus.ACTIVE
        return SessionStatus.UNKNOWN
