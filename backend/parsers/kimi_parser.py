"""Parser for Kimi session logs.

Format: JSONL with roles: user, assistant, _checkpoint, tool, _usage
Location: ~/.kimi/sessions/{hash}/{uuid}/context.jsonl
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import (
    SessionParser, SessionSummary, SessionStatus, AgentType
)


class KimiParser(SessionParser):
    """Parser for Kimi session logs."""

    AGENT_TYPE = AgentType.KIMI
    WATCH_PATHS = ["~/.kimi/sessions"]

    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Kimi context.jsonl file."""
        events = []
        user_messages = []
        tool_calls = []
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        timestamp_start = None
        timestamp_end = None
        session_id = file_path.parent.name  # UUID from parent folder

        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    content = entry.get("content", "")

                    # Skip checkpoints and usage entries for main content
                    if role == "_checkpoint":
                        continue

                    if role == "_usage":
                        token_count = entry.get("token_count", 0)
                        token_usage["total_tokens"] = token_count
                        continue

                    # Extract timestamp from first entry (if available)
                    if not timestamp_start and role == "user":
                        timestamp_start = entry.get("timestamp", "")

                    # Extract user intent from first user message
                    if role == "user":
                        if isinstance(content, str):
                            self.collect_user_message(user_messages, content)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    self.collect_user_message(user_messages, item.get("text", ""))
                                    break

                    # Extract assistant actions
                    if role == "assistant":
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    # Tool calls
                                    if "tool_calls" in item:
                                        for tool in item["tool_calls"]:
                                            func_name = tool.get("function", {}).get("name", "")
                                            if func_name:
                                                tool_calls.append(func_name)
                                                events.append({
                                                    "type": "tool_call",
                                                    "timestamp": "",
                                                    "description": f"Tool: {func_name}",
                                                    "icon": self._get_tool_icon(func_name),
                                                })
                                    # Thinking
                                    if item.get("type") == "think":
                                        events.append({
                                            "type": "thinking",
                                            "timestamp": "",
                                            "description": "Thinking...",
                                            "icon": "🧠",
                                        })

                    timestamp_end = entry.get("timestamp", timestamp_end)

                except json.JSONDecodeError:
                    continue

        # Determine status
        status = self._detect_status(events, timestamp_end)

        # Build timeline
        timeline = self.build_timeline(events)
        user_summary = self.build_user_message_summary(user_messages)

        # Extract cwd from path or content
        cwd = self._extract_cwd(file_path)

        return SessionSummary(
            session_id=session_id,
            agent_type=self.AGENT_TYPE,
            agent_name="Kimi",
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
            git_branch=None,
            plan_steps=[],
            source_file=str(file_path),
        )

    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single JSONL line for incremental updates."""
        try:
            entry = json.loads(line)
            role = entry.get("role", "")
            content = entry.get("content", "")

            if role == "user":
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
                    "timestamp": entry.get("timestamp", ""),
                    "text": text,
                }

            elif role == "assistant":
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "think":
                                return {
                                    "type": "thinking",
                                    "timestamp": "",
                                }
                            if "tool_calls" in item:
                                for tool in item["tool_calls"]:
                                    return {
                                        "type": "tool_call",
                                        "timestamp": "",
                                        "function": tool.get("function", {}).get("name"),
                                    }

            elif role == "_usage":
                return {
                    "type": "token_count",
                    "timestamp": "",
                    "tokens": entry.get("token_count", 0),
                }

            return None

        except json.JSONDecodeError:
            return None

    def _get_tool_icon(self, tool_name: str) -> str:
        """Get icon for tool type."""
        icons = {
            "Shell": "🛠️",
            "Read": "📖",
            "Write": "💾",
            "Edit": "📝",
            "Search": "🔍",
        }
        return icons.get(tool_name, "🔧")

    def _detect_status(self, events: List[Dict], last_timestamp: str) -> SessionStatus:
        """Detect session status."""
        # Kimi doesn't have explicit completion markers
        # Check if there are recent events
        if events:
            return SessionStatus.ACTIVE
        return SessionStatus.UNKNOWN

    def _extract_cwd(self, file_path: Path) -> str:
        """Extract working directory from file path or session."""
        # Try to extract from the hash directory name
        # Kimi sessions are in ~/.kimi/sessions/{hash}/{uuid}/context.jsonl
        return f"~/.kimi/sessions/{file_path.parent.parent.name}"
