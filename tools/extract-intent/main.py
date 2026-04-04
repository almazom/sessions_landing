#!/usr/bin/env python3
"""Dedicated CLI for semantic intent extraction and tracked file change summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple


TOOL_NAME = "extract-intent"
TOOL_VERSION = "1.9.0"
PROMPT_ID = "intent-vector-ru"
TRACK_PROMPT_ID = "change-vector-ru"
DEFAULT_MAX_STEPS = 5
DEFAULT_TRACK_MAX_STEPS = 7
DEFAULT_PREFLIGHT_TIMEOUT = 30
DEFAULT_RUNTIME_TIMEOUT = 60
DEFAULT_PROVIDER_CHAIN = "auto"
DEFAULT_FORMAT = "auto"
DEFAULT_TRACK_KIND = "auto"
DEFAULT_TRACK_STATE_DIR = "~/.cache/extract-intent_cli/track"
TRACK_STATE_VERSION = 1
TRACK_MAX_WORDS_PER_BULLET = 3
TRACK_EVENT_LIMIT = 18
TRACK_STREAM_SAMPLE_LIMIT = 12
STEP_NUMERALS = ["①", "②", "③", "④", "⑤", "⑥", "⑦"]
STREAM_SIGNAL_PATTERNS = {
    "error_lines": re.compile(r"(error|exception|fatal|traceback|fail(?:ed|ure)?)", re.IGNORECASE),
    "warn_lines": re.compile(r"(warn|warning)", re.IGNORECASE),
    "timeout_lines": re.compile(r"(timeout|timed out|deadline exceeded)", re.IGNORECASE),
    "retry_lines": re.compile(r"\bretry\b", re.IGNORECASE),
    "auth_lines": re.compile(r"(401|403|auth|unauthor|forbidden|access denied)", re.IGNORECASE),
    "queue_lines": re.compile(r"(queue|очеред)", re.IGNORECASE),
}


class TrackStateError(ValueError):
    """Raised when persisted track state is invalid or incompatible."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Extract easy-to-read Russian intent steps from one session file or summarize tracked file changes.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", "-i", help="Path to one JSON or JSONL session file")
    parser.add_argument("--project", help="Project folder; resolve the latest session file for this project before extraction")
    parser.add_argument("--track", help="Path to one tracked JSON, JSONL, or log file")
    parser.add_argument(
        "--provider",
        "--harness-provider",
        "--hp",
        dest="harness_provider",
        help="Single source harness provider alias, used with --project, e.g. gemini or pi",
    )
    parser.add_argument("--providers", default="all", help="Comma-separated provider list or 'all' when using --project")
    parser.add_argument("--providers-config", help="Override provider catalog JSON path for --project resolution")
    parser.add_argument("--date", help="List sessions by date: today, yesterday, week, YYYY-MM-DD, or last-N-days")

    parser.add_argument("--format", default=DEFAULT_FORMAT, choices=["auto", "json", "jsonl"], help="Source format")
    parser.add_argument("--track-kind", default=DEFAULT_TRACK_KIND, choices=["auto", "json", "jsonl", "log"], help="Tracked file kind")
    parser.add_argument("--track-state-dir", help=f"Override track state directory (default: {DEFAULT_TRACK_STATE_DIR})")
    parser.add_argument("--reset-track", action="store_true", help="Replace the saved baseline for --track with the current file")
    parser.add_argument("--ignore-path", help="Comma-separated JSON path prefixes to ignore in --track json mode")
    parser.add_argument("--ignore-line", help="Comma-separated regex patterns to ignore in --track log/jsonl mode")
    parser.add_argument("--no-advance", action="store_true", help="Do not move the saved baseline after reporting a tracked diff")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Intent step count, 3-7")
    parser.add_argument("--processing-provider", "--pp", help="Single AI provider used for semantic summary, e.g. gemini or pi")
    parser.add_argument("--provider-chain", default=DEFAULT_PROVIDER_CHAIN, help="Provider chain for nx-cognize")
    parser.add_argument("--state-file", help="Override nx-cognize provider state cache path")
    parser.add_argument("--preflight-timeout", type=int, default=DEFAULT_PREFLIGHT_TIMEOUT, help="Preflight timeout in seconds")
    parser.add_argument("--runtime-timeout", type=int, default=DEFAULT_RUNTIME_TIMEOUT, help="Runtime timeout in seconds")
    parser.add_argument("--timezone", default="Europe/Moscow", help="Timezone for date filtering (default: Europe/Moscow)")
    parser.add_argument("--pretty", action="store_true", help="Render a human-friendly terminal view instead of JSON")
    parser.add_argument("--output", "-o", help="Write JSON or pretty text to file instead of stdout")
    parser.add_argument("--version", action="store_true", help="Show version")
    return parser.parse_args()


def emit_error(message: str) -> None:
    print(message, file=sys.stderr)


