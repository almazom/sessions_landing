"""Base parser class and common data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import re


INTENT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "if", "in", "into", "is", "it", "of", "on", "or", "so", "that",
    "the", "this", "to", "we", "with",
    "а", "без", "был", "бы", "в", "во", "вот", "все", "да", "для", "до",
    "его", "ее", "если", "же", "за", "и", "из", "или", "их", "к", "как",
    "когда", "ли", "мне", "мы", "на", "над", "не", "нет", "но", "о", "об",
    "он", "она", "они", "по", "под", "при", "про", "с", "со", "так", "то",
    "тут", "ты", "у", "уже", "что", "это", "я",
}


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"
    UNKNOWN = "unknown"


class AgentType(str, Enum):
    CODEX = "codex"
    KIMI = "kimi"
    GEMINI = "gemini"
    QWEN = "qwen"
    CLAUDE = "claude"
    PI = "pi"


@dataclass
class TimelineEvent:
    """Single event in session timeline."""
    timestamp: str
    event_type: str
    description: str
    icon: str = "📝"
    details: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SessionSummary:
    """Compressed session summary (~1KB target)."""
    session_id: str
    agent_type: AgentType
    agent_name: str
    cwd: str
    timestamp_start: str
    timestamp_end: Optional[str]
    status: SessionStatus
    user_intent: str  # Truncated first user message
    first_user_message: str = ""
    last_user_message: str = ""
    user_messages: List[str] = field(default_factory=list)
    user_message_count: int = 0
    intent_evolution: List[str] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    tool_calls: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    files_modified: List[str] = field(default_factory=list)
    git_branch: Optional[str] = None
    plan_steps: List[Dict[str, str]] = field(default_factory=list)
    source_file: str = ""
    error_message: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        data["agent_type"] = self.agent_type.value
        data["status"] = self.status.value
        data["timeline"] = [e.to_dict() if hasattr(e, 'to_dict') else e for e in self.timeline]
        return json.dumps(data, ensure_ascii=False, default=str)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        data = asdict(self)
        data["agent_type"] = self.agent_type.value
        data["status"] = self.status.value
        return data


class SessionParser(ABC):
    """Abstract base class for agent session parsers."""

    AGENT_TYPE: AgentType = None
    WATCH_PATHS: List[str] = []

    @abstractmethod
    def parse_file(self, file_path: Path) -> SessionSummary:
        """Parse a session file and return summary."""
        pass

    @abstractmethod
    def parse_line(self, line: str, context: Dict) -> Optional[Dict]:
        """Parse a single JSONL line. Returns event dict or None."""
        pass

    def extract_user_intent(self, text: str, max_length: int = 150) -> str:
        """Extract and truncate user intent from first message."""
        return self._truncate_text(self.normalize_text(text), max_length)

    def normalize_text(self, text: Any) -> str:
        """Normalize message text for compact display."""
        if not isinstance(text, str):
            return ""
        return " ".join(text.replace("\u00a0", " ").split())

    def collect_user_message(self, messages: List[str], text: Any) -> None:
        """Append a normalized user message if it contains readable text."""
        normalized = self.normalize_text(text)
        if normalized:
            messages.append(normalized)

    def build_user_message_summary(self, messages: List[str]) -> Dict[str, Any]:
        """Build compact user-facing context from raw user messages."""
        normalized_messages = [self.normalize_text(message) for message in messages]
        normalized_messages = [message for message in normalized_messages if message]

        first_message = normalized_messages[0] if normalized_messages else ""
        last_message = normalized_messages[-1] if normalized_messages else ""

        return {
            "user_intent": self.extract_user_intent(first_message),
            "first_user_message": self._truncate_text(first_message, 280),
            "last_user_message": self._truncate_text(last_message, 280),
            "user_messages": [self._truncate_text(message, 320) for message in normalized_messages],
            "user_message_count": len(normalized_messages),
            "intent_evolution": self._build_intent_evolution(normalized_messages),
        }

    def detect_status(self, events: List[Dict]) -> SessionStatus:
        """Detect session status from events."""
        if not events:
            return SessionStatus.UNKNOWN

        last_event = events[-1]
        event_type = last_event.get("type", "")

        # Check for completion markers
        completion_types = ["task_complete", "task_completed", "session_end"]
        if event_type in completion_types:
            return SessionStatus.COMPLETED

        # Check for error markers
        if "error" in event_type.lower() or last_event.get("error"):
            return SessionStatus.ERROR

        # Default to active if recent events
        return SessionStatus.ACTIVE

    def build_timeline(self, events: List[Dict], max_events: int = 20) -> List[TimelineEvent]:
        """Build compressed timeline from events."""
        timeline = []
        last_event_type = None

        for event in events[-max_events:]:
            event_type = event.get("type", "unknown")

            # Skip duplicate consecutive events
            if event_type == last_event_type and len(timeline) > 0:
                continue

            timeline.append(TimelineEvent(
                timestamp=event.get("timestamp", ""),
                event_type=event_type,
                description=event.get("description", event_type),
                icon=event.get("icon", "📝"),
                details=event.get("details")
            ))
            last_event_type = event_type

        return timeline

    def calculate_token_usage(self, events: List[Dict]) -> Dict[str, int]:
        """Aggregate token usage from events."""
        total = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        for event in events:
            usage = event.get("token_usage", {})
            total["input_tokens"] += usage.get("input_tokens", 0)
            total["output_tokens"] += usage.get("output_tokens", 0)
            total["total_tokens"] += usage.get("total_tokens", 0)

        return total

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate long text without breaking layout."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3].rstrip() + "..."

    def _build_intent_evolution(self, messages: List[str]) -> List[str]:
        """Compress many user turns into a short progression of intent steps."""
        if not messages:
            return []

        unique_messages: List[str] = []
        last_signature = ""

        for message in messages:
            signature = re.sub(r"\W+", " ", message.lower()).strip()
            if signature and signature != last_signature:
                unique_messages.append(message)
                last_signature = signature

        if len(unique_messages) <= 7:
            selected_messages = unique_messages
        else:
            selected_messages = []
            target = 7
            last_index = len(unique_messages) - 1
            for index in range(target):
                selected_index = round(index * last_index / (target - 1))
                selected_messages.append(unique_messages[selected_index])

        return [self._summarize_intent_step(message) for message in selected_messages]

    def _summarize_intent_step(self, text: str) -> str:
        """Extract a 3-5 word label that hints at the user's direction."""
        words = re.findall(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_./:-]*", text)
        if not words:
            return self._truncate_text(text, 40)

        preferred_words = [
            word for word in words
            if len(word) > 2 and word.lower() not in INTENT_STOPWORDS
        ]

        chosen_words = preferred_words[:5]
        if len(chosen_words) < 3:
            chosen_words = words[:5]

        return " ".join(chosen_words[:5])
