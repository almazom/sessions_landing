"""Pi session parser."""

import json
from pathlib import Path
from typing import Dict, Optional

from .base import SessionParser, SessionSummary, SessionStatus, AgentType


class PiParser(SessionParser):
    """Parser for Pi agent session files (~/.pi/agent/sessions/)."""
    
    AGENT_TYPE = AgentType.PI
    WATCH_PATHS = ["~/.pi/agent/sessions"]
    
    # Map provider names to display names
    PROVIDER_DISPLAY = {
        "zai": "ZhipuAI",
        "openai": "OpenAI", 
        "anthropic": "Anthropic",
        "google": "Google",
    }
    
    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a Pi session JSONL file."""
        # Extract cwd from parent directory name
        # Format: --home-pets--project-path--
        parent_dir = file_path.parent.name
        cwd = self._parse_cwd_from_dir(parent_dir)
        
        # Parse session ID from filename
        # Format: 2026-02-21T13-23-06-771Z_d97a71af-....jsonl
        session_id = self._extract_session_id(file_path.name)
        
        events = []
        user_messages = []
        tool_calls = []
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        current_model = ""
        current_provider = ""
        timestamp_start = ""
        timestamp_end = None
        status = SessionStatus.ACTIVE
        error_message = None
        files_modified = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                    
                entry_type = entry.get("type", "")
                entry_timestamp = entry.get("timestamp", "")
                if entry_timestamp:
                    timestamp_end = entry_timestamp

                # Session start
                if entry_type == "session":
                    timestamp_start = entry_timestamp
                    if not session_id:
                        session_id = entry.get("id", "unknown")
                        
                # Model change
                elif entry_type == "model_change":
                    current_provider = entry.get("provider", "")
                    current_model = entry.get("modelId", "")
                    
                # Messages
                elif entry_type == "message":
                    msg = entry.get("message", {})
                    role = msg.get("role", "")
                    
                    if role == "user":
                        # Extract first user intent
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    self.collect_user_message(user_messages, item.get("text", ""))
                                    break
                        elif isinstance(content, str):
                            self.collect_user_message(user_messages, content)
                                
                        events.append({
                            "type": "user_message",
                            "timestamp": entry.get("timestamp", ""),
                            "description": "User message"
                        })
                        
                    elif role == "assistant":
                        # Extract tool calls and token usage
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    if item.get("type") == "toolCall":
                                        tool_name = item.get("name", "unknown")
                                        tool_calls.append(tool_name)
                                        events.append({
                                            "type": "tool_call",
                                            "timestamp": entry.get("timestamp", ""),
                                            "description": f"Tool: {tool_name}",
                                            "icon": "🔧"
                                        })
                                        
                        # Token usage
                        usage = msg.get("usage", {})
                        if usage:
                            token_usage["input_tokens"] += usage.get("input", 0)
                            token_usage["output_tokens"] += usage.get("output", 0)
                            token_usage["total_tokens"] += usage.get("totalTokens", 0)
                            
                        # Check for errors
                        if msg.get("errorMessage"):
                            error_message = msg.get("errorMessage")
                            status = SessionStatus.ERROR
                            
                        # Check stop reason
                        stop_reason = msg.get("stopReason", "")
                        if stop_reason == "endTurn":
                            timestamp_end = entry_timestamp
                            
                    elif role == "toolResult":
                        tool_name = msg.get("toolName", "")
                        content = msg.get("content", [])
                        
                        # Track file modifications
                        if tool_name in ("write", "edit"):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    text = item.get("text", "")
                                    # Look for file paths in the response
                                    if "path" in text.lower():
                                        events.append({
                                            "type": "file_modified",
                                            "timestamp": entry.get("timestamp", ""),
                                            "description": "Modified file",
                                            "icon": "📝"
                                        })
                                        
        # Determine final status
        if not timestamp_end and not error_message:
            status = SessionStatus.ACTIVE
        elif error_message:
            status = SessionStatus.ERROR
        else:
            status = SessionStatus.COMPLETED
            
        # Build agent name with model
        agent_name = self._build_agent_name(current_provider, current_model)
        
        # Build timeline
        timeline = self.build_timeline(events)
        user_summary = self.build_user_message_summary(user_messages)

        return SessionSummary(
            session_id=session_id,
            agent_type=AgentType.PI,
            agent_name=agent_name,
            cwd=cwd,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            status=status,
            user_intent=user_summary["user_intent"],
            first_user_message=user_summary["first_user_message"],
            last_user_message=user_summary["last_user_message"],
            user_messages=user_summary["user_messages"],
            user_message_count=user_summary["user_message_count"],
            intent_evolution=user_summary["intent_evolution"],
            timeline=timeline,
            tool_calls=tool_calls,
            token_usage=token_usage,
            files_modified=files_modified,
            source_file=str(file_path),
            error_message=error_message
        )
    
    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single JSONL line."""
        try:
            entry = json.loads(line)
            return entry
        except json.JSONDecodeError:
            return None
            
    def _parse_cwd_from_dir(self, dir_name: str) -> str:
        """Parse cwd from session directory name.
        
        Format: --home-pets--project-path--
        Returns: /home/pets/project/path
        """
        # Remove leading/trailing double dashes
        clean = dir_name.strip("-")
        
        # The pattern is: home-pets-PROJECT-PATH with segments separated by single dashes
        # But we need to detect where "home-pets" ends and project path begins
        
        # Common approach: split and reconstruct
        # home-pets- typically becomes /home/pets/
        if clean.startswith("home-pets"):
            # Remove "home-pets" prefix
            rest = clean[10:]  # len("home-pets") = 10, but with - it's 10
            if rest.startswith("-"):
                rest = rest[1:]
            # Now convert remaining dashes to slashes for path segments
            # But be careful - some dashes are part of the actual path
            # We'll convert - to / and let the path be readable
            return f"/home/pets/{rest.replace('-', '/')}"
        
        # Fallback: just convert all double-dashes to slashes
        return "/" + clean.replace("--", "/")
        
    def _extract_session_id(self, filename: str) -> str:
        """Extract session ID from filename.
        
        Format: 2026-02-21T13-23-06-771Z_d97a71af-....jsonl
        """
        if ".jsonl" in filename:
            filename = filename.replace(".jsonl", "")
        # Take the UUID part after the timestamp
        if "_" in filename:
            parts = filename.split("_")
            if len(parts) >= 2:
                return parts[1]
        return filename
        
    def _build_agent_name(self, provider: str, model: str) -> str:
        """Build display name for agent.
        
        Examples:
        - Pi (glm-5)
        - Pi (ZhipuAI/glm-4.5-air)
        """
        if model:
            # Check if it's a non-default model
            display_model = model
            if provider and provider != "pi":
                provider_display = self.PROVIDER_DISPLAY.get(provider, provider)
                return f"Pi ({provider_display}/{model})"
            return f"Pi ({model})"
        return "Pi"