def resolve_source_provider_spec(single_provider: Optional[str], providers_spec: str) -> str:
    if single_provider and providers_spec != "all":
        raise RuntimeError("use either --harness-provider/--hp or --providers, not both")
    return single_provider or providers_spec


def resolve_processing_provider_spec(processing_provider: Optional[str], provider_chain: str) -> str:
    if processing_provider and provider_chain != DEFAULT_PROVIDER_CHAIN:
        raise RuntimeError("use either --processing-provider or --provider-chain, not both")
    return processing_provider or provider_chain


def load_default_processing_chain(base_dir: Path) -> List[str]:
    providers_path = (base_dir.parent / "nx-cognize" / "providers.json").resolve()
    with open(providers_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    default_chain = payload.get("default_chain") or []
    return [item for item in default_chain if isinstance(item, str)]


def resolve_effective_processing_chain(
    base_dir: Path,
    processing_provider: Optional[str],
    provider_chain: str,
    harness_provider: str,
) -> str:
    explicit = resolve_processing_provider_spec(processing_provider, provider_chain)
    if processing_provider or provider_chain != DEFAULT_PROVIDER_CHAIN or not harness_provider:
        return explicit

    default_chain = load_default_processing_chain(base_dir)
    filtered = [item for item in default_chain if item != harness_provider]
    if filtered:
        return ",".join(filtered)
    return explicit


def list_sessions_by_date(
    date_filter: str,
    project_path: Optional[str],
    providers: str,
    providers_config: Optional[str],
    timezone: str,
    base_dir: Path,
) -> Dict[str, Any]:
    """List sessions filtered by date using nx-collect."""
    collect_path = (base_dir.parent / "nx-collect" / "nx-collect").resolve()
    if not collect_path.exists():
        raise RuntimeError("nx-collect wrapper is not available")

    command: List[str] = [
        str(collect_path),
        "--date", date_filter,
        "--providers", providers,
        "--cognize-provider-chain", "local",
        "--timezone", timezone,
    ]
    if project_path:
        command.extend(["--project", project_path])
    if providers_config:
        command.extend(["--providers-config", providers_config])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("nx-collect timed out after 120s") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"nx-collect exited with code {completed.returncode}"
        raise RuntimeError(detail)

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"nx-collect returned invalid JSON: {exc}") from exc


def resolve_latest_project_session(
    project_path: str,
    providers: str,
    providers_config: Optional[str],
    base_dir: Path,
) -> Dict[str, str]:
    collect_path = (base_dir.parent / "nx-collect" / "nx-collect").resolve()
    if not collect_path.exists():
        raise RuntimeError("nx-collect wrapper is not available")

    command: List[str] = [
        str(collect_path),
        "--latest",
        "--project",
        project_path,
        "--providers",
        providers,
        "--cognize-provider-chain",
        "local",
    ]
    if providers_config:
        command.extend(["--providers-config", providers_config])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("nx-collect project lookup timed out after 120s") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"nx-collect exited with code {completed.returncode}"
        raise RuntimeError(detail)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"nx-collect returned invalid JSON: {exc}") from exc

    latest = payload.get("latest")
    if not isinstance(latest, dict) or not latest.get("path"):
        raise RuntimeError("nx-collect did not find a latest session for this project")
    return {
        "path": str(Path(str(latest["path"])).expanduser()),
        "provider": str(latest.get("provider") or ""),
    }


def invoke_cognize(
    *,
    base_dir: Path,
    input_path: Path,
    prompt_id: str,
    provider_chain: str,
    source_format: str,
    max_bullets: int,
    max_words_per_bullet: int,
    state_file: Optional[str],
    preflight_timeout: int,
    runtime_timeout: int,
) -> Dict[str, Any]:
    cognize_path = (base_dir.parent / "nx-cognize" / "nx-cognize").resolve()
    if not cognize_path.exists():
        raise RuntimeError("nx-cognize wrapper is not available")

    command: List[str] = [
        str(cognize_path),
        "--input",
        str(input_path),
        "--prompt-id",
        prompt_id,
        "--provider-chain",
        provider_chain,
        "--format",
        source_format,
        "--max-bullets",
        str(max_bullets),
        "--max-words-per-bullet",
        str(max_words_per_bullet),
        "--preflight-timeout",
        str(preflight_timeout),
        "--runtime-timeout",
        str(runtime_timeout),
    ]
    if state_file:
        command.extend(["--state-file", state_file])

    timeout_seconds = max(5, preflight_timeout + runtime_timeout + 5)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"nx-cognize timed out after {timeout_seconds}s") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "nx-cognize failed")

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc


def resolve_summary_source(selected_provider: str, deterministic: bool = False) -> str:
    if deterministic:
        return "deterministic"
    if selected_provider == "local":
        return "local_fallback"
    return "ai"


