"""Session scanning and management service."""

import time
from threading import Lock
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from backend.api.logging_utils import get_logger, log_event
from backend.parsers import PARSER_REGISTRY
from backend.parsers.base import SessionStatus

logger = get_logger("agent_nexus.scanner")


@dataclass
class SessionStore:
    """In-memory session storage."""
    sessions: Dict[str, dict] = None
    
    def __post_init__(self):
        if self.sessions is None:
            self.sessions = {}
    
    def add(self, session_id: str, data: dict):
        """Add or update session."""
        self.sessions[session_id] = data
        
    def get(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def get_all(self) -> List[dict]:
        """Get all sessions."""
        return list(self.sessions.values())
    
    def get_by_status(self, status: SessionStatus) -> List[dict]:
        """Filter sessions by status."""
        return [s for s in self.sessions.values() if s.get("status") == status.value]
    
    def count(self) -> int:
        """Total session count."""
        return len(self.sessions)
    
    def metrics(self) -> dict:
        """Calculate aggregate metrics."""
        sessions = self.get_all()
        
        by_agent = {}
        by_status = {}
        total_tokens = 0
        
        for s in sessions:
            agent = s.get("agent_type", "unknown")
            status = s.get("status", "unknown")
            
            by_agent[agent] = by_agent.get(agent, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            total_tokens += s.get("token_usage", {}).get("total_tokens", 0)
        
        return {
            "total_sessions": len(sessions),
            "by_agent": by_agent,
            "by_status": by_status,
            "total_tokens": total_tokens,
            "last_updated": datetime.now().isoformat(),
        }


class SessionScanner:
    """Scan agent session directories and parse sessions."""
    
    # Watch paths for each agent type
    WATCH_PATHS = {
        "codex": "~/.codex/sessions",
        "kimi": "~/.kimi/sessions",
        "gemini": "~/.gemini/tmp",
        "qwen": "~/.qwen/projects",
        "claude": "~/.claude/projects",
        "pi": "~/.pi/agent/sessions",
    }
    
    def __init__(self, store: SessionStore):
        self.store = store
        self._scan_errors = []
        self._scan_lock = Lock()
        self._loaded_once = False
    
    def _scan_all_locked(self) -> int:
        """Scan all agent directories. Returns count of sessions found."""
        self._scan_errors = []
        total = 0
        started_at = time.perf_counter()

        log_event(logger, "info", "scanner.scan.started", agents=list(self.WATCH_PATHS.keys()))
        for agent_type, path_str in self.WATCH_PATHS.items():
            try:
                count = self._scan_agent(agent_type, Path(path_str).expanduser())
                total += count
            except Exception as e:
                self._scan_errors.append(f"{agent_type}: {e}")
                log_event(
                    logger,
                    "error",
                    "scanner.agent.failed",
                    agent_type=agent_type,
                    watch_path=Path(path_str).expanduser(),
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        log_event(
            logger,
            "info",
            "scanner.scan.completed",
            total_sessions=total,
            errors=len(self._scan_errors),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        self._loaded_once = True
        
        return total

    def ensure_loaded(self) -> int:
        """Load sessions once on demand without duplicate concurrent scans."""
        if self._loaded_once:
            return self.store.count()

        with self._scan_lock:
            if self._loaded_once:
                return self.store.count()
            return self._scan_all_locked()

    def scan_all(self) -> int:
        """Force a full scan, even after startup warmup."""
        with self._scan_lock:
            return self._scan_all_locked()

    @property
    def has_loaded_once(self) -> bool:
        return self._loaded_once
    
    def _scan_agent(self, agent_type: str, base_path: Path) -> int:
        """Scan a single agent's session directory."""
        if not base_path.exists():
            log_event(
                logger,
                "info",
                "scanner.agent.skipped_missing_path",
                agent_type=agent_type,
                watch_path=base_path,
            )
            return 0
        
        parser_cls = PARSER_REGISTRY.get(agent_type)
        if not parser_cls:
            log_event(
                logger,
                "warning",
                "scanner.agent.skipped_missing_parser",
                agent_type=agent_type,
                watch_path=base_path,
            )
            return 0
        
        parser = parser_cls()
        count = 0
        matched_files = 0
        parse_errors = 0
        first_error = ""
        
        # Find session files based on agent type
        if agent_type == "codex":
            # Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
            patterns = ["*/*/rollout-*.jsonl", "*/*/*/rollout-*.jsonl"]
        elif agent_type == "claude":
            # Claude: ~/.claude/projects/*/*.jsonl
            patterns = ["*/*.jsonl"]
        elif agent_type == "qwen":
            # Qwen: ~/.qwen/projects/*/chats/*.jsonl
            patterns = ["*/chats/*.jsonl", "*/*.jsonl"]
        elif agent_type == "kimi":
            # Kimi: ~/.kimi/sessions/*/*/context.jsonl
            patterns = ["*/*/context.jsonl"]
        elif agent_type == "gemini":
            # Gemini: ~/.gemini/tmp/*/logs.json
            patterns = ["*/logs.json"]
        elif agent_type == "pi":
            # Pi: ~/.pi/agent/sessions/*/*.jsonl
            patterns = ["*/*.jsonl"]
        else:
            patterns = ["*.jsonl"]
        
        for pattern in patterns:
            for session_file in base_path.glob(pattern):
                if session_file.name == "memory":
                    continue
                matched_files += 1
                try:
                    summary = parser.parse_file(session_file)
                    data = summary.to_dict()
                    self.store.add(summary.session_id, data)
                    count += 1
                except Exception as e:
                    parse_errors += 1
                    if not first_error:
                        first_error = f"{session_file}: {type(e).__name__}: {e}"

        log_event(
            logger,
            "info",
            "scanner.agent.completed",
            agent_type=agent_type,
            watch_path=base_path,
            matched_files=matched_files,
            parsed_sessions=count,
            parse_errors=parse_errors,
            first_error=first_error or None,
        )
        
        return count
    
    def get_errors(self) -> List[str]:
        """Get scan errors."""
        return self._scan_errors


# Global session store
session_store = SessionStore()
session_scanner = SessionScanner(session_store)
