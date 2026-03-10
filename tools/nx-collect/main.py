#!/usr/bin/env python3
"""Collect canonical session files across providers."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TOOL_NAME = "nx-collect"
TOOL_VERSION = "2.2.0"
DEFAULT_LIVE_MINUTES = 10
DEFAULT_ACTIVE_MINUTES = 60
DEFAULT_MODE = "latest"
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_COGNIZE_PROMPT_ID = "intent-vector-ru"
DEFAULT_COGNIZE_PROVIDER_CHAIN = "auto"
DEFAULT_COGNIZE_PREFLIGHT_TIMEOUT = 3
DEFAULT_COGNIZE_RUNTIME_TIMEOUT = 20
TIMESTAMP_KEYS = {
    "created_at",
    "createdAt",
    "ended_at",
    "endedAt",
    "started_at",
    "startedAt",
    "time",
    "timestamp",
    "updated_at",
    "updatedAt",
}
TEXT_KEYS = {
    "content",
    "description",
    "details",
    "input",
    "instruction",
    "message",
    "prompt",
    "summary",
    "text",
}
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
NOISE_PATTERNS = (
    "AGENTS.md instructions",
    "<INSTRUCTIONS>",
    "<environment_context>",
    "Codex Global Instructions",
    "<local-command-caveat>",
)
FIND_OUTPUT_PATTERN = re.compile(r"^(?P<epoch>\d+(?:\.\d+)?) (?P<path>.+)$")


@dataclass(frozen=True)
class Candidate:
    provider: str
    root: Path
    path: Path
    relative_path: str
    modified_epoch: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect canonical session files across providers.",
        allow_abbrev=False,
    )
    parser.add_argument("command", nargs="?", choices=[DEFAULT_MODE], help="Collection mode")
    parser.add_argument("--latest", action="store_true", help="Alias for the latest collection mode")
    parser.add_argument("--providers", default="all", help="Comma-separated provider list or 'all'")
    parser.add_argument("--providers-config", help="Override provider catalog JSON path")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="IANA timezone for local rendering")
    parser.add_argument(
        "--live-within-minutes",
        type=int,
        default=DEFAULT_LIVE_MINUTES,
        help="Mark sessions live when updated within this window",
    )
    parser.add_argument(
        "--active-within-minutes",
        type=int,
        default=DEFAULT_ACTIVE_MINUTES,
        help="Mark sessions active when updated within this window",
    )
    parser.add_argument(
        "--cognize-prompt-id",
        default=DEFAULT_COGNIZE_PROMPT_ID,
        help="Prompt catalog entry to use when generating semantic intent steps",
    )
    parser.add_argument(
        "--cognize-provider-chain",
        default=DEFAULT_COGNIZE_PROVIDER_CHAIN,
        help="Provider chain for nx-cognize, e.g. auto or local",
    )
    parser.add_argument(
        "--cognize-preflight-timeout",
        type=int,
        default=DEFAULT_COGNIZE_PREFLIGHT_TIMEOUT,
        help="nx-cognize preflight timeout in seconds",
    )
    parser.add_argument(
        "--cognize-runtime-timeout",
        type=int,
        default=DEFAULT_COGNIZE_RUNTIME_TIMEOUT,
        help="nx-cognize runtime timeout in seconds",
    )
    parser.add_argument("--output", "-o", help="Write result JSON to file instead of stdout")
    parser.add_argument("--version", action="store_true", help="Show version")
    return parser.parse_args()


def emit_error(message: str) -> None:
    print(message, file=sys.stderr)


def resolve_mode(args: argparse.Namespace) -> str:
    if args.command:
        return args.command
    if args.latest:
        return DEFAULT_MODE
    return DEFAULT_MODE


def resolve_timezone(name: str) -> Tuple[timezone | ZoneInfo, str]:
    try:
        return ZoneInfo(name), name
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {name}") from exc


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_provider_config(base_dir: Path, override: Optional[str]) -> Tuple[Dict[str, Any], Path]:
    config_path = Path(override).expanduser() if override else (base_dir / "providers.json")
    with open(config_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload, config_path.resolve()


def resolve_provider_list(spec: str, config: Dict[str, Any]) -> List[str]:
    supported = set(config["providers"].keys())
    if spec == "all":
        return list(config["default_providers"])

    providers = [item.strip() for item in spec.split(",") if item.strip()]
    if not providers:
        raise ValueError("provider list cannot be empty")
    invalid = [item for item in providers if item not in supported]
    if invalid:
        raise ValueError(f"unsupported providers: {', '.join(invalid)}")
    return providers


def normalize_text(value: Any, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\u00a0", " ").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def wrap_record(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"value": value}


def extract_strings(value: Any, results: List[str]) -> None:
    if isinstance(value, str):
        text = normalize_text(value)
        if text:
            results.append(text)
        return
    if isinstance(value, list):
        for item in value:
            extract_strings(item, results)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TEXT_KEYS:
                extract_strings(item, results)
            elif isinstance(item, (dict, list)):
                extract_strings(item, results)


def is_noise_message(text: str) -> bool:
    if not text:
        return True
    return any(pattern in text for pattern in NOISE_PATTERNS)


def extract_user_messages(record: Dict[str, Any]) -> List[str]:
    messages: List[str] = []
    role = record.get("role")
    record_type = record.get("type")
    is_user_entry = role == "user" or record_type == "user"

    if role == "user":
        extract_strings(record.get("content"), messages)

    if record_type == "user":
        if isinstance(record.get("message"), str):
            messages.append(normalize_text(record["message"]))
        elif isinstance(record.get("message"), dict):
            extract_strings(record["message"], messages)
        extract_strings(record.get("content"), messages)

    payload = record.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            messages.append(normalize_text(payload.get("message")))
        if payload.get("type") == "message" and payload.get("role") == "user":
            extract_strings(payload.get("content"), messages)

    message = record.get("message")
    if isinstance(message, dict) and message.get("role") == "user":
        extract_strings(message.get("content"), messages)
    elif isinstance(message, str) and is_user_entry:
        messages.append(normalize_text(message))

    content = record.get("content")
    if is_user_entry:
        extract_strings(content, messages)

    nested_messages = record.get("messages")
    if isinstance(nested_messages, list):
        for item in nested_messages:
            if isinstance(item, dict):
                messages.extend(extract_user_messages(item))

    return [text for text in messages if text and not is_noise_message(text)]


def dedupe_texts(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def detect_format(path: Path) -> str:
    return "jsonl" if path.suffix.lower() == ".jsonl" else "json"


def load_records(path: Path) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    parse_errors = 0
    source_format = detect_format(path)

    if source_format == "jsonl":
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                records.append(wrap_record(payload))
    else:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            for item in payload:
                records.append(wrap_record(item))
        else:
            records.append(wrap_record(payload))

    return records, parse_errors


def extract_session_messages(path: Path) -> Tuple[List[str], int, int]:
    records, parse_errors = load_records(path)
    return summarize_records(records, parse_errors)


def parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    if not isinstance(value, str):
        return None

    raw_value = value.strip()
    if not raw_value:
        return None
    if raw_value.isdigit():
        return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)

    candidate = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_timestamps(value: Any, results: List[datetime]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TIMESTAMP_KEYS:
                parsed = parse_timestamp(item)
                if parsed is not None:
                    results.append(parsed)
            if isinstance(item, (dict, list)):
                extract_timestamps(item, results)
        return
    if isinstance(value, list):
        for item in value:
            extract_timestamps(item, results)


def summarize_intent_step(text: str) -> str:
    words = re.findall(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_./:-]*", text)
    if not words:
        return normalize_text(text, 40)

    preferred_words = [
        word for word in words
        if len(word) > 2 and word.lower() not in INTENT_STOPWORDS
    ]
    chosen_words = preferred_words[:5]
    if len(chosen_words) < 3:
        chosen_words = words[:5]
    return " ".join(chosen_words[:5])


def build_intent_evolution(messages: List[str]) -> List[str]:
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
        last_index = len(unique_messages) - 1
        for index in range(7):
            selected_index = round(index * last_index / 6)
            selected_messages.append(unique_messages[selected_index])

    return [summarize_intent_step(message) for message in selected_messages]


def summarize_records(records: List[Dict[str, Any]], parse_errors: int) -> Tuple[List[str], int, int, Optional[datetime], List[str]]:
    messages: List[str] = []
    timestamps: List[datetime] = []
    for record in records:
        messages.extend(extract_user_messages(record))
        extract_timestamps(record, timestamps)

    unique_messages = dedupe_texts(messages)
    started_at = min(timestamps) if timestamps else None
    intent_evolution = build_intent_evolution(unique_messages)
    return unique_messages, len(records), parse_errors, started_at, intent_evolution


def derive_session_id(path: Path) -> str:
    if path.stem in {"wire", "context"} and path.parent.name:
        return path.parent.name
    if path.stem.startswith("session-"):
        return path.stem.removeprefix("session-")
    return path.stem


def project_hint_from_relative(relative_path: str) -> str:
    parts = [part for part in PurePosixPath(relative_path).parts if part]
    if not parts:
        return ""
    if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
        return "/".join(parts[:3])
    return parts[0]


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
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes} мин"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if minutes == 0:
        return f"{hours} ч"
    return f"{hours} ч {minutes} мин"


def modified_human(local_dt: datetime, tzinfo: timezone | ZoneInfo) -> str:
    today = datetime.now(tzinfo).date()
    if local_dt.date() == today:
        return f"today at {local_dt:%H:%M}"
    if local_dt.date() == today - timedelta(days=1):
        return f"yesterday at {local_dt:%H:%M}"
    return local_dt.strftime("%Y-%m-%d %H:%M")


def activity_state(seconds: float, live_minutes: int, active_minutes: int) -> str:
    if seconds <= live_minutes * 60:
        return "live"
    if seconds <= active_minutes * 60:
        return "active"
    return "idle"


def normalize_find_pattern(pattern: str) -> str:
    normalized = pattern.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("**/"):
        normalized = normalized[3:]
    return normalized


def build_find_predicate(pattern: str) -> str:
    normalized = normalize_find_pattern(pattern)
    if "/" in normalized:
        path_pattern = normalized if normalized.startswith("*") else f"*/{normalized}"
        return f"-path {shlex.quote(path_pattern)}"
    return f"-name {shlex.quote(normalized)}"


def build_find_listing_command(root: Path, include_patterns: Iterable[str], exclude_patterns: Iterable[str]) -> str:
    parts = ["find", shlex.quote(str(root)), "-type f"]
    include_predicates = [build_find_predicate(pattern) for pattern in include_patterns]
    if include_predicates:
        if len(include_predicates) == 1:
            parts.append(include_predicates[0])
        else:
            parts.append(r"\( " + " -o ".join(include_predicates) + r" \)")
    parts.extend(f"! {build_find_predicate(pattern)}" for pattern in exclude_patterns)
    parts.append(r"-printf '%T@ %p\n'")
    parts.append("2>/dev/null")
    parts.append("| sort -nr")
    return " ".join(parts)


def run_find_listing(command: str) -> Tuple[List[str], Optional[str]]:
    completed = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 and not stdout_lines:
        detail = completed.stderr.strip() or f"finder command failed with exit code {completed.returncode}"
        return [], detail
    return stdout_lines, None


def parse_candidate_line(provider_name: str, root: Path, line: str) -> Candidate:
    match = FIND_OUTPUT_PATTERN.match(line)
    if not match:
        raise ValueError(f"unexpected finder output for {provider_name}: {line}")
    path = Path(match.group("path")).expanduser().resolve()
    try:
        relative_path = path.relative_to(root).as_posix()
    except ValueError:
        relative_path = path.name
    return Candidate(
        provider=provider_name,
        root=root,
        path=path,
        relative_path=relative_path,
        modified_epoch=float(match.group("epoch")),
    )


def scan_provider(provider_name: str, provider_config: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(provider_config["root"]).expanduser()
    result: Dict[str, Any] = {
        "provider": provider_name,
        "root": str(root),
        "scanned_files": 0,
        "candidates": [],
        "error": "",
    }
    if not root.exists():
        result["error"] = "provider root does not exist"
        return result

    include_patterns = list(provider_config.get("include", []))
    exclude_patterns = list(provider_config.get("exclude", []))
    command = build_find_listing_command(root, include_patterns, exclude_patterns)
    lines, shell_error = run_find_listing(command)
    if shell_error:
        result["error"] = shell_error
        return result

    candidates: List[Candidate] = []
    for line in lines:
        try:
            candidates.append(parse_candidate_line(provider_name, root.resolve(), line))
        except ValueError as exc:
            result["error"] = str(exc)
            return result

    result["scanned_files"] = len(candidates)
    result["candidates"] = candidates
    return result


def sort_candidates(candidates: List[Candidate], provider_order: List[str]) -> List[Candidate]:
    provider_rank = {name: index for index, name in enumerate(provider_order)}
    return sorted(
        candidates,
        key=lambda item: (-item.modified_epoch, provider_rank.get(item.provider, 999), str(item.path)),
    )


def run_cognitive_intent(
    session_path: Path,
    base_dir: Path,
    prompt_id: str,
    provider_chain: str,
    preflight_timeout: int,
    runtime_timeout: int,
) -> Tuple[Optional[List[str]], Optional[str], Optional[str], Optional[str]]:
    cognize_path = (base_dir.parent / "nx-cognize" / "nx-cognize").resolve()
    if not cognize_path.exists():
        return None, None, None, "nx-cognize wrapper is not available"

    timeout_seconds = max(5, preflight_timeout + runtime_timeout + 5)
    command = [
        str(cognize_path),
        "--input",
        str(session_path),
        "--prompt-id",
        prompt_id,
        "--provider-chain",
        provider_chain,
        "--preflight-timeout",
        str(preflight_timeout),
        "--runtime-timeout",
        str(runtime_timeout),
        "--max-bullets",
        "7",
        "--max-words-per-bullet",
        "5",
    ]
    if provider_chain == "local":
        command.extend([
            "--state-file",
            str(session_path.parent / ".nx-cognize-state.local.json"),
        ])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, None, None, f"nx-cognize timed out after {timeout_seconds}s"
    except OSError as exc:
        return None, None, None, str(exc)

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or f"nx-cognize exited with code {completed.returncode}"
        return None, None, None, stderr

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, None, None, f"nx-cognize returned invalid JSON: {exc}"

    summary = payload.get("summary") or {}
    meta = payload.get("meta") or {}
    intent_steps = summary.get("intent_steps_ru") or summary.get("intent_bullets") or []
    if not isinstance(intent_steps, list):
        return None, None, None, "nx-cognize result is missing intent steps"

    normalized_steps = [
        normalize_text(step, 120)
        for step in intent_steps
        if normalize_text(step, 120)
    ]
    if len(normalized_steps) < 3:
        return None, None, None, "nx-cognize returned fewer than 3 intent steps"

    selected_provider = str(meta.get("selected_provider") or "")
    source = "ai"
    if selected_provider == "local":
        source = "local_fallback"
    return normalized_steps[:7], source, selected_provider or None, None


def enrich_candidate(
    candidate: Candidate,
    base_dir: Path,
    tzinfo: timezone | ZoneInfo,
    live_minutes: int,
    active_minutes: int,
    cognize_prompt_id: str,
    cognize_provider_chain: str,
    cognize_preflight_timeout: int,
    cognize_runtime_timeout: int,
) -> Tuple[Dict[str, Any], Optional[str]]:
    modified_at = datetime.fromtimestamp(candidate.modified_epoch, tz=timezone.utc)
    local_dt = modified_at.astimezone(tzinfo)
    now = datetime.now(timezone.utc)
    age_seconds_value = max(0.0, (now - modified_at).total_seconds())
    summary = {
        "provider": candidate.provider,
        "path": str(candidate.path),
        "relative_path": candidate.relative_path,
        "filename": candidate.path.name,
        "session_id": derive_session_id(candidate.path),
        "format": detect_format(candidate.path),
        "project_hint": project_hint_from_relative(candidate.relative_path),
        "modified_at": modified_at.isoformat(),
        "modified_at_local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
        "modified_human": modified_human(local_dt, tzinfo),
        "age_seconds": round(age_seconds_value, 2),
        "age_human": age_human(age_seconds_value),
        "activity_state": activity_state(age_seconds_value, live_minutes, active_minutes),
        "record_count": 0,
        "parse_errors": 0,
        "user_message_count": 0,
        "first_user_message": "",
        "last_user_message": "",
        "intent_evolution": [],
        "intent_summary_source": "local_fallback",
        "intent_summary_provider": "nx-collect",
    }

    try:
        messages, record_count, parse_errors, started_at, local_intent_evolution = extract_session_messages(candidate.path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return summary, str(exc)

    summary["record_count"] = record_count
    summary["parse_errors"] = parse_errors
    summary["user_message_count"] = len(messages)
    summary["intent_evolution"] = local_intent_evolution
    if messages:
        summary["first_user_message"] = messages[0]
        summary["last_user_message"] = messages[-1]
    if started_at is not None and started_at <= modified_at:
        duration_seconds = int((modified_at - started_at).total_seconds())
        summary["started_at"] = started_at.isoformat()
        summary["started_at_local"] = started_at.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        summary["duration_seconds"] = duration_seconds
        summary["duration_human"] = duration_human(duration_seconds)
    if messages:
        intent_steps, source, provider_name, cognize_error = run_cognitive_intent(
            session_path=candidate.path,
            base_dir=base_dir,
            prompt_id=cognize_prompt_id,
            provider_chain=cognize_provider_chain,
            preflight_timeout=cognize_preflight_timeout,
            runtime_timeout=cognize_runtime_timeout,
        )
        if intent_steps:
            summary["intent_evolution"] = intent_steps
            summary["intent_summary_source"] = source or "local_fallback"
            summary["intent_summary_provider"] = provider_name or "nx-cognize"
        elif cognize_error:
            return summary, f"cognize: {cognize_error}"
    return summary, None


def validate_result(payload: Dict[str, Any]) -> None:
    required = ["meta", "query", "latest", "errors"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"missing result keys: {', '.join(missing)}")
    if not isinstance(payload["errors"], list):
        raise ValueError("errors must be a list")


def write_output(payload: Dict[str, Any], output_path: Optional[str]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.write("\n")
        return
    sys.stdout.write(rendered)
    sys.stdout.write("\n")


def main() -> int:
    args = parse_args()
    if args.version:
        print(TOOL_VERSION)
        return 0

    if args.live_within_minutes < 1 or args.active_within_minutes < 1:
        emit_error("activity windows must be positive integers")
        return 2
    if args.live_within_minutes > args.active_within_minutes:
        emit_error("--live-within-minutes cannot exceed --active-within-minutes")
        return 2
    if args.cognize_preflight_timeout < 1 or args.cognize_runtime_timeout < 1:
        emit_error("cognize timeouts must be positive integers")
        return 2

    mode = resolve_mode(args)

    try:
        tzinfo, timezone_label = resolve_timezone(args.timezone)
        base_dir = Path(__file__).resolve().parent
        provider_config, provider_config_path = load_provider_config(base_dir, args.providers_config)
        providers = resolve_provider_list(args.providers, provider_config)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        emit_error(str(exc))
        return 2

    scan_results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers) or 1) as executor:
        future_map = {
            executor.submit(scan_provider, provider, provider_config["providers"][provider]): provider
            for provider in providers
        }
        for future in concurrent.futures.as_completed(future_map):
            scan_results.append(future.result())

    scan_by_provider = {item["provider"]: item for item in scan_results}
    ordered_scan_results = [scan_by_provider[provider] for provider in providers]

    all_candidates: List[Candidate] = []
    errors: List[Dict[str, str]] = []
    for scan_result in ordered_scan_results:
        all_candidates.extend(scan_result["candidates"])
        if scan_result["error"]:
            errors.append(
                {
                    "provider": scan_result["provider"],
                    "stage": "scan",
                    "detail": scan_result["error"],
                }
            )

    sorted_candidates = sort_candidates(all_candidates, providers)
    latest_candidate = sorted_candidates[0] if sorted_candidates else None
    enriched_cache: Dict[str, Dict[str, Any]] = {}

    def cached_enrich(candidate: Candidate) -> Dict[str, Any]:
        cache_key = str(candidate.path)
        if cache_key in enriched_cache:
            return enriched_cache[cache_key]
        summary, parse_error = enrich_candidate(
            candidate,
            base_dir=base_dir,
            tzinfo=tzinfo,
            live_minutes=args.live_within_minutes,
            active_minutes=args.active_within_minutes,
            cognize_prompt_id=args.cognize_prompt_id,
            cognize_provider_chain=args.cognize_provider_chain,
            cognize_preflight_timeout=args.cognize_preflight_timeout,
            cognize_runtime_timeout=args.cognize_runtime_timeout,
        )
        if parse_error:
            stage = "cognize" if parse_error.startswith("cognize: ") else "parse"
            errors.append(
                {
                    "provider": candidate.provider,
                    "stage": stage,
                    "detail": f"{candidate.path}: {parse_error.removeprefix('cognize: ')}",
                }
            )
        enriched_cache[cache_key] = summary
        return summary

    latest = cached_enrich(latest_candidate) if latest_candidate else None

    result = {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "generated_at": utcnow_iso(),
            "timezone": timezone_label,
            "scanned_providers": len(providers),
            "scanned_files": len(all_candidates),
        },
        "query": {
            "mode": mode,
            "providers": providers,
            "timezone": timezone_label,
            "live_within_minutes": args.live_within_minutes,
            "active_within_minutes": args.active_within_minutes,
            "cognize_prompt_id": args.cognize_prompt_id,
            "cognize_provider_chain": args.cognize_provider_chain,
            "providers_config_path": str(provider_config_path),
        },
        "latest": latest,
        "errors": errors,
    }

    try:
        validate_result(result)
    except ValueError as exc:
        emit_error(str(exc))
        return 4

    write_output(result, args.output)
    return 0 if latest else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        emit_error("interrupted")
        raise SystemExit(130)