def build_result_meta(
    *,
    prompt_id: str,
    selected_provider: str,
    provider_attempts: List[Dict[str, Any]],
    deterministic: bool = False,
) -> Dict[str, Any]:
    return {
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "generated_at": now_utc_iso(),
        "prompt_id": prompt_id,
        "selected_provider": selected_provider,
        "processing_provider": selected_provider,
        "summary_source": resolve_summary_source(selected_provider, deterministic=deterministic),
        "provider_attempts": provider_attempts,
    }


def build_result(payload: Dict[str, Any], source_provider: str = "") -> Dict[str, Any]:
    meta = payload.get("meta") or {}
    source = payload.get("source") or {}
    summary = payload.get("summary") or {}
    selected_provider = str(meta.get("selected_provider") or "")

    return {
        "meta": build_result_meta(
            prompt_id=PROMPT_ID,
            selected_provider=selected_provider,
            provider_attempts=meta.get("provider_attempts") or [],
        ),
        "source": {
            "harness_provider": source_provider,
            "provider": source_provider,
            "format": source.get("format") or DEFAULT_FORMAT,
            "user_message_count": int(source.get("user_message_count") or 0),
            "first_user_message": summary.get("first_user_message") or "",
            "last_user_message": summary.get("last_user_message") or "",
        },
        "intent": {
            "title": summary.get("title") or "",
            "summary": summary.get("summary") or "",
            "steps": list(summary.get("intent_steps_ru") or summary.get("intent_bullets") or []),
            "key_topics": list(summary.get("key_topics") or []),
            "confidence": float(summary.get("confidence") or 0.0),
        },
    }


def validate_result(payload: Dict[str, Any]) -> None:
    required = {"meta", "source", "intent"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"missing result keys: {', '.join(sorted(missing))}")

    steps = payload["intent"].get("steps")
    if not isinstance(steps, list) or len(steps) < 3 or len(steps) > 7:
        raise ValueError("intent.steps must contain 3-7 items")


