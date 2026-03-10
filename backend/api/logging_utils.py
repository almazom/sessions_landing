"""Structured logging helpers for Agent Nexus."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_CONFIGURED_LOGGERS: set[str] = set()
_SENSITIVE_FIELD_NAMES = {
    "authorization",
    "code",
    "cookie",
    "hash",
    "id_token",
    "password",
    "session_id",
}
_SENSITIVE_FIELD_SUFFIXES = ("_cookie", "_hash", "_secret", "_token")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 500 else f"{value[:497]}..."
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def configure_logging(logger: logging.Logger) -> None:
    """Install a plain stdout handler once per logger so JSON lines stay readable."""
    if logger.name in _CONFIGURED_LOGGERS:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _CONFIGURED_LOGGERS.add(logger.name)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    configure_logging(logger)
    return logger


def short_ref(value: Any, keep: int = 8) -> str:
    """Short, non-secret reference for logs."""
    text = str(value or "")
    if not text:
        return ""
    return text if len(text) <= keep else text[:keep]


def sanitize_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Mask obviously sensitive values before sending them to logs."""
    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        lowered_key = key.lower()
        if lowered_key in _SENSITIVE_FIELD_NAMES or lowered_key.endswith(_SENSITIVE_FIELD_SUFFIXES):
            sanitized[key] = "[redacted]"
            continue
        sanitized[key] = _json_safe(value)
    return sanitized


def log_event(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "logger": logger.name,
        "event": event,
    }
    payload.update(sanitize_fields(fields))
    getattr(logger, level.lower())(json.dumps(payload, ensure_ascii=False, sort_keys=True))
