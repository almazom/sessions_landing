"""Parser for Gemini session logs.

Format: JSON array with sessionId, type, message fields
Location: ~/.gemini/tmp/{hash}/logs.json
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import (
    SessionParser, SessionSummary, SessionStatus, AgentType
)


class GeminiParser(SessionParser):
    """Parser for Gemini session logs."""

    AGENT_TYPE = AgentType.GEMINI
    WATCH_PATHS = ["~/.gemini/tmp"]

    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Gemini logs.json file."""
        events = []
        user_messages = []
        session_id = ""
        timestamp_start = None
        timestamp_end = None

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []

        if not logs:
            return self._empty_summary(file_path)

        for entry in logs:
            entry_type = entry.get("type", "")
            timestamp = entry.get("timestamp", "")
            session_id = entry.get("sessionId", session_id)

            if not timestamp_start:
                timestamp_start = timestamp
            timestamp_end = timestamp

            # Extract user message
            if entry_type == "user":
                message = entry.get("message", "")
                if isinstance(message, str):
                    self.collect_user_message(user_messages, message)

                events.append({
                    "type": "user_message",
                    "timestamp": timestamp,
                    "description": "User message",
                    "icon": "💬",
                })

            # Extract model response
            elif entry_type == "model" or entry_type == "assistant":
                events.append({
                    "type": "model_response",
                    "timestamp": timestamp,
                    "description": "Model response",
                    "icon": "🤖",
                })

        status = self._detect_status(events, timestamp_end)
        timeline = self.build_timeline(events)
        cwd = self._extract_cwd(file_path)
        user_summary = self.build_user_message_summary(user_messages)

        return SessionSummary(
            session_id=session_id or file_path.parent.name,
            agent_type=self.AGENT_TYPE,
            agent_name="Gemini",
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
            tool_calls=[],
            token_usage={},
            files_modified=[],
            git_branch=None,
            plan_steps=[],
            source_file=str(file_path),
        )

    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single line (Gemini uses JSON arrays, not JSONL)."""
        try:
            entry = json.loads(line)
            entry_type = entry.get("type", "")
            timestamp = entry.get("timestamp", "")

            if entry_type == "user":
                return {
                    "type": "user_message",
                    "timestamp": timestamp,
                    "text": entry.get("message", "")[:150],
                }
            elif entry_type in ("model", "assistant"):
                return {
                    "type": "model_response",
                    "timestamp": timestamp,
                }

            return None

        except json.JSONDecodeError:
            return None

    def _empty_summary(self, file_path: Path) -> SessionSummary:
        """Return empty summary for invalid files."""
        return SessionSummary(
            session_id=file_path.parent.name,
            agent_type=self.AGENT_TYPE,
            agent_name="Gemini",
            cwd=self._extract_cwd(file_path),
            timestamp_start="",
            timestamp_end=None,
            status=SessionStatus.UNKNOWN,
            user_intent="",
            timeline=[],
            tool_calls=[],
            token_usage={},
            files_modified=[],
            git_branch=None,
            plan_steps=[],
            source_file=str(file_path),
        )

    def _detect_status(self, events: List[Dict], last_timestamp: str) -> SessionStatus:
        """Detect session status."""
        if events:
            return SessionStatus.ACTIVE
        return SessionStatus.UNKNOWN

    def _extract_cwd(self, file_path: Path) -> str:
        """Extract working directory from file path."""
        # Gemini sessions are in ~/.gemini/tmp/{hash}/
        return f"~/.gemini/tmp/{file_path.parent.name}"
