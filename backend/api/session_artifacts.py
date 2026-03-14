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

from .interactive_identity import (
    InteractiveIdentityMismatch,
    InteractiveIdentityNotFound,
    InteractiveIdentityStale,
    resolve_runtime_identity_from_artifact_route,
)
from .scanner import SessionScanner

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERACTIVE_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "interactive"
INTERACTIVE_FIXTURE_FALLBACKS = {
    "codex": INTERACTIVE_FIXTURE_ROOT / "codex" / "rollout-interactive-fixture.jsonl",
}

DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_LIVE_WITHIN_MINUTES = 10
DEFAULT_ACTIVE_WITHIN_MINUTES = 60
DETAIL_TIMELINE_LIMIT = 14
DETAIL_GIT_COMMIT_LIMIT = 12
DETAIL_TOPIC_THREAD_LIMIT = 5

TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "apply",
    "are",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
    "add",
    "check",
    "collect",
    "continue",
    "create",
    "debug",
    "do",
    "edit",
    "file",
    "files",
    "fix",
    "improve",
    "make",
    "open",
    "patch",
    "pnpm",
    "resume",
    "run",
    "ship",
    "show",
    "update",
    "verify",
    "bye",
    "agent",
    "artifact",
    "artifacts",
    "context",
    "command",
    "commands",
    "exec",
    "hello",
    "first",
    "last",
    "latest",
    "message",
    "messages",
    "now",
    "step",
    "steps",
    "tool",
    "tools",
    "block",
    "user",
    "users",
    "в",
    "во",
    "для",
    "до",
    "и",
    "из",
    "или",
    "как",
    "на",
    "не",
    "но",
    "о",
    "об",
    "по",
    "под",
    "при",
    "с",
    "со",
    "что",
    "это",
    "добавить",
    "запустить",
    "открыть",
    "первое",
    "первый",
    "показать",
    "последнее",
    "последний",
    "проверить",
    "продолжить",
    "сделать",
    "сессию",
    "сессии",
    "собрать",
    "финальный",
}

TOPIC_GENERIC_TOKENS = {
    "api",
    "app",
    "backend",
    "card",
    "cards",
    "client",
    "components",
    "frontend",
    "json",
    "jsonl",
    "jsx",
    "main",
    "md",
    "py",
    "spec",
    "test",
    "tests",
    "ts",
    "tsx",
}

TOPIC_SKIP_UNIGRAMS = {
    "detail",
    "page",
    "session",
}

TOPIC_SOURCE_WEIGHTS = {
    "commit": 4,
    "file": 3,
    "timeline": 2,
    "message": 1,
    "tool": 1,
}

EVIDENCE_LAYER_ORDER = [
    "user messages",
    "artifact timeline",
    "files modified",
    "git commits",
]

INTERACTIVE_TRANSPORT_BY_HARNESS = {
    "codex": "codex_app_server",
}


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
    interactive_fixture_path = INTERACTIVE_FIXTURE_FALLBACKS.get(harness)
    if (
        interactive_fixture_path is not None
        and interactive_fixture_path.exists()
        and interactive_fixture_path.name == route_id
    ):
        return interactive_fixture_path

    for candidate in _iter_provider_candidate_paths(harness, route_id):
        if candidate.is_file():
            return candidate
    return None


def _apply_repo_fixture_session_overrides(
    harness: str,
    file_path: Path,
    session: Dict[str, Any],
) -> Dict[str, Any]:
    fixture_path = INTERACTIVE_FIXTURE_FALLBACKS.get(harness)
    if fixture_path is None:
        return session

    if file_path.expanduser().resolve() != fixture_path.expanduser().resolve():
        return session

    return {
        **session,
        "resume_supported": True,
    }


def derive_resume_supported(session: Dict[str, Any]) -> bool:
    if "resume_supported" in session:
        return bool(session.get("resume_supported"))

    harness = str(session.get("agent_type") or session.get("provider") or "").strip().lower()
    session_id = str(session.get("session_id") or "").strip()
    cwd = str(session.get("cwd") or "").strip()

    if harness != "codex":
        return False

    if not session_id or not cwd:
        return False

    return bool(
        re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            session_id,
        )
    )


