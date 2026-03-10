#!/usr/bin/env python3
"""Dedicated CLI for semantic intent extraction over one session file."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


TOOL_NAME = "extract-intent"
TOOL_VERSION = "1.7.0"
PROMPT_ID = "intent-vector-ru"
DEFAULT_MAX_STEPS = 5
DEFAULT_PREFLIGHT_TIMEOUT = 30
DEFAULT_RUNTIME_TIMEOUT = 60
DEFAULT_PROVIDER_CHAIN = "auto"
DEFAULT_FORMAT = "auto"
STEP_NUMERALS = ["①", "②", "③", "④", "⑤", "⑥", "⑦"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Extract 3-7 easy-to-read Russian intent steps from one JSON or JSONL session file.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", "-i", help="Path to one JSON or JSONL session file")
    parser.add_argument("--project", help="Project folder; resolve the latest session file for this project before extraction")
    parser.add_argument(
        "--provider",
        "--harness-provider",
        "--hp",
        dest="harness_provider",
        help="Single source harness provider alias, used with --project, e.g. gemini or pi",
    )
    parser.add_argument("--providers", default="all", help="Comma-separated provider list or 'all' when using --project")
    parser.add_argument("--providers-config", help="Override provider catalog JSON path for --project resolution")
    parser.add_argument("--format", default=DEFAULT_FORMAT, choices=["auto", "json", "jsonl"], help="Source format")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Intent step count, 3-7")
    parser.add_argument("--processing-provider", "--pp", help="Single AI provider used for semantic summary, e.g. gemini or pi")
    parser.add_argument("--provider-chain", default=DEFAULT_PROVIDER_CHAIN, help="Provider chain for nx-cognize")
    parser.add_argument("--state-file", help="Override nx-cognize provider state cache path")
    parser.add_argument("--preflight-timeout", type=int, default=DEFAULT_PREFLIGHT_TIMEOUT, help="Preflight timeout in seconds")
    parser.add_argument("--runtime-timeout", type=int, default=DEFAULT_RUNTIME_TIMEOUT, help="Runtime timeout in seconds")
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


def build_result(payload: Dict[str, Any], source_provider: str = "") -> Dict[str, Any]:
    meta = payload.get("meta") or {}
    source = payload.get("source") or {}
    summary = payload.get("summary") or {}
    selected_provider = str(meta.get("selected_provider") or "")
    summary_source = "ai"
    if selected_provider == "local":
        summary_source = "local_fallback"

    return {
        "meta": {
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prompt_id": PROMPT_ID,
            "selected_provider": selected_provider,
            "processing_provider": selected_provider,
            "summary_source": summary_source,
            "provider_attempts": meta.get("provider_attempts") or [],
        },
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
    args = parse_args()
    if args.version:
        print(TOOL_VERSION)
        return 0

    if args.max_steps < 3 or args.max_steps > 7:
        emit_error("--max-steps must be in range 3..7")
        return 2
    if args.preflight_timeout < 1 or args.runtime_timeout < 1:
        emit_error("timeouts must be positive integers")
        return 2
    if args.harness_provider and not args.project:
        emit_error("--harness-provider/--hp can be used only together with --project")
        return 2
    if args.processing_provider and args.processing_provider not in {"qwen", "gemini", "claude", "pi", "local"}:
        emit_error("--processing-provider must be one of: qwen, gemini, claude, pi, local")
        return 2
    if bool(args.input) == bool(args.project):
        emit_error("exactly one selector is required: --input/-i or --project")
        return 2

    base_dir = Path(__file__).resolve().parent
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

    cognize_path = (base_dir.parent / "nx-cognize" / "nx-cognize").resolve()
    if not cognize_path.exists():
        emit_error("nx-cognize wrapper is not available")
        return 3

    command: List[str] = [
        str(cognize_path),
        "--input",
        str(input_path),
        "--prompt-id",
        PROMPT_ID,
        "--provider-chain",
        resolve_effective_processing_chain(
            base_dir=base_dir,
            processing_provider=args.processing_provider,
            provider_chain=args.provider_chain,
            harness_provider=source_provider,
        ),
        "--format",
        args.format,
        "--max-bullets",
        str(args.max_steps),
        "--max-words-per-bullet",
        "5",
        "--preflight-timeout",
        str(args.preflight_timeout),
        "--runtime-timeout",
        str(args.runtime_timeout),
    ]
    if args.state_file:
        command.extend(["--state-file", args.state_file])

    timeout_seconds = max(5, args.preflight_timeout + args.runtime_timeout + 5)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        emit_error(f"nx-cognize timed out after {timeout_seconds}s")
        return 3
    except OSError as exc:
        emit_error(str(exc))
        return 3

    if completed.returncode != 0:
        emit_error((completed.stderr or completed.stdout).strip() or "nx-cognize failed")
        return 3

    try:
        cognitive_payload = json.loads(completed.stdout)
        result = build_result(cognitive_payload, source_provider=source_provider)
        validate_result(result)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        emit_error(str(exc))
        return 4

    rendered = render_pretty(result) if args.pretty else json.dumps(result, ensure_ascii=False, indent=2)
    write_output(rendered, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
