"""Parser for Codex CLI session logs.

Format: JSONL with events like session_meta, response_item, event_msg, function_call
Location: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base import (
    SessionParser, SessionSummary, SessionStatus, AgentType
)


class CodexParser(SessionParser):
    """Parser for Codex CLI session logs."""

    AGENT_TYPE = AgentType.CODEX
    WATCH_PATHS = ["~/.codex/sessions"]

    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Codex session JSONL file."""
        events = []
        session_meta = {}
        user_messages = []
        tool_calls = []
        files_modified = []
        plan_steps = []
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        timestamp_start = None
        timestamp_end = None
        git_branch = None
        cwd = ""
        agent_nickname = "Codex"
        agent_role = ""

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    event_type = event.get("type", "")
                    payload = event.get("payload", {})
                    timestamp = event.get("timestamp", "")

                    if not timestamp_start:
                        timestamp_start = timestamp
                    timestamp_end = timestamp

                    # Extract session metadata
                    if event_type == "session_meta":
                        session_meta = payload
                        cwd = payload.get("cwd", "")
                        agent_nickname = payload.get("agent_nickname", "Codex")
                        agent_role = payload.get("agent_role", "")
                        git_info = payload.get("git", {})
                        git_branch = git_info.get("branch")

                    # Extract user message (intent)
                    elif event_type == "response_item":
                        if payload.get("type") == "message" and payload.get("role") == "user":
                            content = payload.get("content", [])
                            for item in content:
                                if item.get("type") == "input_text":
                                    text = item.get("text", "")
                                    self.collect_user_message(user_messages, text)

                    # Extract function calls (tool usage)
                    elif event_type == "response_item":
                        if payload.get("type") == "function_call":
                            func_name = payload.get("name", "")
                            if func_name:
                                tool_calls.append(func_name)
                                events.append({
                                    "type": "function_call",
                                    "timestamp": timestamp,
                                    "description": f"Tool: {func_name}",
                                    "icon": self._get_tool_icon(func_name),
                                })

                                # Track file modifications
                                if func_name == "apply_patch":
                                    args = json.loads(payload.get("arguments", "{}"))
                                    # Extract file from patch
                                    patch_content = args.get("command", [""])[0] if args.get("command") else ""
                                    if "*** Update File:" in patch_content:
                                        file_path_match = patch_content.split("*** Update File:")[1].split("\\")[0].strip()
                                        if file_path_match:
                                            files_modified.append(file_path_match)

                    # Extract token counts
                    elif event_type == "event_msg":
                        if payload.get("type") == "token_count":
                            info = payload.get("info") or {}
                            usage = info.get("total_token_usage") or {}
                            token_usage["input_tokens"] = usage.get("input_tokens", 0)
                            token_usage["output_tokens"] = usage.get("output_tokens", 0)
                            token_usage["total_tokens"] = usage.get("total_tokens", 0)

                        # Track user messages too
                        elif payload.get("type") == "user_message":
                            msg = payload.get("message", "")
                            self.collect_user_message(user_messages, msg)

                    # Extract plan updates
                    elif event_type == "response_item":
                        if payload.get("type") == "function_call" and payload.get("name") == "update_plan":
                            try:
                                args = json.loads(payload.get("arguments", "{}"))
                                plan = args.get("plan", [])
                                for step in plan:
                                    plan_steps.append({
                                        "step": step.get("step", ""),
                                        "status": step.get("status", "pending")
                                    })
                            except:
                                pass

                    # Detect completion
                    elif event_type == "event_msg":
                        if payload.get("type") == "task_complete":
                            events.append({
                                "type": "task_complete",
                                "timestamp": timestamp,
                                "description": "Session completed",
                                "icon": "✅",
                            })

                except json.JSONDecodeError:
                    continue

        # Determine status
        status = self._detect_status(events, timestamp_end)

        # Build timeline
        timeline = self.build_timeline(events)
        user_summary = self.build_user_message_summary(user_messages)

        return SessionSummary(
            session_id=session_meta.get("id", file_path.stem),
            agent_type=self.AGENT_TYPE,
            agent_name=f"Codex ({agent_nickname})" if agent_nickname != "Codex" else "Codex",
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
            plan_steps=plan_steps,
            source_file=str(file_path),
        )

    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single JSONL line for incremental updates."""
        try:
            event = json.loads(line)
            event_type = event.get("type", "")
            payload = event.get("payload", {})
            timestamp = event.get("timestamp", "")

            if event_type == "session_meta":
                return {
                    "type": "session_meta",
                    "timestamp": timestamp,
                    "session_id": payload.get("id"),
                    "cwd": payload.get("cwd"),
                    "agent_nickname": payload.get("agent_nickname"),
                }

            elif event_type == "response_item":
                if payload.get("type") == "function_call":
                    return {
                        "type": "function_call",
                        "timestamp": timestamp,
                        "function": payload.get("name"),
                        "icon": self._get_tool_icon(payload.get("name", "")),
                    }
                elif payload.get("type") == "message" and payload.get("role") == "user":
                    content = payload.get("content", [])
                    for item in content:
                        if item.get("type") == "input_text":
                            return {
                                "type": "user_message",
                                "timestamp": timestamp,
                                "text": item.get("text", "")[:150],
                            }

            elif event_type == "event_msg":
                if payload.get("type") == "token_count":
                    info = payload.get("info", {})
                    usage = info.get("total_token_usage", {})
                    return {
                        "type": "token_count",
                        "timestamp": timestamp,
                        "tokens": usage.get("total_tokens", 0),
                    }
                elif payload.get("type") == "task_complete":
                    return {
                        "type": "task_complete",
                        "timestamp": timestamp,
                    }

            return None

        except json.JSONDecodeError:
            return None

    def _get_tool_icon(self, tool_name: str) -> str:
        """Get icon for tool type."""
        icons = {
            "exec_command": "🛠️",
            "apply_patch": "📝",
            "read_file": "📖",
            "write_file": "💾",
            "update_plan": "📋",
            "search": "🔍",
            "view_image": "🖼️",
            "js_repl": "⚡",
        }
        return icons.get(tool_name, "🔧")

    def _detect_status(self, events: List[Dict], last_timestamp: str) -> SessionStatus:
        """Detect session status from events."""
        for event in reversed(events):
            if event.get("type") == "task_complete":
                return SessionStatus.COMPLETED
            if "error" in event.get("type", "").lower():
                return SessionStatus.ERROR

        # Check if session is recent (active within last 5 minutes)
        if last_timestamp:
            try:
                from datetime import datetime, timedelta
                last_time = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
                if datetime.now(last_time.tzinfo) - last_time < timedelta(minutes=5):
                    return SessionStatus.ACTIVE
            except:
                pass

        return SessionStatus.ACTIVE
