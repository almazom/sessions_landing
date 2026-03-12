"""Helpers for stable session artifact routes and detail payloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.parsers import PARSER_REGISTRY
from backend.parsers.base import SessionSummary

from .scanner import SessionScanner

DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_LIVE_WITHIN_MINUTES = 10
DEFAULT_ACTIVE_WITHIN_MINUTES = 60


def resolve_timezone(name: str) -> Tuple[ZoneInfo, str]:
    try:
        return ZoneInfo(name), name
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE), DEFAULT_TIMEZONE


def build_session_route(
    harness: str,
    source_file: str,
    session_id: Optional[str] = None,
) -> Dict[str, str]:
    path = Path(source_file) if source_file else Path()
    filename = path.name

    if harness == "kimi" and path.parts:
        route_id = path.parent.name or filename or (session_id or "")
    elif harness == "gemini":
        route_id = (
            filename if filename and filename != "logs.json"
            else path.parent.name or (session_id or "")
        )
    else:
        route_id = filename or (session_id or "")

    return {
        "harness": harness,
        "id": route_id,
        "href": f"/sessions/{quote(harness, safe='')}/{quote(route_id, safe='')}",
    }


def attach_session_route(session: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(session)
    harness = str(enriched.get("agent_type") or enriched.get("provider") or "").strip()
    source_file = str(enriched.get("source_file") or enriched.get("path") or "").strip()
    session_id = str(enriched.get("session_id") or "").strip()

    if not harness or not source_file:
        return enriched

    enriched["route"] = build_session_route(harness, source_file, session_id)
    return enriched


def session_matches_route(session: Dict[str, Any], harness: str, route_id: str) -> bool:
    route = attach_session_route(session).get("route")
    return bool(route) and route.get("harness") == harness and route.get("id") == route_id


def resolve_session_file_from_store(
    sessions: Iterable[Dict[str, Any]],
    harness: str,
    route_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
    for session in sessions:
        if not session_matches_route(session, harness, route_id):
            continue
        source_file = str(session.get("source_file") or "").strip()
        if not source_file:
            continue
        return session, Path(source_file).expanduser()
    return None, None


def _iter_provider_candidate_paths(harness: str, route_id: str) -> Iterable[Path]:
    watch_root = Path(SessionScanner.WATCH_PATHS.get(harness, "")).expanduser()
    if not watch_root.exists():
        return []

    if harness == "kimi":
        return watch_root.glob(f"*/{route_id}/context.jsonl")

    if harness == "gemini" and not route_id.endswith(".json"):
        return watch_root.glob(f"{route_id}/logs.json")

    return watch_root.rglob(route_id)


def resolve_session_file_fallback(harness: str, route_id: str) -> Optional[Path]:
    for candidate in _iter_provider_candidate_paths(harness, route_id):
        if candidate.is_file():
            return candidate
    return None


def parse_session_file(harness: str, file_path: Path) -> Dict[str, Any]:
    parser_cls = PARSER_REGISTRY.get(harness)
    if not parser_cls:
        raise ValueError(f"unsupported harness: {harness}")

    parser = parser_cls()
    summary: SessionSummary = parser.parse_file(file_path)
    return summary.to_dict()


def inspect_session_file(file_path: Path) -> Dict[str, Any]:
    suffix = file_path.suffix.lower()

    if suffix == ".jsonl":
        record_count = 0
        parse_errors = 0
        with open(file_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                record_count += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    parse_errors += 1
        return {"format": "jsonl", "record_count": record_count, "parse_errors": parse_errors}

    if suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError:
                return {"format": "json", "record_count": 0, "parse_errors": 1}

        if isinstance(payload, list):
            return {"format": "json", "record_count": len(payload), "parse_errors": 0}
        return {"format": "json", "record_count": 1, "parse_errors": 0}

    return {"format": suffix.lstrip(".") or "unknown", "record_count": 0, "parse_errors": 0}


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_human(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    if rounded < 60:
        unit = "second" if rounded == 1 else "seconds"
        return f"{rounded} {unit} ago"
    if rounded < 3600:
        minutes = rounded // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit} ago"
    if rounded < 86400:
        hours = rounded // 3600
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} ago"
    days = rounded // 86400
    unit = "day" if days == 1 else "days"
    return f"{days} {unit} ago"


def duration_human(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"

    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)

    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if remaining_minutes:
        parts.append(f"{remaining_minutes} мин")
    if not hours and not remaining_minutes and remaining_seconds:
        parts.append(f"{remaining_seconds} сек")
    return " ".join(parts) if parts else "0 сек"


def modified_human(local_dt: datetime, tzinfo: ZoneInfo) -> str:
    now_local = datetime.now(timezone.utc).astimezone(tzinfo)
    if local_dt.date() == now_local.date():
        return f"today at {local_dt.strftime('%H:%M')}"
    if (now_local.date() - local_dt.date()).days == 1:
        return f"yesterday at {local_dt.strftime('%H:%M')}"
    return local_dt.strftime("%Y-%m-%d %H:%M")


def activity_state(seconds: float, live_minutes: int, active_minutes: int) -> str:
    if seconds <= live_minutes * 60:
        return "live"
    if seconds <= active_minutes * 60:
        return "active"
    return "idle"


def build_session_detail_payload(
    session: Dict[str, Any],
    file_path: Path,
    timezone_name: str = DEFAULT_TIMEZONE,
    live_within_minutes: int = DEFAULT_LIVE_WITHIN_MINUTES,
    active_within_minutes: int = DEFAULT_ACTIVE_WITHIN_MINUTES,
) -> Dict[str, Any]:
    tzinfo, timezone_label = resolve_timezone(timezone_name)
    file_stats = inspect_session_file(file_path)
    route = build_session_route(
        str(session.get("agent_type") or session.get("provider") or ""),
        str(file_path),
        str(session.get("session_id") or ""),
    )

    modified_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    modified_local = modified_at.astimezone(tzinfo)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - modified_at).total_seconds())

    started_at = parse_iso_datetime(session.get("timestamp_start"))
    ended_at = parse_iso_datetime(session.get("timestamp_end")) or modified_at
    duration_seconds: Optional[int] = None
    if started_at:
        duration_seconds = max(0, int((ended_at - started_at).total_seconds()))

    payload = {
        "provider": session.get("agent_type"),
        "agent_name": session.get("agent_name"),
        "path": str(file_path),
        "relative_path": file_path.name,
        "filename": file_path.name,
        "session_id": session.get("session_id"),
        "format": file_stats["format"],
        "modified_at": modified_at.isoformat(),
        "modified_at_local": modified_local.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "modified_human": modified_human(modified_local, tzinfo),
        "age_seconds": age_seconds,
        "age_human": age_human(age_seconds),
        "activity_state": activity_state(age_seconds, live_within_minutes, active_within_minutes),
        "record_count": file_stats["record_count"],
        "parse_errors": file_stats["parse_errors"],
        "user_message_count": session.get("user_message_count", 0),
        "started_at": started_at.isoformat() if started_at else None,
        "started_at_local": started_at.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z").strip() if started_at else None,
        "duration_seconds": duration_seconds,
        "duration_human": duration_human(duration_seconds) if duration_seconds is not None else None,
        "first_user_message": session.get("first_user_message") or "",
        "last_user_message": session.get("last_user_message") or "",
        "intent_evolution": session.get("intent_evolution") or [],
        "intent_summary_source": "local_fallback",
        "intent_summary_provider": None,
        "route": route,
        "cwd": session.get("cwd") or "",
        "status": session.get("status"),
        "user_intent": session.get("user_intent") or "",
        "tool_calls": session.get("tool_calls") or [],
        "token_usage": session.get("token_usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "files_modified": session.get("files_modified") or [],
        "git_branch": session.get("git_branch"),
        "plan_steps": session.get("plan_steps") or [],
        "timeline": session.get("timeline") or [],
        "error_message": session.get("error_message"),
    }

    return {
        "meta": {
            "timezone": timezone_label,
            "live_within_minutes": live_within_minutes,
            "active_within_minutes": active_within_minutes,
        },
        "session": payload,
    }