def parse_session_file(harness: str, file_path: Path) -> Dict[str, Any]:
    parser_cls = PARSER_REGISTRY.get(harness)
    if not parser_cls:
        raise ValueError(f"unsupported harness: {harness}")

    parser = parser_cls()
    summary: SessionSummary = parser.parse_file(file_path)
    return _apply_repo_fixture_session_overrides(
        harness,
        file_path,
        summary.to_dict(),
    )


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


def _format_local_datetime(value: Optional[datetime], tzinfo: ZoneInfo) -> Optional[str]:
    if not value:
        return None
    return value.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def _camel_case_to_words(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)


def _tokenize_topic_text(value: str) -> List[str]:
    normalized = _camel_case_to_words(value).replace("/", " ").replace("_", " ").replace("-", " ")
    tokens = re.findall(r"[A-Za-zА-Яа-я0-9]+", normalized.lower())
    return [
        token
        for token in tokens
        if len(token) >= 3
        and not token.isdigit()
        and token not in TOPIC_STOPWORDS
    ]


def build_topic_threads(
    user_messages: Iterable[Any],
    timeline: Iterable[Dict[str, Any]],
    files_modified: Iterable[Any],
    git_commits: Iterable[Dict[str, Any]],
    tool_calls: Iterable[Any],
    limit: int = DETAIL_TOPIC_THREAD_LIMIT,
) -> List[str]:
    scored_candidates: Dict[str, Dict[str, Any]] = {}

    def add_candidate(label: str, signal: str, bonus: int = 0) -> None:
        normalized = " ".join(label.split()).strip()
        if not normalized:
            return

        payload = scored_candidates.setdefault(
            normalized,
            {"label": normalized, "score": 0, "signals": set()},
        )
        payload["score"] += TOPIC_SOURCE_WEIGHTS.get(signal, 1) + bonus
        payload["signals"].add(signal)

    def ingest_text(value: str, signal: str) -> None:
        tokens = _tokenize_topic_text(value)
        if not tokens:
            return

        for token in tokens:
            if token in TOPIC_GENERIC_TOKENS or token in TOPIC_SKIP_UNIGRAMS:
                continue
            add_candidate(token, signal)

        for first, second in zip(tokens, tokens[1:]):
            if first in TOPIC_GENERIC_TOKENS or second in TOPIC_GENERIC_TOKENS:
                continue
            add_candidate(f"{first} {second}", signal, bonus=1)

    for message in user_messages:
        if isinstance(message, str):
            ingest_text(message, "message")

    for event in timeline:
        if isinstance(event, dict):
            ingest_text(str(event.get("description") or ""), "timeline")

    for file_path in files_modified:
        if isinstance(file_path, str):
            ingest_text(file_path, "file")

    for commit in git_commits:
        if isinstance(commit, dict):
            ingest_text(str(commit.get("title") or ""), "commit")

    for tool in tool_calls:
        if isinstance(tool, str):
            ingest_text(tool, "tool")

    ranked = sorted(
        scored_candidates.values(),
        key=lambda item: (
            len(item["label"].split()) > 1,
            len(item["signals"]),
            item["score"],
            len(item["label"]),
        ),
        reverse=True,
    )

    selected: List[str] = []
    seen_tokens: set[str] = set()
    for item in ranked:
        label = item["label"]
        label_tokens = set(label.split())
        if label_tokens and label_tokens <= seen_tokens:
            continue

        selected.append(label)
        seen_tokens.update(label_tokens)

        if len(selected) >= limit:
            break

    return selected


