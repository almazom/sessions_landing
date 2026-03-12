"""Helpers for stable session artifact routes and detail payloads."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.parsers import PARSER_REGISTRY
from backend.parsers.base import SessionSummary

from .scanner import SessionScanner

DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_LIVE_WITHIN_MINUTES = 10
DEFAULT_ACTIVE_WITHIN_MINUTES = 60
DETAIL_TIMELINE_LIMIT = 14
DETAIL_GIT_COMMIT_LIMIT = 12


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


def _normalize_message_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def _message_signature(value: str) -> str:
    normalized = _normalize_message_text(value).lower()
    return re.sub(r"\W+", " ", normalized).strip()


def _dedupe_consecutive_messages(messages: Iterable[Any]) -> List[str]:
    deduped: List[str] = []
    last_signature = None

    for message in messages:
        normalized = _normalize_message_text(message)
        if not normalized:
            continue

        signature = _message_signature(normalized)
        if signature and signature == last_signature:
            continue

        deduped.append(normalized)
        last_signature = signature

    return deduped


def _select_evenly_spaced(values: List[Any], limit: int) -> List[Any]:
    if len(values) <= limit:
        return list(values)

    last_index = len(values) - 1
    selected: List[Any] = []
    seen_indexes = set()

    for index in range(limit):
        selected_index = round(index * last_index / (limit - 1))
        if selected_index in seen_indexes:
            continue
        selected.append(values[selected_index])
        seen_indexes.add(selected_index)

    if len(selected) == limit:
        return selected

    for value in values:
        if value in selected:
            continue
        selected.append(value)
        if len(selected) == limit:
            break

    return selected


def build_message_anchors(messages: Iterable[Any]) -> Dict[str, Any]:
    deduped = _dedupe_consecutive_messages(messages)
    if not deduped:
        return {
            "first": "",
            "middle": [],
            "last": "",
        }

    first = deduped[0]
    last = deduped[-1]
    middle_candidates = deduped[1:-1]
    middle_limit = min(4, len(middle_candidates))
    middle = (
        _select_evenly_spaced(middle_candidates, middle_limit)
        if middle_limit > 0
        else []
    )

    return {
        "first": first,
        "middle": middle,
        "last": last,
    }


def build_detail_timeline(timeline: Iterable[Any], max_events: int = DETAIL_TIMELINE_LIMIT) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []

    for raw_event in timeline:
        if hasattr(raw_event, "to_dict"):
            event = raw_event.to_dict()
        elif isinstance(raw_event, dict):
            event = dict(raw_event)
        else:
            continue

        normalized.append({
            "timestamp": event.get("timestamp", ""),
            "event_type": event.get("event_type") or event.get("type") or "unknown",
            "description": event.get("description") or event.get("event_type") or event.get("type") or "unknown",
            "icon": event.get("icon", "📝"),
            "details": event.get("details"),
        })

    if len(normalized) <= max_events:
        return normalized

    if max_events <= 2:
        return normalized[:max_events]

    first = normalized[0]
    last = normalized[-1]
    middle = normalized[1:-1]
    middle_limit = max_events - 2

    return [first, *_select_evenly_spaced(middle, middle_limit), last]


def _empty_git_context(repository_root: Optional[str] = None) -> Dict[str, Any]:
    return {
        "repository_root": repository_root,
        "commits": [],
    }


def _run_git_command(cwd: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_git_repository_root(cwd: str) -> Optional[str]:
    if not cwd:
        return None

    path = Path(cwd).expanduser()
    if not path.exists():
        return None

    result = _run_git_command(str(path), ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None

    repository_root = result.stdout.strip()
    return repository_root or None


def list_session_git_commits(
    cwd: str,
    started_at: Optional[str],
    ended_at: Optional[str],
    timezone_name: str = DEFAULT_TIMEZONE,
    limit: int = DETAIL_GIT_COMMIT_LIMIT,
) -> Dict[str, Any]:
    repository_root = resolve_git_repository_root(cwd)
    if not repository_root:
        return _empty_git_context()

    started_dt = parse_iso_datetime(started_at)
    ended_dt = parse_iso_datetime(ended_at)
    if not started_dt or not ended_dt or ended_dt < started_dt:
        return _empty_git_context(repository_root)

    tzinfo, _ = resolve_timezone(timezone_name)
    pretty_format = "%H%x1f%h%x1f%aI%x1f%an%x1f%s%x1e"
    result = _run_git_command(
        repository_root,
        [
            "log",
            "--reverse",
            "--no-merges",
            f"--since={started_dt.isoformat()}",
            f"--until={ended_dt.isoformat()}",
            f"--pretty=format:{pretty_format}",
            f"-n{limit}",
        ],
    )

    if result.returncode != 0 or not result.stdout.strip():
        return _empty_git_context(repository_root)

    commits: List[Dict[str, Any]] = []
    for raw_record in result.stdout.split("\x1e"):
        record = raw_record.strip()
        if not record:
            continue

        parts = [part.strip() for part in record.split("\x1f")]
        if len(parts) != 5:
            continue

        commit_hash, short_hash, committed_at, author_name, title = parts
        committed_dt = parse_iso_datetime(committed_at)
        commits.append({
            "hash": commit_hash,
            "short_hash": short_hash,
            "title": title,
            "author_name": author_name,
            "committed_at": committed_dt.isoformat() if committed_dt else committed_at,
            "committed_at_local": committed_dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z").strip() if committed_dt else committed_at,
        })

    return {
        "repository_root": repository_root,
        "commits": commits,
    }


def build_session_git_commit_context(
    cwd: str,
    started_at: Optional[str],
    ended_at: Optional[str],
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    return list_session_git_commits(
        cwd=cwd,
        started_at=started_at,
        ended_at=ended_at,
        timezone_name=timezone_name,
    )


def build_session_detail_payload(
    session: Dict[str, Any],
    file_path: Path,
    timezone_name: str = DEFAULT_TIMEZONE,
    live_within_minutes: int = DEFAULT_LIVE_WITHIN_MINUTES,
    active_within_minutes: int = DEFAULT_ACTIVE_WITHIN_MINUTES,
) -> Dict[str, Any]:
    tzinfo, timezone_label = resolve_timezone(timezone_name)
    file_stats = inspect_session_file(file_path)
    user_messages = session.get("user_messages") or []
    message_anchors = build_message_anchors(user_messages)
    timeline = build_detail_timeline(session.get("timeline") or [])
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
    git_context = build_session_git_commit_context(
        cwd=str(session.get("cwd") or ""),
        started_at=started_at.isoformat() if started_at else None,
        ended_at=ended_at.isoformat(),
        timezone_name=timezone_label,
    )
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
        "user_messages": _dedupe_consecutive_messages(user_messages),
        "message_anchors": message_anchors,
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
        "git_repository_root": git_context.get("repository_root"),
        "git_commits": git_context.get("commits") or [],
        "plan_steps": session.get("plan_steps") or [],
        "timeline": timeline,
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
