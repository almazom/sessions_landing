#!/usr/bin/env python3
"""Safe ask-only local query CLI over one session artifact."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


TOOL_NAME = "nx-session-query"
TOOL_VERSION = "1.0.0"
DEFAULT_FORMAT = "auto"
DEFAULT_MAX_EVIDENCE_ITEMS = 3
QUESTION_NUMERALS = ["①", "②", "③", "④", "⑤"]
TEXT_KEYS = ("content", "message", "text", "description", "summary", "title", "prompt")
QUESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "artifact",
    "ask",
    "about",
    "be",
    "была",
    "было",
    "были",
    "быть",
    "как",
    "какая",
    "какие",
    "какой",
    "какую",
    "когда",
    "что",
    "это",
    "this",
    "what",
    "which",
    "with",
    "why",
    "where",
    "session",
    "сессии",
    "сессия",
    "сессию",
    "эту",
    "этой",
}
GOAL_HINT_TOKENS = {
    "goal",
    "intent",
    "main",
    "purpose",
    "target",
    "wanted",
    "главная",
    "главный",
    "задача",
    "намерение",
    "смысл",
    "фокус",
    "цель",
    "хотел",
    "хотела",
    "хотели",
}
KIND_WEIGHTS = {
    "user_message": 6,
    "timeline": 4,
    "assistant_message": 2,
    "artifact_field": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Ask one safe local question over one JSON or JSONL session artifact.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", "-i", required=True, help="Path to one JSON or JSONL session artifact")
    parser.add_argument("--question", "-q", required=True, help="Safe ask-only question over the artifact")
    parser.add_argument("--harness-provider", help="Optional harness provider alias such as codex or gemini")
    parser.add_argument("--format", default=DEFAULT_FORMAT, choices=["auto", "json", "jsonl"], help="Source format")
    parser.add_argument(
        "--max-evidence-items",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_ITEMS,
        help="How many evidence excerpts to keep, 1-5",
    )
    parser.add_argument("--pretty", action="store_true", help="Render a compact terminal view instead of JSON")
    parser.add_argument("--output", "-o", help="Write JSON or pretty output to file instead of stdout")
    parser.add_argument("--version", action="store_true", help="Show version")
    return parser.parse_args()


def emit_error(message: str) -> None:
    print(message, file=sys.stderr)


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def tokenize(value: str) -> List[str]:
    normalized = (
        normalize_text(value)
        .replace("/", " ")
        .replace("_", " ")
        .replace("-", " ")
    )
    tokens = []
    for chunk in normalized.replace(".", " ").replace(",", " ").replace(":", " ").replace(";", " ").split():
        chunk = chunk.strip().lower()
        if len(chunk) < 3 or chunk in QUESTION_STOPWORDS:
            continue
        tokens.append(chunk)
    return list(dict.fromkeys(tokens))


def detect_format(path: Path, explicit_format: str) -> str:
    if explicit_format != DEFAULT_FORMAT:
        return explicit_format
    if path.suffix.lower() == ".jsonl":
        return "jsonl"
    return "json"


def load_source(path: Path, explicit_format: str) -> Tuple[str, List[Any], int]:
    source_format = detect_format(path, explicit_format)
    if source_format == "jsonl":
        records: List[Any] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid JSONL at line {line_number}: {exc}") from exc
        return source_format, records, len(records)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {exc}") from exc

    if isinstance(payload, list):
        return "json", payload, len(payload)
    return "json", [payload], 1


def infer_snippet_kind(key: str, role: str, event_type: str) -> Tuple[str, str]:
    normalized_role = role.lower().strip()
    normalized_event = event_type.lower().strip()

    if normalized_role == "user" or normalized_event == "user_message":
        return "user_message", "User message"
    if normalized_role == "assistant":
        return "assistant_message", "Assistant message"
    if normalized_event or key == "description":
        label = normalized_event.replace("_", " ").strip() if normalized_event else "timeline"
        return "timeline", f"Timeline · {label or 'timeline'}"
    return "artifact_field", key.replace("_", " ").strip().title()


def collect_snippets(records: Iterable[Any]) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    seen_signatures = set()

    def visit(node: Any, context: Dict[str, str]) -> None:
        if isinstance(node, dict):
            role = str(node.get("role") or context.get("role") or "")
            event_type = str(node.get("event_type") or node.get("type") or context.get("event_type") or "")

            for key in TEXT_KEYS:
                text = normalize_text(node.get(key))
                if len(text) < 3:
                    continue
                kind, label = infer_snippet_kind(key, role, event_type)
                signature = (kind, text.lower())
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                snippets.append({
                    "kind": kind,
                    "label": label,
                    "text": text,
                })

            next_context = dict(context)
            if role:
                next_context["role"] = role
            if event_type:
                next_context["event_type"] = event_type

            for key, value in node.items():
                if key in TEXT_KEYS:
                    continue
                if isinstance(value, (dict, list)):
                    visit(value, next_context)
            return

        if isinstance(node, list):
            for item in node:
                visit(item, context)

    for record in records:
        visit(record, {})

    return snippets


def trim_excerpt(value: str, limit: int = 220) -> str:
    normalized = normalize_text(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def score_snippet(snippet: Dict[str, Any], question_tokens: List[str], goal_question: bool) -> Tuple[int, List[str]]:
    snippet_tokens = tokenize(snippet["text"])
    overlap = [token for token in snippet_tokens if token in question_tokens]
    score = len(overlap) * 5 + KIND_WEIGHTS.get(snippet["kind"], 0)
    if goal_question and snippet["kind"] == "user_message":
        score += 4
    return score, overlap


def select_evidence(
    question: str,
    snippets: List[Dict[str, Any]],
    max_items: int,
) -> Tuple[List[Dict[str, Any]], float, List[str]]:
    question_tokens = tokenize(question)
    goal_question = any(token in GOAL_HINT_TOKENS for token in question_tokens)
    scored: List[Dict[str, Any]] = []

    for snippet in snippets:
        score, overlap = score_snippet(snippet, question_tokens, goal_question)
        scored.append({
            **snippet,
            "score": score,
            "overlap": overlap,
        })

    ranked = sorted(
        scored,
        key=lambda item: (item["score"], KIND_WEIGHTS.get(item["kind"], 0), len(item["text"])),
        reverse=True,
    )

    positive = [item for item in ranked if item["score"] > 0]
    if positive:
        evidence = positive[:max_items]
    else:
        fallback = [item for item in ranked if item["kind"] == "user_message"] or ranked
        evidence = fallback[:max_items]

    if not evidence:
        return [], 0.12, [
            "В artifact не нашлось достаточных локальных текстовых сигналов для уверенного ответа.",
            "Source artifact не меняется; это ask-only слой поверх файла.",
        ]

    confidence = 0.28 + min(0.36, len(evidence) * 0.12)
    if any(item["overlap"] for item in evidence):
        confidence += 0.18
    if evidence[0]["kind"] == "user_message":
        confidence += 0.08
    confidence = min(confidence, 0.9)

    limitations = [
        "Ответ собран локально по text overlap и не использует внешний AI provider.",
        "Source artifact не меняется; это ask-only слой поверх файла.",
    ]
    if not any(item["overlap"] for item in evidence):
        limitations.append("Для этого вопроса прямого token overlap почти нет, поэтому ответ опирается на ближайшие локальные сигналы.")

    return evidence, confidence, limitations


def build_response(question: str, evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "По этому artifact пока не хватает локальных сигналов, чтобы ответить уверенно."

    primary = trim_excerpt(evidence[0]["text"], 180)
    secondary = [trim_excerpt(item["text"], 120) for item in evidence[1:3]]
    question_tokens = tokenize(question)
    goal_question = any(token in GOAL_HINT_TOKENS for token in question_tokens)

    if goal_question:
        response = f"По локальным сигналам из artifact, главный фокус выглядел так: {primary}"
        if secondary:
            response += f" Дополнительно всплывали: {'; '.join(secondary)}."
        return response

    response = f"Лучший локальный ответ по artifact: {primary}"
    if secondary:
        response += f" Подтверждающие сигналы: {'; '.join(secondary)}."
    return response


def build_result(
    harness_provider: str,
    source_format: str,
    record_count: int,
    question: str,
    snippets: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    confidence: float,
    limitations: List[str],
) -> Dict[str, Any]:
    return {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "answer_source": "local_artifact",
            "reasoning_mode": "lexical_evidence_match",
        },
        "source": {
            "harness_provider": harness_provider,
            "format": source_format,
            "record_count": record_count,
            "snippet_count": len(snippets),
            "user_message_count": sum(1 for item in snippets if item["kind"] == "user_message"),
        },
        "question": {
            "text": question,
        },
        "answer": {
            "mode": "ask-only",
            "response": build_response(question, evidence),
            "confidence": round(confidence, 3),
            "evidence": [
                {
                    "kind": item["kind"],
                    "label": item["label"],
                    "excerpt": trim_excerpt(item["text"]),
                    "score": item["score"],
                }
                for item in evidence
            ],
            "limitations": limitations,
        },
    }


def validate_result(payload: Dict[str, Any]) -> None:
    required = {"meta", "source", "question", "answer"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"missing result keys: {', '.join(sorted(missing))}")

    evidence = payload["answer"].get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("answer.evidence must be a list")


def render_pretty(payload: Dict[str, Any]) -> str:
    lines = [
        "🧠 Ask This Session",
        f"❓ {payload['question']['text']}",
        f"💬 {payload['answer']['response']}",
        f"📏 confidence: {int(payload['answer']['confidence'] * 100)}%",
        "",
        "🔎 Evidence",
    ]
    for index, item in enumerate(payload["answer"]["evidence"][:5]):
        lines.append(f"{QUESTION_NUMERALS[index]} [{item['label']}] {item['excerpt']}")
    if not payload["answer"]["evidence"]:
        lines.append("— локальные evidence excerpts не найдены")
    lines.extend(["", "⚠️ Limits"])
    for item in payload["answer"]["limitations"]:
        lines.append(f"• {item}")
    return "\n".join(lines)


def write_output(rendered: str, output_path: str | None) -> None:
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rendered}\n", encoding="utf-8")
        return
    sys.stdout.write(rendered)


def main() -> int:
    args = parse_args()

    if args.version:
        print(TOOL_VERSION)
        return 0

    input_path = Path(args.input).expanduser()
    if not input_path.exists() or not input_path.is_file():
        emit_error(f"input file not found: {input_path}")
        return 2

    question = normalize_text(args.question)
    if len(question) < 3:
        emit_error("question must contain at least 3 characters")
        return 2

    max_evidence_items = args.max_evidence_items
    if max_evidence_items < 1 or max_evidence_items > 5:
        emit_error("max-evidence-items must be between 1 and 5")
        return 2

    try:
        source_format, records, record_count = load_source(input_path, args.format)
        snippets = collect_snippets(records)
        evidence, confidence, limitations = select_evidence(question, snippets, max_evidence_items)
        payload = build_result(
            harness_provider=normalize_text(args.harness_provider),
            source_format=source_format,
            record_count=record_count,
            question=question,
            snippets=snippets,
            evidence=evidence,
            confidence=confidence,
            limitations=limitations,
        )
        validate_result(payload)
    except ValueError as exc:
        emit_error(str(exc))
        return 4
    except RuntimeError as exc:
        emit_error(str(exc))
        return 4
    except OSError as exc:
        emit_error(str(exc))
        return 1

    rendered = render_pretty(payload) if args.pretty else json.dumps(payload, ensure_ascii=False, indent=2)
    write_output(rendered, args.output)
    if args.output:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
