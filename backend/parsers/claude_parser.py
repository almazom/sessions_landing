"""Parser for Claude Code session logs.

Format: JSONL with type, message, sessionId, version, cwd
Location: ~/.claude/projects/{path}/{uuid}.jsonl
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import (
    SessionParser, SessionSummary, SessionStatus, AgentType
)


class ClaudeParser(SessionParser):
    """Parser for Claude Code session logs."""

    AGENT_TYPE = AgentType.CLAUDE
    WATCH_PATHS = ["~/.claude/projects"]

    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Claude session JSONL file."""
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
        files_modified = []

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

                    # Extract session info
                    if not cwd:
                        cwd = entry.get("cwd", "")
                    if not git_branch:
                        git_branch = entry.get("gitBranch")

                    # Skip file-history-snapshot entries
                    if entry_type == "file-history-snapshot":
                        continue

                    # Extract user message
                    if entry_type == "user":
                        message = entry.get("message", {})
                        content = message.get("content", "")

                        if isinstance(content, str):
                            if not content.startswith("<"):
                                self.collect_user_message(user_messages, content)

                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    if item.get("type") == "text":
                                        text = item.get("text", "")
                                        if text and not text.startswith("<"):
                                            self.collect_user_message(user_messages, text)
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
                        content = message.get("content", [])
                        stop_reason = message.get("stop_reason", "")

                        # Build agent name with model info
                        agent_name = f"Claude ({model})" if model else "Claude Code"

                        
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):                                    # Thinking
                                    if item.get("type") == "thinking":
                                        events.append({
                                            "type": "thinking",
                                            "timestamp": timestamp,
                                            "description": "Thinking...",
                                            "icon": "🧠",
                                        })
                                    # Text
                                    elif item.get("type") == "text":
                                        events.append({
                                            "type": "assistant_message",
                                            "timestamp": timestamp,
                                            "description": "Response",
                                            "icon": "🤖",
                                        })
                                    # Tool use
                                    elif item.get("type") == "tool_use":
                                        tool_name = item.get("name", "")
                                        if tool_name:
                                            tool_calls.append(tool_name)
                                            events.append({
                                                "type": "tool_use",
                                                "timestamp": timestamp,
                                                "description": f"Tool: {tool_name}",
                                                "icon": self._get_tool_icon(tool_name),
                                            })
                                            # Track file modifications
                                            if tool_name in ("write_file", "edit_file"):
                                                input_data = item.get("input", {})
                                                file_path = input_data.get("file_path", "")
                                                if file_path:
                                                    files_modified.append(file_path)

                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    # Thinking
                                    if item.get("type") == "thinking":
                                        events.append({
                                            "type": "thinking",
                                            "timestamp": timestamp,
                                            "description": "Thinking...",
                                            "icon": "🧠",
                                        })
                                    # Text
                                    elif item.get("type") == "text":
                                        events.append({
                                            "type": "assistant_message",
                                            "timestamp": timestamp,
                                            "description": "Response",
                                            "icon": "🤖",
                                        })
                                    # Tool use
                                    elif item.get("type") == "tool_use":
                                        tool_name = item.get("name", "")
                                        if tool_name:
                                            tool_calls.append(tool_name)
                                            events.append({
                                                "type": "tool_use",
                                                "timestamp": timestamp,
                                                "description": f"Tool: {tool_name}",
                                                "icon": self._get_tool_icon(tool_name),
                                            })
                                            # Track file modifications
                                            if tool_name in ("write_file", "edit_file"):
                                                input_data = item.get("input", {})
                                                file_path = input_data.get("file_path", "")
                                                if file_path:
                                                    files_modified.append(file_path)

                        # Token usage
                        usage = message.get("usage", {})
                        if usage:
                            token_usage["input_tokens"] += usage.get("input_tokens", 0)
                            token_usage["output_tokens"] += usage.get("output_tokens", 0)

                        # Check for end turn
                        if stop_reason == "end_turn":
                            events.append({
                                "type": "end_turn",
                                "timestamp": timestamp,
                                "description": "Turn complete",
                                "icon": "✅",
                            })

                    # Tool results
                    elif entry_type == "tool_result":
                        events.append({
                            "type": "tool_result",
                            "timestamp": timestamp,
                            "description": "Tool result",
                            "icon": "✅",
                        })

                except json.JSONDecodeError:
                    continue

        status = self._detect_status(events, timestamp_end)
        timeline = self.build_timeline(events)
        user_summary = self.build_user_message_summary(user_messages)

        agent_name = f"Claude ({model})" if model else "Claude Code"

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
            files_modified=list(set(files_modified)),
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
                    if not content.startswith("<"):
                        text = content[:150]
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            t = item.get("text", "")
                            if not t.startswith("<"):
                                text = t[:150]
                                break
                return {
                    "type": "user_message",
                    "timestamp": timestamp,
                    "text": text,
                }

            elif entry_type == "assistant":
                message = entry.get("message", {})
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "thinking":
                                return {
                                    "type": "thinking",
                                    "timestamp": timestamp,
                                }
                            if item.get("type") == "tool_use":
                                return {
                                    "type": "tool_use",
                                    "timestamp": timestamp,
                                    "function": item.get("name"),
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
            "bash": "🛠️",
            "grep": "🔍",
            "glob": "📁",
            "task": "📋",
            "web_search": "🌐",
            "web_fetch": "📥",
        }
        return icons.get(tool_name, "🔧")

    def _detect_status(self, events: List[Dict], last_timestamp: str) -> SessionStatus:
        """Detect session status."""
        if events:
            # Check for end_turn
            for event in reversed(events):
                if event.get("type") == "end_turn":
                    return SessionStatus.COMPLETED
            return SessionStatus.ACTIVE
        return SessionStatus.UNKNOWN
