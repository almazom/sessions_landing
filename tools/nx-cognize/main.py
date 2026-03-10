#!/usr/bin/env python3
"""Isolated cognitive CLI for JSON and JSONL files."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


TOOL_NAME = "nx-cognize"
TOOL_VERSION = "0.2.0"
DEFAULT_FORMATS = {"json", "jsonl", "auto"}
DEFAULT_PROMPT_ID = "session-summary"
PROMPT_FILES = {
    "session-summary": "session-summary.yaml",
    "intent-vector-ru": "intent-vector-ru.yaml",
}
MIN_BULLETS = 3
MAX_BULLETS = 7
MIN_WORDS_PER_BULLET = 3
MAX_WORDS_PER_BULLET = 5
WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_./:-]*")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "i", "if", "in", "into", "is", "it", "of", "on", "or", "so", "that",
    "the", "this", "to", "we", "with",
    "а", "без", "бы", "в", "во", "все", "да", "для", "до", "его", "ее",
    "если", "же", "за", "и", "из", "или", "их", "к", "как", "когда", "ли",
    "мне", "мы", "на", "не", "нет", "но", "о", "он", "она", "они", "по",
    "под", "при", "про", "с", "со", "так", "то", "ты", "у", "что", "это", "я"
}
TEXT_KEYS = {
    "content", "description", "details", "input", "instruction", "message",
    "prompt", "summary", "text"
}
NOISE_PATTERNS = (
    "AGENTS.md instructions",
    "<INSTRUCTIONS>",
    "<environment_context>",
    "Codex Global Instructions",
    "subagent_notification",
)
SEMANTIC_INTENT_RULES = [
    (re.compile(r"(фильтр.*сегодня|today filter|today\b)", re.IGNORECASE), "починить фильтр сегодня"),
    (re.compile(r"(sort|sorting|сортиров|active session|live session|latest session)", re.IGNORECASE), "исправить latest сортировку"),
    (re.compile(r"(latest.*card|card.*latest|карточк.*latest|latest карточк)", re.IGNORECASE), "исправить latest карточку"),
    (re.compile(r"(полный путь|path to file|full path|path-only|путь к файлу)", re.IGNORECASE), "показать полный путь"),
    (re.compile(r"(playwright|e2e|published flow|published url|smoke pipeline|login pipeline)", re.IGNORECASE), "проверить published flow"),
    (re.compile(r"(contract-first|contract first|manifest|schema|cli contract|isolated cli)", re.IGNORECASE), "усилить contract-first cli"),
    (re.compile(r"(aura|profile|профайл|аура|agents\\.md|memory card|\\.memory|documentation layer)", re.IGNORECASE), "разложить docs по слоям"),
    (re.compile(r"(memory|memery)", re.IGNORECASE), "уточнить memory слой"),
    (re.compile(r"(publish|published|deploy|republish|start_published)", re.IGNORECASE), "перепроверить published deploy"),
    (re.compile(r"(logo|логотип|gemini cli|qwen cli|claude code|pi mino|pi mini)", re.IGNORECASE), "обновить provider logos"),
    (re.compile(r"(gemini.*json|tmp folder|json vs jsonl|session-\\*\\.json)", re.IGNORECASE), "учесть gemini json сессии"),
    (re.compile(r"(intent|вектор намерений|semantic|cognitive layer)", re.IGNORECASE), "улучшить вектор намерений"),
    (re.compile(r"(nx-collect|latest jsonl|latest session|find latest|jsonl file)", re.IGNORECASE), "доработать cli latest"),
    (re.compile(r"(subagent|parallel|six providers|6 providers)", re.IGNORECASE), "параллельно искать latest"),
    (re.compile(r"(duration|длительност|started_at)", re.IGNORECASE), "показать длительность сессии"),
    (re.compile(r"(shell|bash|xargs|ls -lt|run each command|run each comand|find /home|confirm.*shell)", re.IGNORECASE), "проверить shell команды"),
    (re.compile(r"(reasoning|ризанинг|последний измененный файл|точка кодекс|rollout-)", re.IGNORECASE), "объяснить поиск latest"),
]


@dataclass
class ProviderAttempt:
    provider: str
    ok: bool
    stage: str
    detail: str
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "provider": self.provider,
            "ok": self.ok,
            "stage": self.stage,
            "detail": self.detail,
        }
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 2)
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cognitive summary over JSON or JSONL source files.")
    parser.add_argument("--input", "-i", required=True, help="Path to JSON or JSONL input file")
    parser.add_argument("--output", "-o", help="Write result JSON to file instead of stdout")
    parser.add_argument("--provider-chain", default="auto", help="Comma-separated providers or 'auto'")
    parser.add_argument(
        "--prompt-id",
        default=DEFAULT_PROMPT_ID,
        choices=sorted(PROMPT_FILES.keys()),
        help="Prompt catalog entry to use for the cognitive operation",
    )
    parser.add_argument("--state-file", help="Override provider state cache file path")
    parser.add_argument("--refresh-provider-health", action="store_true", help="Force parallel provider preflight refresh")
    parser.add_argument("--format", default="auto", choices=sorted(DEFAULT_FORMATS), help="Input format")
    parser.add_argument("--max-bullets", type=int, default=5, help="Intent bullet count, 3-7")
    parser.add_argument("--max-words-per-bullet", type=int, default=5, help="Words per bullet, 3-5")
    parser.add_argument("--preflight-timeout", type=int, default=45, help="Preflight timeout seconds")
    parser.add_argument("--runtime-timeout", type=int, default=600, help="Runtime timeout seconds")
    parser.add_argument("--version", action="store_true", help="Show version")
    return parser.parse_args()


def emit_error(message: str) -> None:
    print(message, file=sys.stderr)


def load_provider_config(base_dir: Path) -> Dict[str, Any]:
    with open(base_dir / "providers.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_prompt_spec(base_dir: Path, prompt_id: str) -> Dict[str, Any]:
    prompt_file = PROMPT_FILES.get(prompt_id)
    if not prompt_file:
        raise ValueError(f"unsupported prompt id: {prompt_id}")
    prompt_path = base_dir / "prompts" / prompt_file
    with open(prompt_path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict) or "template" not in payload:
        raise ValueError(f"invalid prompt file: {prompt_path}")
    return payload


def empty_provider_state() -> Dict[str, Any]:
    return {
        "updated_at": "",
        "providers": {},
    }


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso8601(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_seconds(value: Any) -> Optional[float]:
    timestamp = parse_iso8601(value)
    if timestamp is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())


def resolve_state_path(base_dir: Path, config: Dict[str, Any], override: Optional[str]) -> Path:
    if override:
        return Path(override).expanduser()
    cache_config = config.get("health_cache", {})
    state_file = cache_config.get("state_file", "provider-state.local.json")
    return (base_dir / state_file).resolve()


def load_provider_state(state_path: Path) -> Dict[str, Any]:
    if not state_path.exists():
        return empty_provider_state()
    with open(state_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return empty_provider_state()
    payload.setdefault("updated_at", "")
    payload.setdefault("providers", {})
    return payload


def save_provider_state(state_path: Path, state: Dict[str, Any]) -> None:
    state["updated_at"] = utcnow_iso()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_provider_chain(spec: str, config: Dict[str, Any]) -> List[str]:
    if spec == "auto":
        return list(config["default_chain"])
    chain = [item.strip() for item in spec.split(",") if item.strip()]
    if not chain:
        raise ValueError("provider chain cannot be empty")
    supported = set(config["providers"].keys())
    invalid = [item for item in chain if item not in supported]
    if invalid:
        raise ValueError(f"unsupported providers: {', '.join(invalid)}")
    return chain


def detect_format(path: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    if path.suffix.lower() == ".jsonl":
        return "jsonl"
    return "json"


def normalize_text(value: Any, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\u00a0", " ").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def is_noise_message(text: str) -> bool:
    if not text:
        return True
    return any(pattern in text for pattern in NOISE_PATTERNS)


def wrap_record(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"value": value}


def count_lines(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def load_records(path: Path, source_format: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    parse_errors = 0
    records: List[Dict[str, Any]] = []
    line_count = 0

    if source_format == "jsonl":
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line_count += 1
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
        line_count = count_lines(path)
        if isinstance(payload, list):
            for item in payload:
                records.append(wrap_record(item))
        elif isinstance(payload, dict):
            records.append(payload)
        else:
            records.append(wrap_record(payload))

    return records, {
        "line_count": line_count,
        "record_count": len(records),
        "parse_errors": parse_errors,
    }


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


def extract_user_messages(record: Dict[str, Any]) -> List[str]:
    messages: List[str] = []
    role = record.get("role")
    if role == "user":
        extract_strings(record.get("content"), messages)

    if record.get("type") == "user":
        if isinstance(record.get("message"), str):
            messages.append(normalize_text(record["message"]))
        elif isinstance(record.get("message"), dict):
            extract_strings(record["message"], messages)

    payload = record.get("payload")
    if isinstance(payload, dict):
        if payload.get("type") == "user_message":
            messages.append(normalize_text(payload.get("message")))
        if payload.get("type") == "message" and payload.get("role") == "user":
            extract_strings(payload.get("content"), messages)

    message = record.get("message")
    if isinstance(message, dict) and message.get("role") == "user":
        extract_strings(message.get("content"), messages)
    elif isinstance(message, str) and role == "user":
        messages.append(normalize_text(message))

    content = record.get("content")
    if role == "user":
        extract_strings(content, messages)

    cleaned = []
    for message_text in messages:
        normalized = normalize_text(message_text)
        if normalized and not is_noise_message(normalized):
            cleaned.append(normalized)
    return cleaned


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


def extract_words(text: str) -> List[str]:
    return WORD_PATTERN.findall(text)


def build_packet(records: List[Dict[str, Any]], stats: Dict[str, int]) -> Dict[str, Any]:
    user_messages: List[str] = []
    snippets: List[str] = []
    for record in records:
        user_messages.extend(extract_user_messages(record))
        extract_strings(record, snippets)

    unique_snippets = dedupe_texts(snippets)
    unique_user_messages = dedupe_texts(user_messages)

    stats["user_message_count"] = len(unique_user_messages)
    return {
        "stats": stats,
        "first_user_message": unique_user_messages[0] if unique_user_messages else "",
        "last_user_message": unique_user_messages[-1] if unique_user_messages else "",
        "user_messages": unique_user_messages[:24],
        "snippets": unique_snippets[:40],
    }


def render_prompt(
    prompt_spec: Dict[str, Any],
    packet: Dict[str, Any],
    max_bullets: int,
    max_words_per_bullet: int,
) -> str:
    payload = {
        "source_stats": packet["stats"],
        "first_user_message": packet["first_user_message"],
        "last_user_message": packet["last_user_message"],
        "user_messages": packet["user_messages"],
        "snippets": packet["snippets"][:18],
    }
    template = str(prompt_spec["template"])
    return (
        template
        .replace("__MAX_BULLETS__", str(max_bullets))
        .replace("__MAX_WORDS_PER_BULLET__", str(max_words_per_bullet))
        .replace("__SOURCE_PACKET_JSON__", json.dumps(payload, ensure_ascii=False))
    )


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped)
    return stripped.strip()


def extract_json_object(text: str) -> Dict[str, Any]:
    stripped = strip_code_fences(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def clamp_bullets(bullets: List[str], max_bullets: int, max_words_per_bullet: int) -> List[str]:
    compacted = []
    for bullet in bullets:
        words = extract_words(str(bullet))
        if not words:
            continue
        compacted.append(" ".join(words[:max_words_per_bullet]))
    compacted = [item for item in compacted if item]
    if len(compacted) < MIN_BULLETS:
        return compacted
    return compacted[:max_bullets]


def topic_keywords(texts: Iterable[str], limit: int = 5) -> List[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for word in extract_words(text.lower()):
            if len(word) <= 2 or word in STOPWORDS:
                continue
            counter[word] += 1
    return [word for word, _count in counter.most_common(limit)]


def summarize_intent_step(text: str, max_words_per_bullet: int) -> str:
    words = [
        word for word in extract_words(text)
        if len(word) > 1 and word.lower() not in STOPWORDS
    ]
    if not words:
        words = extract_words(text)
    return " ".join(words[:max_words_per_bullet])


def semantic_intent_step(text: str, max_words_per_bullet: int) -> str:
    normalized = " ".join(text.lower().split())
    for pattern, replacement in SEMANTIC_INTENT_RULES:
        if pattern.search(normalized):
            return replacement
    return summarize_intent_step(text, max_words_per_bullet)


def sample_intent_messages(messages: List[str], limit: int) -> List[str]:
    unique_messages = dedupe_texts(messages)
    if len(unique_messages) <= limit:
        return unique_messages

    sampled_messages: List[str] = []
    last_index = len(unique_messages) - 1
    for index in range(limit):
        sampled_index = round(index * last_index / (limit - 1))
        sampled_messages.append(unique_messages[sampled_index])
    return dedupe_texts(sampled_messages, limit=limit)


def local_intent_steps(packet: Dict[str, Any], max_bullets: int, max_words_per_bullet: int) -> List[str]:
    user_messages = packet["user_messages"]
    topic_list = topic_keywords(user_messages or packet["snippets"], limit=max_words_per_bullet)
    steps = [
        semantic_intent_step(message, max_words_per_bullet)
        for message in sample_intent_messages(user_messages, max_bullets)
    ]
    cleaned_steps = dedupe_texts([step for step in steps if step])

    while len(cleaned_steps) < MIN_BULLETS:
        filler = " ".join(topic_list[:max_words_per_bullet]) or "понять ход этой сессии"
        if filler not in cleaned_steps:
            cleaned_steps.append(filler)
        else:
            cleaned_steps.append(f"шаг {len(cleaned_steps) + 1} этой сессии")

    return cleaned_steps[:max_bullets]


def local_summary(
    packet: Dict[str, Any],
    prompt_id: str,
    max_bullets: int,
    max_words_per_bullet: int,
) -> Dict[str, Any]:
    first_message = packet["first_user_message"]
    last_message = packet["last_user_message"]
    user_messages = packet["user_messages"]
    intent_steps = local_intent_steps(packet, max_bullets, max_words_per_bullet)
    key_topics = topic_keywords(user_messages + packet["snippets"])
    title_candidates = user_messages[-3:] or [last_message, first_message]
    title_source = max(title_candidates, key=len, default="") or last_message or first_message or "JSONL cognitive session"
    title_words = extract_words(title_source)
    title = " ".join(title_words[:6]) or " ".join(key_topics[:4]) or "Вектор пользовательских намерений"
    if prompt_id == "intent-vector-ru":
        summary = (
            "Семантическая выжимка показывает, как шаг за шагом двигались пользовательские намерения."
            if user_messages else
            "Семантическая выжимка построена по доступным следам пользовательской сессии."
        )
    else:
        summary = (
            "This file centers on user-driven instructions extracted from the source log."
            if not user_messages else
            "The source log shows a user-guided session with a clear progression of intent."
        )
    return {
        "title": title,
        "summary": summary,
        "first_user_message": first_message,
        "last_user_message": last_message,
        "intent_bullets": intent_steps,
        "intent_steps_ru": intent_steps,
        "key_topics": key_topics,
        "confidence": 0.45,
    }


def validate_summary(summary: Dict[str, Any], max_bullets: int, max_words_per_bullet: int) -> Dict[str, Any]:
    required = [
        "title",
        "summary",
        "first_user_message",
        "last_user_message",
        "key_topics",
        "confidence",
    ]
    missing = [key for key in required if key not in summary]
    if missing:
        raise ValueError(f"missing summary keys: {', '.join(missing)}")

    raw_intent_steps = summary.get("intent_steps_ru")
    if raw_intent_steps is None:
        raw_intent_steps = summary.get("intent_bullets")
    normalized_steps = clamp_bullets(list(raw_intent_steps or []), max_bullets, max_words_per_bullet)

    normalized = {
        "title": normalize_text(summary["title"], 120),
        "summary": normalize_text(summary["summary"], 240).rstrip(".") + ".",
        "first_user_message": normalize_text(summary["first_user_message"], 280),
        "last_user_message": normalize_text(summary["last_user_message"], 280),
        "intent_bullets": normalized_steps,
        "intent_steps_ru": normalized_steps,
        "key_topics": [normalize_text(item, 48) for item in list(summary["key_topics"])[:6] if normalize_text(item, 48)],
        "confidence": max(0.0, min(1.0, float(summary["confidence"]))),
    }

    if len(normalized["intent_steps_ru"]) < MIN_BULLETS:
        raise ValueError("summary has fewer than 3 intent bullets")
    if normalized["summary"].endswith("..."):
        normalized["summary"] = normalized["summary"][:-3].rstrip() + "."
    return normalized


def fill_command(template: List[str], prompt: str) -> List[str]:
    return [part.replace("{prompt}", prompt) for part in template]


def run_command(command: List[str], timeout_seconds: int) -> Tuple[bool, str, float]:
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return False, "command not found", round((time.perf_counter() - started_at) * 1000, 2)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_seconds}s", round((time.perf_counter() - started_at) * 1000, 2)

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    combined = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    if completed.returncode != 0:
        return False, normalize_text(combined, 300) or f"exit code {completed.returncode}", duration_ms
    return True, combined.strip(), duration_ms


def update_state_from_preflight(
    provider_state: Dict[str, Any],
    provider_name: str,
    ok: bool,
    detail: str,
    duration_ms: float,
) -> None:
    provider_record = provider_state.setdefault("providers", {}).setdefault(provider_name, {})
    now = utcnow_iso()
    provider_record["last_preflight_at"] = now
    provider_record["last_preflight_ok"] = ok
    provider_record["last_preflight_detail"] = detail
    provider_record["last_preflight_latency_ms"] = duration_ms
    if ok:
        provider_record["last_available_at"] = now
        provider_record["last_available_latency_ms"] = duration_ms
        best_latency = provider_record.get("best_preflight_latency_ms")
        provider_record["best_preflight_latency_ms"] = duration_ms if best_latency is None else min(best_latency, duration_ms)
        provider_record["success_count"] = int(provider_record.get("success_count", 0)) + 1
    else:
        provider_record["last_failure_at"] = now
        provider_record["failure_count"] = int(provider_record.get("failure_count", 0)) + 1


def update_state_from_runtime(
    provider_state: Dict[str, Any],
    provider_name: str,
    ok: bool,
    detail: str,
    duration_ms: float,
) -> None:
    provider_record = provider_state.setdefault("providers", {}).setdefault(provider_name, {})
    now = utcnow_iso()
    provider_record["last_runtime_at"] = now
    provider_record["last_runtime_ok"] = ok
    provider_record["last_runtime_detail"] = detail
    provider_record["last_runtime_latency_ms"] = duration_ms
    if ok:
        provider_record["last_available_at"] = now


def run_preflight_probe(provider_name: str, config: Dict[str, Any], timeout_seconds: int) -> ProviderAttempt:
    spec = config["providers"][provider_name]
    ok, output, duration_ms = run_command(spec["preflight"], timeout_seconds)
    if not ok:
        return ProviderAttempt(provider_name, False, "preflight", output, duration_ms)
    if "ok" not in output.lower():
        return ProviderAttempt(provider_name, False, "preflight", "preflight did not return ok", duration_ms)
    return ProviderAttempt(provider_name, True, "preflight", "preflight passed", duration_ms)


def refresh_provider_health(
    chain: List[str],
    config: Dict[str, Any],
    provider_state: Dict[str, Any],
    timeout_seconds: int,
    force_refresh: bool,
) -> List[ProviderAttempt]:
    attempts: List[ProviderAttempt] = []
    cache_config = config.get("health_cache", {})
    refresh_after_seconds = int(cache_config.get("refresh_after_seconds", 300))
    probe_candidates = [provider for provider in chain if provider != "local"]
    providers_to_probe = []
    provider_order = {provider_name: index for index, provider_name in enumerate(chain)}

    for provider_name in probe_candidates:
        record = provider_state.get("providers", {}).get(provider_name, {})
        fresh_age = age_seconds(record.get("last_preflight_at"))
        is_fresh = fresh_age is not None and fresh_age <= refresh_after_seconds
        if force_refresh or not is_fresh:
            providers_to_probe.append(provider_name)

    if not providers_to_probe:
        return attempts

    max_workers = max(1, len(providers_to_probe))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(run_preflight_probe, provider_name, config, timeout_seconds): provider_name
            for provider_name in providers_to_probe
        }
        for future in concurrent.futures.as_completed(future_map):
            attempt = future.result()
            attempts.append(attempt)
            update_state_from_preflight(
                provider_state,
                attempt.provider,
                attempt.ok,
                attempt.detail,
                attempt.duration_ms or 0.0,
            )

    attempts.sort(key=lambda item: provider_order[item.provider])
    return attempts


def rank_runtime_chain(chain: List[str], provider_state: Dict[str, Any], config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    cache_config = config.get("health_cache", {})
    available_within_seconds = int(cache_config.get("prefer_recent_available_seconds", 3600))
    ranked: List[Tuple[Tuple[float, float, float, float], str]] = []
    available_providers: List[str] = []

    for static_index, provider_name in enumerate(chain):
        if provider_name == "local":
            continue

        record = provider_state.get("providers", {}).get(provider_name, {})
        last_preflight_ok = record.get("last_preflight_ok") is True
        last_available_age = age_seconds(record.get("last_available_at"))
        is_recently_available = (
            last_preflight_ok and
            last_available_age is not None and
            last_available_age <= available_within_seconds
        )
        if is_recently_available:
            available_providers.append(provider_name)

        latency_ms = (
            record.get("last_preflight_latency_ms")
            or record.get("best_preflight_latency_ms")
            or float("inf")
        )
        availability_bucket = 0 if is_recently_available else 1
        recent_age = last_available_age if last_available_age is not None else float("inf")
        ranked.append(((availability_bucket, latency_ms, recent_age, static_index), provider_name))

    ordered = [provider_name for _sort_key, provider_name in sorted(ranked)]
    if "local" in chain:
        ordered.append("local")
        if "local" not in available_providers:
            available_providers.append("local")
    return ordered, available_providers


def try_provider(
    provider_name: str,
    prompt: str,
    prompt_id: str,
    config: Dict[str, Any],
    runtime_timeout: int,
    max_bullets: int,
    max_words_per_bullet: int,
    packet: Dict[str, Any],
    provider_state: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[ProviderAttempt]]:
    attempts: List[ProviderAttempt] = []
    if provider_name == "local":
        summary = local_summary(packet, prompt_id, max_bullets, max_words_per_bullet)
        attempts.append(ProviderAttempt(provider_name, True, "local", "fallback summary generated"))
        update_state_from_runtime(provider_state, provider_name, True, "fallback summary generated", 0.0)
        return summary, attempts

    spec = config["providers"][provider_name]
    record = provider_state.get("providers", {}).get(provider_name, {})
    if record.get("last_preflight_ok") is not True:
        attempts.append(ProviderAttempt(provider_name, False, "runtime", "skipped runtime because latest preflight is not healthy"))
        return None, attempts

    ok, runtime_output, duration_ms = run_command(fill_command(spec["runtime"], prompt), runtime_timeout)
    if not ok:
        attempts.append(ProviderAttempt(provider_name, False, "runtime", runtime_output, duration_ms))
        update_state_from_runtime(provider_state, provider_name, False, runtime_output, duration_ms)
        return None, attempts

    try:
        payload = extract_json_object(runtime_output)
        summary = validate_summary(payload, max_bullets, max_words_per_bullet)
    except Exception as exc:
        detail = f"invalid json payload: {exc}"
        attempts.append(ProviderAttempt(provider_name, False, "runtime", detail, duration_ms))
        update_state_from_runtime(provider_state, provider_name, False, detail, duration_ms)
        return None, attempts

    attempts.append(ProviderAttempt(provider_name, True, "runtime", "runtime returned valid json", duration_ms))
    update_state_from_runtime(provider_state, provider_name, True, "runtime returned valid json", duration_ms)
    return summary, attempts


def build_result(
    input_path: Path,
    source_format: str,
    packet: Dict[str, Any],
    summary: Dict[str, Any],
    prompt_id: str,
    selected_provider: str,
    attempts: List[ProviderAttempt],
    runtime_chain: List[str],
    available_providers: List[str],
    state_path: Path,
) -> Dict[str, Any]:
    return {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prompt_id": prompt_id,
            "selected_provider": selected_provider,
            "provider_order": runtime_chain,
            "available_providers": available_providers,
            "provider_state_path": str(state_path),
            "provider_attempts": [attempt.to_dict() for attempt in attempts],
        },
        "source": {
            "path": str(input_path),
            "format": source_format,
            "line_count": packet["stats"]["line_count"],
            "record_count": packet["stats"]["record_count"],
            "parse_errors": packet["stats"]["parse_errors"],
            "user_message_count": packet["stats"]["user_message_count"],
        },
        "summary": summary,
    }


def write_output(result: Dict[str, Any], output_path: Optional[str]) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.write("\n")
    else:
        print(rendered)


def main() -> int:
    args = parse_args()
    if args.version:
        print(TOOL_VERSION)
        return 0

    if args.max_bullets < MIN_BULLETS or args.max_bullets > MAX_BULLETS:
        emit_error("[E200] INVALID_ARGUMENT: --max-bullets must be in range 3..7")
        return 2
    if args.max_words_per_bullet < MIN_WORDS_PER_BULLET or args.max_words_per_bullet > MAX_WORDS_PER_BULLET:
        emit_error("[E200] INVALID_ARGUMENT: --max-words-per-bullet must be in range 3..5")
        return 2

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        emit_error(f"[E201] INVALID_ARGUMENT: input file not found: {input_path}")
        return 2

    try:
        base_dir = Path(__file__).resolve().parent
        config = load_provider_config(Path(__file__).resolve().parent)
        prompt_spec = load_prompt_spec(base_dir, args.prompt_id)
        chain = resolve_provider_chain(args.provider_chain, config)
        source_format = detect_format(input_path, args.format)
        state_path = resolve_state_path(base_dir, config, args.state_file)
        provider_state = load_provider_state(state_path)
    except ValueError as exc:
        emit_error(f"[E202] INVALID_ARGUMENT: {exc}")
        return 2
    except Exception as exc:
        emit_error(f"[E500] INTERNAL_ERROR: failed to load provider config: {exc}")
        return 1

    try:
        records, stats = load_records(input_path, source_format)
        packet = build_packet(records, stats)
    except json.JSONDecodeError as exc:
        emit_error(f"[E400] PARSE_ERROR: {exc}")
        return 4
    except Exception as exc:
        emit_error(f"[E500] INTERNAL_ERROR: failed to load source: {exc}")
        return 1

    prompt = render_prompt(prompt_spec, packet, args.max_bullets, args.max_words_per_bullet)
    all_attempts: List[ProviderAttempt] = []
    preflight_attempts = refresh_provider_health(
        chain=chain,
        config=config,
        provider_state=provider_state,
        timeout_seconds=args.preflight_timeout,
        force_refresh=args.refresh_provider_health,
    )
    all_attempts.extend(preflight_attempts)
    runtime_chain, available_providers = rank_runtime_chain(chain, provider_state, config)

    for provider_name in runtime_chain:
        summary, attempts = try_provider(
            provider_name=provider_name,
            prompt=prompt,
            prompt_id=args.prompt_id,
            config=config,
            runtime_timeout=args.runtime_timeout,
            max_bullets=args.max_bullets,
            max_words_per_bullet=args.max_words_per_bullet,
            packet=packet,
            provider_state=provider_state,
        )
        all_attempts.extend(attempts)
        if summary is None:
            continue

        try:
            validated_summary = validate_summary(summary, args.max_bullets, args.max_words_per_bullet)
            save_provider_state(state_path, provider_state)
            result = build_result(
                input_path,
                source_format,
                packet,
                validated_summary,
                args.prompt_id,
                provider_name,
                all_attempts,
                runtime_chain,
                available_providers,
                state_path,
            )
            write_output(result, args.output)
            return 0
        except Exception as exc:
            all_attempts.append(ProviderAttempt(provider_name, False, "runtime", f"output validation failed: {exc}"))

    save_provider_state(state_path, provider_state)
    emit_error("[E300] PROVIDER_FAILURE: all providers failed")
    for attempt in all_attempts:
        emit_error(f" - {attempt.provider} [{attempt.stage}] ok={attempt.ok}: {attempt.detail}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