def build_session_state_model(
    session: Dict[str, Any],
    computed_activity_state: str,
    interactive_session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status = str(session.get("status") or "").strip().lower()
    query_enabled = bool(session.get("query_enabled"))
    resume_supported = bool(session.get("resume_supported"))
    within_operational_window = computed_activity_state in {"live", "active"}

    labels: List[str] = []
    if status in {"completed", "error", "failed"}:
        labels.append("archived")
    elif computed_activity_state == "live":
        labels.append("live")
    elif status in {"active", "running"} and within_operational_window:
        labels.append("live")
    else:
        labels.append("archived")

    if resume_supported:
        labels.append("restorable")
    if query_enabled:
        labels.append("queryable")

    if resume_supported:
        safety_mode = "resume-allowed"
        summary = "Сессию можно безопасно продолжить через отдельный harness flow."
    elif query_enabled:
        safety_mode = "ask-only"
        summary = "Сессию можно читать и использовать для безопасных вопросов без продолжения runtime."
    elif status in {"active", "running"} and computed_activity_state == "idle":
        safety_mode = "read-only"
        summary = (
            "Artifact ещё помечен как active, но recent activity уже idle, "
            "поэтому detail page честно остаётся read-only до явного restore flow."
        )
    else:
        safety_mode = "read-only"
        summary = "Сессия доступна только для чтения: resume и ask flow пока не подключены."

    rationale = [
        f"Observed status: {status or 'unknown'}.",
        f"Observed activity state: {computed_activity_state}.",
    ]
    if status in {"active", "running"} and computed_activity_state == "idle":
        rationale.append(
            "The source still says active, but the recent activity window is already cold."
        )

    rationale.extend([
        "Resume stays disabled until a harness-specific restore flow exists.",
        "Ask mode is enabled only when an explicit query layer is wired.",
    ])

    return {
        "labels": labels,
        "safety_mode": safety_mode,
        "summary": summary,
        "rationale": rationale,
        "capabilities": {
            "can_ask": query_enabled,
            "can_resume": resume_supported,
            "can_restore": resume_supported,
        },
        "interactive_session": interactive_session,
    }


def build_interactive_session_capability(
    session: Dict[str, Any],
    route: Dict[str, str],
) -> Dict[str, Any]:
    def capability_response(
        *,
        available: bool,
        label: str,
        detail: str,
        href: Optional[str],
        transport: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "available": available,
            "label": label,
            "detail": detail,
            "href": href,
            "transport": transport,
        }

    harness = str(session.get("agent_type") or session.get("provider") or "").strip()
    session_id = str(session.get("session_id") or "").strip()
    interactive_transport = INTERACTIVE_TRANSPORT_BY_HARNESS.get(harness)

    if not interactive_transport:
        return capability_response(
            available=False,
            label="Interactive mode not supported",
            detail="Interactive browser continuation is not supported for this harness yet.",
            href=None,
            transport=None,
        )

    interactive_href = f"{route['href']}/interactive"
    if not bool(session.get("resume_supported")):
        return capability_response(
            available=False,
            label="Interactive mode not enabled",
            detail="Interactive continuation stays disabled until resume support is explicitly enabled.",
            href=interactive_href,
            transport=interactive_transport,
        )

    try:
        resolve_runtime_identity_from_artifact_route(
            harness=harness,
            artifact_route_id=route["id"],
            artifact_session_id=session_id,
        )
    except InteractiveIdentityNotFound:
        detail = "Interactive continuation is disabled because no runtime identity mapping was found."
    except InteractiveIdentityStale:
        detail = "Interactive continuation is disabled because the runtime identity is stale."
    except InteractiveIdentityMismatch:
        detail = "Interactive continuation is disabled because the runtime identity does not match this route."
    else:
        return capability_response(
            available=True,
            label="Interactive mode available",
            detail="Open the dedicated route to continue this Codex session through the backend interactive flow.",
            href=interactive_href,
            transport=interactive_transport,
        )

    return capability_response(
        available=False,
        label="Interactive mode blocked",
        detail=detail,
        href=interactive_href,
        transport=interactive_transport,
    )


def build_evidence_sparsity(
    user_messages: Iterable[Any],
    timeline: Iterable[Dict[str, Any]],
    files_modified: Iterable[Any],
    git_commits: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    timeline_items = list(timeline)
    git_commit_items = list(git_commits)
    has_message_layer = bool(_dedupe_consecutive_messages(user_messages))
    has_file_layer = any(isinstance(path, str) and path.strip() for path in files_modified)

    present_layers: List[str] = []
    if has_message_layer:
        present_layers.append("user messages")
    if timeline_items:
        present_layers.append("artifact timeline")
    if has_file_layer:
        present_layers.append("files modified")
    if git_commit_items:
        present_layers.append("git commits")

    missing_layers = [
        label
        for label in EVIDENCE_LAYER_ORDER
        if label not in present_layers
    ]
    has_repo_signal = any(label in {"files modified", "git commits"} for label in present_layers)
    is_sparse = len(present_layers) <= 1 or (len(present_layers) == 2 and not has_repo_signal)

    if not present_layers:
        summary = (
            "Evidence stack пока почти пустой: виден только source artifact, "
            "а сообщения, timeline и repo signals для этого окна ещё не проявились."
        )
    elif is_sparse:
        summary = (
            f"Evidence stack пока тонкий: {', '.join(present_layers)} доступны, "
            f"но {', '.join(missing_layers)} отсутствуют в этом окне."
        )
    else:
        summary = (
            f"Evidence stack уже многослойный: {', '.join(present_layers)} "
            "подтверждают историю этой сессии."
        )

    return {
        "is_sparse": is_sparse,
        "summary": summary,
        "present_layers": present_layers,
        "missing_layers": missing_layers,
    }


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
    session = {
        **session,
        "resume_supported": derive_resume_supported(session),
    }
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
    computed_activity_state = activity_state(age_seconds, live_within_minutes, active_within_minutes)

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

    topic_threads = build_topic_threads(
        user_messages=user_messages,
        timeline=timeline,
        files_modified=session.get("files_modified") or [],
        git_commits=git_context.get("commits") or [],
        tool_calls=session.get("tool_calls") or [],
    )
    interactive_session = build_interactive_session_capability(session, route)
    state_model = build_session_state_model(session, computed_activity_state, interactive_session=interactive_session)
    evidence_sparsity = build_evidence_sparsity(
        user_messages=user_messages,
        timeline=timeline,
        files_modified=session.get("files_modified") or [],
        git_commits=git_context.get("commits") or [],
    )
    time_window = {
        "source": "session_artifact",
        "started_at": started_at.isoformat() if started_at else None,
        "started_at_local": _format_local_datetime(started_at, tzinfo),
        "ended_at": ended_at.isoformat(),
        "ended_at_local": _format_local_datetime(ended_at, tzinfo),
        "duration_seconds": duration_seconds,
        "duration_human": duration_human(duration_seconds) if duration_seconds is not None else None,
        "scope_summary": "Commits, files, and timeline evidence are interpreted inside this session window.",
    }

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
        "activity_state": computed_activity_state,
        "record_count": file_stats["record_count"],
        "parse_errors": file_stats["parse_errors"],
        "user_message_count": session.get("user_message_count", 0),
        "started_at": started_at.isoformat() if started_at else None,
        "started_at_local": _format_local_datetime(started_at, tzinfo),
        "ended_at": ended_at.isoformat(),
        "ended_at_local": _format_local_datetime(ended_at, tzinfo),
        "duration_seconds": duration_seconds,
        "duration_human": duration_human(duration_seconds) if duration_seconds is not None else None,
        "time_window": time_window,
        "first_user_message": session.get("first_user_message") or "",
        "last_user_message": session.get("last_user_message") or "",
        "user_messages": _dedupe_consecutive_messages(user_messages),
        "message_anchors": message_anchors,
        "intent_evolution": session.get("intent_evolution") or [],
        "intent_summary_source": "local_fallback",
        "intent_summary_provider": None,
        "topic_threads": topic_threads,
        "route": route,
        "cwd": session.get("cwd") or "",
        "status": session.get("status"),
        "state_model": state_model,
        "evidence_sparsity": evidence_sparsity,
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