def has_explicit_flag(raw_args: List[str], flag: str) -> bool:
    return any(item == flag or item.startswith(f"{flag}=") for item in raw_args)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_space(value: Any, limit: int = 200) -> str:
    if not isinstance(value, str):
        value = str(value)
    normalized = " ".join(value.replace("\u00a0", " ").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip()


def parse_csv_items(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def compile_regex_list(raw_value: Optional[str]) -> List[Pattern[str]]:
    patterns: List[Pattern[str]] = []
    for item in parse_csv_items(raw_value):
        try:
            patterns.append(re.compile(item))
        except re.error as exc:
            raise ValueError(f"invalid --ignore-line regex {item!r}: {exc}") from exc
    return patterns


def canonicalize_track_path(path_value: str) -> Path:
    return Path(path_value).expanduser().resolve()


def resolve_track_state_dir(override: Optional[str]) -> Path:
    return Path(override or DEFAULT_TRACK_STATE_DIR).expanduser()


def detect_track_kind(track_path: Path, requested_kind: str) -> str:
    if requested_kind != DEFAULT_TRACK_KIND:
        return requested_kind

    suffix = track_path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".log", ".txt"}:
        return "log"
    raise ValueError("could not detect tracked file kind; use --track-kind json|jsonl|log")


def track_state_file_path(track_state_dir: Path, track_path: Path) -> Path:
    digest = hashlib.sha256(str(track_path).encode("utf-8")).hexdigest()[:16]
    return track_state_dir / f"{digest}.json"


def load_track_state(state_path: Path) -> Optional[Dict[str, Any]]:
    if not state_path.exists():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise TrackStateError(f"invalid track state JSON: {state_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TrackStateError(f"invalid track state payload: {state_path}")
    if int(payload.get("version") or 0) != TRACK_STATE_VERSION:
        raise TrackStateError(f"unsupported track state version in {state_path}")
    if not isinstance(payload.get("path"), str) or not payload.get("path"):
        raise TrackStateError(f"missing path in track state: {state_path}")
    if payload.get("kind") not in {"json", "jsonl", "log"}:
        raise TrackStateError(f"invalid kind in track state: {state_path}")
    return payload


def save_track_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_file_identity(path: Path) -> Dict[str, Any]:
    stat_result = path.stat()
    return {
        "device": int(stat_result.st_dev),
        "inode": int(stat_result.st_ino),
        "size": int(stat_result.st_size),
        "mtime_ns": int(stat_result.st_mtime_ns),
    }


def count_text_lines(path: Path) -> int:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def compute_tail_fingerprint(path: Path, limit: int = 4096) -> str:
    with open(path, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        data = handle.read()
    return hashlib.sha256(data).hexdigest()


def render_scalar(value: Any, limit: int = 80) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit].rstrip() + "..."


def is_numeric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def flatten_json_value(value: Any, prefix: str = "", result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if result is None:
        result = {}

    if isinstance(value, dict):
        if not value:
            result[prefix or "$"] = {}
            return result
        for key in sorted(value.keys()):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flatten_json_value(value[key], child_prefix, result)
        return result

    if isinstance(value, list):
        if not value:
            result[prefix or "$"] = []
            return result
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flatten_json_value(item, child_prefix, result)
        return result

    result[prefix or "$"] = value
    return result


def is_ignored_json_path(path_value: str, prefixes: List[str]) -> bool:
    for prefix in prefixes:
        if path_value == prefix:
            return True
        if path_value.startswith(f"{prefix}.") or path_value.startswith(f"{prefix}["):
            return True
    return False


def dedupe_texts(items: Iterable[str], limit: Optional[int] = None) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
        if limit is not None and len(result) >= limit:
            break
    return result


def collect_jsonl_fragments(value: Any, results: List[str], prefix: str = "") -> None:
    if len(results) >= 8:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if len(results) >= 8:
                break
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (str, int, float, bool)) or item is None:
                results.append(normalize_space(f"{child_prefix} {render_scalar(item, 48)}", 120))
            elif isinstance(item, (dict, list)):
                collect_jsonl_fragments(item, results, child_prefix)
        return
    if isinstance(value, list):
        for index, item in enumerate(value[:6]):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            if isinstance(item, (str, int, float, bool)) or item is None:
                results.append(normalize_space(f"{child_prefix} {render_scalar(item, 48)}", 120))
            else:
                collect_jsonl_fragments(item, results, child_prefix)
            if len(results) >= 8:
                break
        return
    if prefix:
        results.append(normalize_space(f"{prefix} {render_scalar(value, 48)}", 120))


def build_json_state(track_path: Path, observed_at: str, full_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": TRACK_STATE_VERSION,
        "path": str(track_path),
        "kind": "json",
        "baseline_at": observed_at,
        "file_identity": build_file_identity(track_path),
        "line_count": count_text_lines(track_path),
        "json_snapshot": full_snapshot,
    }


def build_stream_state(track_path: Path, kind: str, observed_at: str) -> Dict[str, Any]:
    identity = build_file_identity(track_path)
    return {
        "version": TRACK_STATE_VERSION,
        "path": str(track_path),
        "kind": kind,
        "baseline_at": observed_at,
        "file_identity": identity,
        "offset": int(identity["size"]),
        "line_count": count_text_lines(track_path),
        "tail_fingerprint": compute_tail_fingerprint(track_path),
    }


def build_track_baseline_state(track_path: Path, kind: str, observed_at: str) -> Dict[str, Any]:
    if kind == "json":
        with open(track_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        full_snapshot = flatten_json_value(payload)
        return build_json_state(track_path, observed_at, full_snapshot)
    return build_stream_state(track_path, kind, observed_at)


def build_json_track_payload(
    track_path: Path,
    previous_state: Dict[str, Any],
    ignore_paths: List[str],
    observed_at: str,
) -> Dict[str, Any]:
    with open(track_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    full_snapshot = flatten_json_value(payload)
    previous_snapshot = dict(previous_state.get("json_snapshot") or {})
    filtered_previous = {
        path_value: value
        for path_value, value in previous_snapshot.items()
        if not is_ignored_json_path(path_value, ignore_paths)
    }
    filtered_current = {
        path_value: value
        for path_value, value in full_snapshot.items()
        if not is_ignored_json_path(path_value, ignore_paths)
    }

    added_paths = sorted(set(filtered_current) - set(filtered_previous))
    removed_paths = sorted(set(filtered_previous) - set(filtered_current))
    changed_paths = sorted(
        path_value
        for path_value in set(filtered_current).intersection(filtered_previous)
        if filtered_current[path_value] != filtered_previous[path_value]
    )

    events: List[str] = []
    if added_paths:
        events.append(f"added paths {len(added_paths)}")
        for path_value in added_paths[:6]:
            events.append(f"добавлено поле {path_value} {render_scalar(filtered_current[path_value], 48)}")
    if removed_paths:
        events.append(f"removed paths {len(removed_paths)}")
        for path_value in removed_paths[:6]:
            events.append(f"удалено поле {path_value}")
    if changed_paths:
        events.append(f"changed paths {len(changed_paths)}")
        for path_value in changed_paths[:8]:
            before = filtered_previous[path_value]
            after = filtered_current[path_value]
            if is_numeric_value(before) and is_numeric_value(after):
                delta = after - before
                events.append(
                    f"изменено число {path_value} {render_scalar(before, 24)} -> {render_scalar(after, 24)} delta {delta:+g}"
                )
            else:
                events.append(
                    f"изменено поле {path_value} {render_scalar(before, 24)} -> {render_scalar(after, 24)}"
                )

    raw_changed = previous_snapshot != full_snapshot
    next_state = build_json_state(track_path, observed_at, full_snapshot)
    status = "changed" if events else "no_material_changes"
    return {
        "path": str(track_path),
        "kind": "json",
        "baseline_at": str(previous_state.get("baseline_at") or observed_at),
        "observed_at": observed_at,
        "events": dedupe_texts(events, limit=TRACK_EVENT_LIMIT),
        "stats": {
            "status": status,
            "raw_changed": raw_changed,
            "added_paths": len(added_paths),
            "removed_paths": len(removed_paths),
            "changed_paths": len(changed_paths),
            "ignored_path_prefixes": len(ignore_paths),
        },
        "next_state": next_state,
    }


def read_stream_delta(track_path: Path, previous_state: Dict[str, Any]) -> Tuple[List[str], bool, bool]:
    current_identity = build_file_identity(track_path)
    previous_identity = previous_state.get("file_identity") or {}
    previous_offset = int(previous_state.get("offset") or 0)
    rotated = (
        current_identity["inode"] != int(previous_identity.get("inode") or -1)
        or current_identity["device"] != int(previous_identity.get("device") or -1)
    )
    truncated = (not rotated) and current_identity["size"] < previous_offset
    start_offset = 0 if rotated or truncated else previous_offset

    with open(track_path, "rb") as handle:
        handle.seek(start_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    return text.splitlines(), rotated, truncated


def summarize_stream_line(raw_line: str, kind: str) -> str:
    normalized = normalize_space(raw_line, 160)
    if kind != "jsonl":
        return normalized
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        return normalized

    fragments: List[str] = []
    collect_jsonl_fragments(payload, fragments)
    if not fragments:
        return normalized
    return normalize_space(" · ".join(fragments), 160)


def build_stream_signal_counts(lines: Iterable[str]) -> Dict[str, int]:
    counts = {key: 0 for key in STREAM_SIGNAL_PATTERNS}
    for line in lines:
        for key, pattern in STREAM_SIGNAL_PATTERNS.items():
            if pattern.search(line):
                counts[key] += 1
    return counts


def build_stream_track_payload(
    track_path: Path,
    kind: str,
    previous_state: Dict[str, Any],
    ignore_patterns: List[Pattern[str]],
    observed_at: str,
) -> Dict[str, Any]:
    raw_lines, rotated, truncated = read_stream_delta(track_path, previous_state)
    kept_lines = [
        line for line in raw_lines
        if normalize_space(line) and not any(pattern.search(line) for pattern in ignore_patterns)
    ]
    summaries = dedupe_texts(
        [summarize_stream_line(line, kind) for line in kept_lines],
        limit=TRACK_STREAM_SAMPLE_LIMIT,
    )
    signal_counts = build_stream_signal_counts(kept_lines)

    events: List[str] = []
    if rotated or truncated:
        events.append("обнаружена ротация файла")
    if kept_lines:
        events.append(f"appended lines {len(raw_lines)}")
    if kind == "jsonl" and kept_lines:
        events.append(f"new records {len(kept_lines)}")
    if signal_counts["error_lines"]:
        events.append(f"error lines {signal_counts['error_lines']}")
    if signal_counts["warn_lines"]:
        events.append(f"warning lines {signal_counts['warn_lines']}")
    if signal_counts["timeout_lines"]:
        events.append(f"timeout lines {signal_counts['timeout_lines']}")
    if signal_counts["retry_lines"]:
        events.append(f"retry lines {signal_counts['retry_lines']}")
    if signal_counts["auth_lines"]:
        events.append(f"auth lines {signal_counts['auth_lines']}")
    if signal_counts["queue_lines"]:
        events.append(f"queue lines {signal_counts['queue_lines']}")
    for snippet in summaries:
        events.append(f"новая строка {snippet}")

    next_state = build_stream_state(track_path, kind, observed_at)
    raw_changed = bool(raw_lines or rotated or truncated)
    status = "changed" if events else "no_material_changes"
    return {
        "path": str(track_path),
        "kind": kind,
        "baseline_at": str(previous_state.get("baseline_at") or observed_at),
        "observed_at": observed_at,
        "events": dedupe_texts(events, limit=TRACK_EVENT_LIMIT),
        "stats": {
            "status": status,
            "raw_changed": raw_changed,
            "appended_lines": len(raw_lines),
            "material_lines": len(kept_lines),
            "ignored_lines": max(0, len(raw_lines) - len(kept_lines)),
            "rotation_detected": rotated or truncated,
            "parseable_lines": len(kept_lines) if kind == "jsonl" else 0,
            **signal_counts,
        },
        "next_state": next_state,
    }


def build_track_payload(
    track_path: Path,
    kind: str,
    previous_state: Dict[str, Any],
    ignore_paths: List[str],
    ignore_patterns: List[Pattern[str]],
    observed_at: str,
) -> Dict[str, Any]:
    if Path(str(previous_state["path"])).resolve() != track_path:
        raise TrackStateError("track state path mismatch; use --reset-track")
    if str(previous_state.get("kind") or "") != kind:
        raise TrackStateError("track kind mismatch; use --reset-track")

    if kind == "json":
        return build_json_track_payload(track_path, previous_state, ignore_paths, observed_at)
    return build_stream_track_payload(track_path, kind, previous_state, ignore_patterns, observed_at)


def build_track_event_records(track_payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"role": "user", "content": event} for event in track_payload["events"]]


def write_track_event_file(records: List[Dict[str, str]]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
    temp_path = Path(handle.name)
    try:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
    finally:
        handle.close()
    return temp_path


def build_track_result_from_cognitive(track_payload: Dict[str, Any], cognitive_payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = cognitive_payload.get("meta") or {}
    summary = cognitive_payload.get("summary") or {}
    selected_provider = str(meta.get("selected_provider") or "")

    return {
        "meta": build_result_meta(
            prompt_id=TRACK_PROMPT_ID,
            selected_provider=selected_provider,
            provider_attempts=meta.get("provider_attempts") or [],
        ),
        "source": {
            "path": track_payload["path"],
            "kind": track_payload["kind"],
            "baseline_at": track_payload["baseline_at"],
            "observed_at": track_payload["observed_at"],
        },
        "change": {
            "summary": summary.get("summary") or "",
            "steps": list(summary.get("intent_steps_ru") or summary.get("intent_bullets") or []),
            "stats": track_payload["stats"],
            "confidence": float(summary.get("confidence") or 0.0),
        },
    }


def build_deterministic_track_result(
    *,
    track_path: Path,
    kind: str,
    baseline_at: str,
    observed_at: str,
    summary_text: str,
    stats: Dict[str, Any],
    steps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "meta": build_result_meta(
            prompt_id=TRACK_PROMPT_ID,
            selected_provider="",
            provider_attempts=[],
            deterministic=True,
        ),
        "source": {
            "path": str(track_path),
            "kind": kind,
            "baseline_at": baseline_at,
            "observed_at": observed_at,
        },
        "change": {
            "summary": summary_text,
            "steps": list(steps or []),
            "stats": stats,
            "confidence": 1.0,
        },
    }


def validate_track_result(payload: Dict[str, Any]) -> None:
    required = {"meta", "source", "change"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"missing track result keys: {', '.join(sorted(missing))}")

    steps = payload["change"].get("steps")
    if not isinstance(steps, list) or len(steps) > 7:
        raise ValueError("change.steps must contain 0-7 items")

    source = payload["source"]
    if not all(isinstance(source.get(field), str) and source.get(field) for field in ("path", "kind", "baseline_at", "observed_at")):
        raise ValueError("track source requires path, kind, baseline_at, and observed_at")


def build_track_baseline_result(track_path: Path, kind: str, observed_at: str, summary_text: str, status: str) -> Dict[str, Any]:
    result = build_deterministic_track_result(
        track_path=track_path,
        kind=kind,
        baseline_at=observed_at,
        observed_at=observed_at,
        summary_text=summary_text,
        stats={"status": status},
    )
    validate_track_result(result)
    return result


def run_track_mode(args: argparse.Namespace, base_dir: Path, max_steps: int) -> Dict[str, Any]:
    track_path = canonicalize_track_path(args.track)
    if not track_path.exists():
        raise ValueError(f"tracked file not found: {track_path}")

    kind = detect_track_kind(track_path, args.track_kind)
    ignore_paths = parse_csv_items(args.ignore_path)
    ignore_patterns = compile_regex_list(args.ignore_line)
    state_dir = resolve_track_state_dir(args.track_state_dir)
    state_path = track_state_file_path(state_dir, track_path)
    observed_at = now_utc_iso()

    if args.reset_track:
        next_state = build_track_baseline_state(track_path, kind, observed_at)
        save_track_state(state_path, next_state)
        return build_track_baseline_result(track_path, kind, observed_at, "Базовая точка обновлена.", "baseline_reset")

    previous_state = load_track_state(state_path)
    if previous_state is None:
        next_state = build_track_baseline_state(track_path, kind, observed_at)
        save_track_state(state_path, next_state)
        return build_track_baseline_result(track_path, kind, observed_at, "Базовая точка сохранена.", "baseline_created")

    track_payload = build_track_payload(
        track_path=track_path,
        kind=kind,
        previous_state=previous_state,
        ignore_paths=ignore_paths,
        ignore_patterns=ignore_patterns,
        observed_at=observed_at,
    )

    if track_payload["stats"]["status"] == "no_material_changes":
        if track_payload["stats"].get("raw_changed") and not args.no_advance:
            save_track_state(state_path, track_payload["next_state"])
        result = build_deterministic_track_result(
            track_path=track_path,
            kind=kind,
            baseline_at=track_payload["baseline_at"],
            observed_at=track_payload["observed_at"],
            summary_text="Содержательных изменений нет.",
            stats=track_payload["stats"],
        )
        validate_track_result(result)
        return result

    temp_input: Optional[Path] = None
    try:
        temp_input = write_track_event_file(build_track_event_records(track_payload))
        cognitive_payload = invoke_cognize(
            base_dir=base_dir,
            input_path=temp_input,
            prompt_id=TRACK_PROMPT_ID,
            provider_chain=resolve_effective_processing_chain(
                base_dir=base_dir,
                processing_provider=args.processing_provider,
                provider_chain=args.provider_chain,
                harness_provider="",
            ),
            source_format="jsonl",
            max_bullets=max_steps,
            max_words_per_bullet=TRACK_MAX_WORDS_PER_BULLET,
            state_file=args.state_file,
            preflight_timeout=args.preflight_timeout,
            runtime_timeout=args.runtime_timeout,
        )
        result = build_track_result_from_cognitive(track_payload, cognitive_payload)
        validate_track_result(result)
        if not args.no_advance:
            save_track_state(state_path, track_payload["next_state"])
        return result
    finally:
        if temp_input is not None:
            temp_input.unlink(missing_ok=True)


def render_sessions_pretty(payload: Dict[str, Any]) -> str:
    """Render sessions list in human-friendly format."""
    sessions = payload.get("sessions", [])
    query = payload.get("query", {})
    date_filter = query.get("date_filter", "unknown")

    date_labels = {
        "today": "сегодня",
        "yesterday": "вчера",
        "week": "неделю",
    }
    label = date_labels.get(date_filter, date_filter)

    lines = [f"📋 Сессии за {label} ({len(sessions)})"]
    lines.append("━" * 40)
    lines.append("")

    for session in sessions:
        provider = session.get("provider", "?")
        modified = session.get("modified_human", "?")
        path = session.get("path", "?")
        activity = session.get("activity_state", "unknown")

        activity_icons = {"live": "🟢", "active": "🟡", "idle": "⚪"}
        icon = activity_icons.get(activity, "⚪")

        lines.append(f"{icon} {provider} · {modified}")
        lines.append(f"   {path}")
        lines.append("")

    return "\n".join(lines)


def render_pretty(payload: Dict[str, Any]) -> str:
    meta = payload["meta"]
    source = payload["source"]
    intent = payload["intent"]
    lines = [
        "🧭 Вектор намерений",
    ]
    harness_provider = str(source.get("harness_provider") or "").strip()
    processing_provider = str(meta.get("processing_provider") or "").strip()
    if harness_provider or processing_provider:
        lines.append(
            f"🧩 harness: {harness_provider or '-'} · processing: {processing_provider or '-'}"
        )
    summary = str(intent.get("summary") or "").strip()
    if summary:
        lines.extend([
            f"📝 {summary}",
            "",
        ])
    else:
        lines.append("")
    for index, step in enumerate(intent["steps"]):
        lines.append(f"{STEP_NUMERALS[index]} {step}")
    return "\n".join(lines)


def render_track_pretty(payload: Dict[str, Any]) -> str:
    source = payload["source"]
    change = payload["change"]
    stats = change.get("stats") or {}
    status = str(stats.get("status") or "")

    if status in {"baseline_created", "baseline_reset"}:
        lines = [
            "🧷 Базовая точка",
            f"📄 {source['path']}",
            f"🕒 {source['observed_at']}",
            f"📝 {change['summary']}",
        ]
        return "\n".join(lines)

    lines = [
        "🔎 Изменения файла",
        f"📄 {source['path']}",
        f"🕒 {source['baseline_at']} -> {source['observed_at']}",
    ]

    stat_parts: List[str] = []
    if source["kind"] == "json":
        stat_parts.append(f"+{int(stats.get('added_paths') or 0)} добавлено")
        stat_parts.append(f"-{int(stats.get('removed_paths') or 0)} удалено")
        stat_parts.append(f"~{int(stats.get('changed_paths') or 0)} изменено")
    else:
        stat_parts.append(f"+{int(stats.get('appended_lines') or 0)} строк")
        ignored_lines = int(stats.get("ignored_lines") or 0)
        if ignored_lines:
            stat_parts.append(f"шум {ignored_lines}")
        stat_parts.append(f"ротация: {'да' if stats.get('rotation_detected') else 'нет'}")
    lines.append(f"📈 {' · '.join(stat_parts)}")
    lines.append("")
    lines.append(f"📝 {change['summary']}")

    steps = list(change.get("steps") or [])
    if steps:
        lines.append("")
        for index, step in enumerate(steps):
            lines.append(f"{STEP_NUMERALS[index]} {step}")
    return "\n".join(lines)


def write_output(rendered: str, output_path: Optional[str]) -> None:
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
    raw_args = sys.argv[1:]
    args = parse_args()
    if args.version:
        print(TOOL_VERSION)
        return 0

    effective_max_steps = args.max_steps
    if args.track and not has_explicit_flag(raw_args, "--max-steps"):
        effective_max_steps = DEFAULT_TRACK_MAX_STEPS

    if effective_max_steps < 3 or effective_max_steps > 7:
        emit_error("--max-steps must be in range 3..7")
        return 2
    if args.preflight_timeout < 1 or args.runtime_timeout < 1:
        emit_error("timeouts must be positive integers")
        return 2
    if args.harness_provider and not args.project and not args.date:
        emit_error("--harness-provider/--hp can be used only together with --project")
        return 2
    if args.processing_provider and args.processing_provider not in {"qwen", "gemini", "claude", "pi", "local"}:
        emit_error("--processing-provider must be one of: qwen, gemini, claude, pi, local")
        return 2

    has_date = bool(args.date)
    has_input = bool(args.input)
    has_project = bool(args.project)
    has_track = bool(args.track)

    if args.reset_track and not has_track:
        emit_error("--reset-track can be used only together with --track")
        return 2
    if args.no_advance and not has_track:
        emit_error("--no-advance can be used only together with --track")
        return 2
    if (args.track_kind != DEFAULT_TRACK_KIND or args.track_state_dir or args.ignore_path or args.ignore_line) and not has_track:
        emit_error("--track-kind, --track-state-dir, --ignore-path, and --ignore-line require --track")
        return 2
    if has_track and (has_input or has_project or has_date):
        emit_error("--track cannot be used together with --input, --project, or --date")
        return 2

    if has_date:
        if has_input:
            emit_error("--date cannot be used with --input")
            return 2
    else:
        if sum(1 for value in (has_input, has_project, has_track) if value) != 1:
            emit_error("exactly one selector is required: --input/-i, --project, or --track")
            return 2

    base_dir = Path(__file__).resolve().parent

    if args.date:
        try:
            provider_spec = resolve_source_provider_spec(args.harness_provider, args.providers)
            result = list_sessions_by_date(
                date_filter=args.date,
                project_path=args.project,
                providers=provider_spec,
                providers_config=args.providers_config,
                timezone=args.timezone,
                base_dir=base_dir,
            )
        except RuntimeError as exc:
            emit_error(str(exc))
            return 3

        rendered = render_sessions_pretty(result) if args.pretty else json.dumps(result, ensure_ascii=False, indent=2)
        write_output(rendered, args.output)
        return 0

    if has_track:
        try:
            track_result = run_track_mode(args, base_dir, effective_max_steps)
        except json.JSONDecodeError as exc:
            emit_error(str(exc))
            return 4
        except TrackStateError as exc:
            emit_error(str(exc))
            return 4
        except ValueError as exc:
            emit_error(str(exc))
            return 2
        except RuntimeError as exc:
            emit_error(str(exc))
            return 3

        rendered = render_track_pretty(track_result) if args.pretty else json.dumps(track_result, ensure_ascii=False, indent=2)
        write_output(rendered, args.output)
        return 0

    source_provider = ""
    if args.project:
        try:
            provider_spec = resolve_source_provider_spec(args.harness_provider, args.providers)
            resolved = resolve_latest_project_session(
                project_path=args.project,
                providers=provider_spec,
                providers_config=args.providers_config,
                base_dir=base_dir,
            )
            input_path = Path(resolved["path"])
            source_provider = resolved["provider"]
        except RuntimeError as exc:
            emit_error(str(exc))
            return 3
    else:
        input_path = Path(args.input).expanduser()

    if not input_path.exists():
        emit_error(f"input file not found: {input_path}")
        return 2

    try:
        cognitive_payload = invoke_cognize(
            base_dir=base_dir,
            input_path=input_path,
            prompt_id=PROMPT_ID,
            provider_chain=resolve_effective_processing_chain(
                base_dir=base_dir,
                processing_provider=args.processing_provider,
                provider_chain=args.provider_chain,
                harness_provider=source_provider,
            ),
            source_format=args.format,
            max_bullets=effective_max_steps,
            max_words_per_bullet=5,
            state_file=args.state_file,
            preflight_timeout=args.preflight_timeout,
            runtime_timeout=args.runtime_timeout,
        )
        result = build_result(cognitive_payload, source_provider=source_provider)
        validate_result(result)
    except RuntimeError as exc:
        emit_error(str(exc))
        return 3
    except (ValueError, TypeError) as exc:
        emit_error(str(exc))
        return 4

    rendered = render_pretty(result) if args.pretty else json.dumps(result, ensure_ascii=False, indent=2)
    write_output(rendered, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
