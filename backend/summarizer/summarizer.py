"""Session summarizer that compresses session data to ~1KB JSON.

Responsibilities:
- Extract user intent from first message
- Build mini-timeline from events
- Aggregate token usage
- Detect session status
- Compress to target size
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from ..parsers.base import SessionSummary, TimelineEvent
from ..parsers import (
    CodexParser, KimiParser, GeminiParser, QwenParser, ClaudeParser
)


# Secret patterns to mask BEFORE any data reaches frontend
SECRET_PATTERNS = [
    # OpenAI API keys
    (r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***'),
    (r'sk-proj-[a-zA-Z0-9]{20,}', 'sk-proj-***REDACTED***'),
    # GitHub tokens
    (r'ghp_[a-zA-Z0-9]{36}', 'ghp_***REDACTED***'),
    (r'gho_[a-zA-Z0-9]{36}', 'gho_***REDACTED***'),
    (r'ghu_[a-zA-Z0-9]{36}', 'ghu_***REDACTED***'),
    (r'ghs_[a-zA-Z0-9]{36}', 'ghs_***REDACTED***'),
    (r'ghr_[a-zA-Z0-9]{36}', 'ghr_***REDACTED***'),
    # Slack tokens
    (r'xoxb-[a-zA-Z0-9-]+', 'xoxb-***REDACTED***'),
    (r'xoxa-[a-zA-Z0-9-]+', 'xoxa-***REDACTED***'),
    (r'xoxp-[a-zA-Z0-9-]+', 'xoxp-***REDACTED***'),
    # Bearer tokens
    (r'Bearer\s+[a-zA-Z0-9_-]+', 'Bearer ***REDACTED***'),
    # JWT tokens
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', 'eyJ***REDACTED***'),
    # OAuth tokens in URLs
    (r'access_token=[a-zA-Z0-9_-]+', 'access_token=***REDACTED***'),
    (r'refresh_token=[a-zA-Z0-9_-]+', 'refresh_token=***REDACTED***'),
    # API keys in env vars
    (r'API_KEY\s*=\s*["\']?[a-zA-Z0-9_-]{8,}["\']?', 'API_KEY=***REDACTED***'),
    (r'API_TOKEN\s*=\s*["\']?[a-zA-Z0-9_-]{8,}["\']?', 'API_TOKEN=***REDACTED***'),
    (r'SECRET\s*=\s*["\']?[a-zA-Z0-9_-]{8,}["\']?', 'SECRET=***REDACTED***'),
    (r'PASSWORD\s*=\s*["\']?[a-zA-Z0-9_-]{8,}["\']?', 'PASSWORD=***REDACTED***'),
    (r'AUTH_TOKEN\s*=\s*["\']?[a-zA-Z0-9_-]{8,}["\']?', 'AUTH_TOKEN=***REDACTED***'),
    # AWS keys
    (r'AKIA[0-9A-Z]{16}', 'AKIA***REDACTED***'),
    (r'aws_secret_access_key\s*=\s*[a-zA-Z0-9/+=]+', 'aws_secret_access_key=***REDACTED***'),
    # Google API keys
    (r'AIza[a-zA-Z0-9_-]{35}', 'AIza***REDACTED***'),
    # Private keys
    (r'-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----', '-----BEGIN PRIVATE KEY-----***REDACTED***-----END PRIVATE KEY-----'),
    (r'-----BEGIN RSA PRIVATE KEY-----[\s\S]*?-----END RSA PRIVATE KEY-----', '-----BEGIN RSA PRIVATE KEY-----***REDACTED***-----END RSA PRIVATE KEY-----'),
    # URLs with credentials
    (r'([a-zA-Z]+://)([^:]+):([^@]+)@', r'\1***:***@'),
    # encrypted_content field (from Codex logs)
    (r'"encrypted_content":\s*"[^"]*"', '"encrypted_content": "***REDACTED***"'),
    # Generic tokens
    (r'"token":\s*"[a-zA-Z0-9_-]{20,}"', '"token": "***REDACTED***"'),
    (r'"api_key":\s*"[a-zA-Z0-9_-]{20,}"', '"api_key": "***REDACTED***"'),
]


class SessionSummarizer:
    """Compresses session logs to ~1KB summaries."""

    TARGET_SIZE_BYTES = 1024  # Target ~1KB per session
    MAX_INTENT_LENGTH = 150
    MAX_TIMELINE_EVENTS = 20
    MAX_TOOL_CALLS = 30

    def __init__(self):
        self.parsers = {
            "codex": CodexParser(),
            "kimi": KimiParser(),
            "gemini": GeminiParser(),
            "qwen": QwenParser(),
            "claude": ClaudeParser(),
        }

    def summarize_file(self, file_path: Path, agent_type: str) -> Optional[SessionSummary]:
        """Parse a session file and return compressed summary."""
        parser = self.parsers.get(agent_type)
        if not parser:
            return None

        try:
            summary = parser.parse_file(file_path)
            return self.compress(summary)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None

    def compress(self, summary: SessionSummary) -> SessionSummary:
        """Compress a summary to target size."""
        # Truncate user intent
        summary.user_intent = self._truncate_text(summary.user_intent, self.MAX_INTENT_LENGTH)

        # Mask secrets in user intent
        summary.user_intent = self._mask_secrets(summary.user_intent)

        # Limit timeline events
        if len(summary.timeline) > self.MAX_TIMELINE_EVENTS:
            # Keep first and last events, sample middle
            summary.timeline = self._sample_timeline(summary.timeline, self.MAX_TIMELINE_EVENTS)

        # Limit tool calls
        if len(summary.tool_calls) > self.MAX_TOOL_CALLS:
            summary.tool_calls = summary.tool_calls[:self.MAX_TOOL_CALLS]

        # Mask secrets in timeline descriptions
        for event in summary.timeline:
            if event.details:
                event.details = self._mask_secrets(event.details)

        return summary

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        if not text:
            return ""
        text = " ".join(text.split())  # Normalize whitespace
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    def _mask_secrets(self, text: str) -> str:
        """Mask all known secret patterns in text."""
        if not text:
            return text

        masked = text
        for pattern, replacement in SECRET_PATTERNS:
            masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)

        return masked

    def _sample_timeline(self, timeline: List[TimelineEvent], max_events: int) -> List[TimelineEvent]:
        """Sample timeline to max events, keeping first and last."""
        if len(timeline) <= max_events:
            return timeline

        # Always keep first and last
        first = timeline[0]
        last = timeline[-1]

        # Sample from middle
        middle = timeline[1:-1]
        step = len(middle) / (max_events - 2)

        sampled = [first]
        for i in range(max_events - 2):
            idx = int(i * step)
            if idx < len(middle):
                sampled.append(middle[idx])
        sampled.append(last)

        return sampled

    def to_json(self, summary: SessionSummary) -> str:
        """Convert summary to JSON string."""
        return summary.to_json()

    def check_size(self, summary: SessionSummary) -> int:
        """Check size of summary in bytes."""
        return len(summary.to_json().encode('utf-8'))

    def is_within_target(self, summary: SessionSummary) -> bool:
        """Check if summary is within target size."""
        return self.check_size(summary) <= self.TARGET_SIZE_BYTES


def mask_secrets_in_dict(data: Dict) -> Dict:
    """Recursively mask secrets in a dictionary."""
    summarizer = SessionSummarizer()

    def mask_value(value):
        if isinstance(value, str):
            return summarizer._mask_secrets(value)
        elif isinstance(value, dict):
            return {k: mask_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [mask_value(item) for item in value]
        return value

    return mask_value(data)
