from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from backend.parsers.codex_parser import CodexParser


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
CREATE_TIMEOUT_SECONDS = 240
INITIAL_PROMPT = "Reply with only the final integer. What is 1 + 2?"
BROWSER_PROMPT = "Add 2 to the previous result. Reply with only the final integer."
EXPECTED_INITIAL_REPLY = "3"
EXPECTED_BROWSER_REPLY = "5"


class RealSessionParityFixtureBroken(RuntimeError):
    """Raised when the real parity fixture cannot be created honestly."""


@dataclass(frozen=True)
class RealSessionParityFixture:
    artifact_path: Path
    artifact_id: str
    session_id: str
    initial_reply: str
    browser_prompt: str
    expected_browser_reply: str


def _candidate_rollout_files(*, created_after: float) -> list[Path]:
    if not CODEX_SESSIONS_ROOT.exists():
        return []

    candidates = [
        path
        for path in CODEX_SESSIONS_ROOT.rglob("rollout-*.jsonl")
        if path.is_file() and path.stat().st_mtime >= created_after
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates


def _find_matching_artifact(*, created_after: float) -> Path:
    parser = CodexParser()
    candidates = _candidate_rollout_files(created_after=created_after)
    if not candidates:
        raise RealSessionParityFixtureBroken("no new Codex rollout artifact was created")

    for candidate in candidates:
        summary = parser.parse_file(candidate)
        messages = " ".join(summary.user_messages)
        if "1 + 2" in messages:
            return candidate

    raise RealSessionParityFixtureBroken(
        "the newest Codex rollout artifacts do not contain the expected arithmetic prompt"
    )


def _extract_text_fragments(content: object) -> list[str]:
    if not isinstance(content, list):
        return []

    fragments: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            fragments.append(text.strip())
    return fragments


def _inspect_existing_artifact(path: Path) -> tuple[bool, bool]:
    has_initial_prompt = False
    has_browser_prompt = False
    has_initial_reply = False

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            payload = event.get("payload") or {}

            if event_type == "response_item":
                payload_type = payload.get("type")
                role = payload.get("role")
                if payload_type == "message" and role == "user":
                    for text in _extract_text_fragments(payload.get("content")):
                        if text == INITIAL_PROMPT:
                            has_initial_prompt = True
                        if text == BROWSER_PROMPT:
                            has_browser_prompt = True
                elif payload_type == "message" and role == "assistant":
                    if EXPECTED_INITIAL_REPLY in _extract_text_fragments(payload.get("content")):
                        has_initial_reply = True

            elif event_type == "event_msg":
                payload_type = payload.get("type")
                if payload_type == "user_message":
                    message = str(payload.get("message") or "").strip()
                    if message == INITIAL_PROMPT:
                        has_initial_prompt = True
                    if message == BROWSER_PROMPT:
                        has_browser_prompt = True
                elif payload_type == "agent_message":
                    message = str(payload.get("message") or "").strip()
                    if message == EXPECTED_INITIAL_REPLY:
                        has_initial_reply = True
                elif payload_type == "task_complete":
                    last_agent_message = str(payload.get("last_agent_message") or "").strip()
                    if last_agent_message == EXPECTED_INITIAL_REPLY:
                        has_initial_reply = True

    return has_initial_prompt and has_initial_reply, has_browser_prompt


def _find_existing_uncontinued_artifact() -> Path | None:
    for candidate in _candidate_rollout_files(created_after=0):
        has_seed_state, has_browser_prompt = _inspect_existing_artifact(candidate)
        if has_seed_state and not has_browser_prompt:
            return candidate
    return None


def _build_fixture_from_artifact(artifact_path: Path) -> RealSessionParityFixture:
    summary = CodexParser().parse_file(artifact_path)
    if not summary.session_id:
        raise RealSessionParityFixtureBroken(
            f"parity artifact is missing a session id: {artifact_path}"
        )

    return RealSessionParityFixture(
        artifact_path=artifact_path,
        artifact_id=artifact_path.name,
        session_id=summary.session_id,
        initial_reply=EXPECTED_INITIAL_REPLY,
        browser_prompt=BROWSER_PROMPT,
        expected_browser_reply=EXPECTED_BROWSER_REPLY,
    )


def build_real_session_parity_fixture() -> RealSessionParityFixture:
    existing_artifact = _find_existing_uncontinued_artifact()
    if existing_artifact is not None:
        return _build_fixture_from_artifact(existing_artifact)

    started_at = time.time()
    output_path = Path("/tmp") / f"agent-nexus-parity-step1-{int(started_at)}.txt"
    completed = subprocess.run(
        [
            "codex",
            "exec",
            "--json",
            "-o",
            str(output_path),
            INITIAL_PROMPT,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=CREATE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RealSessionParityFixtureBroken(
            f"codex exec failed while creating the parity fixture: {detail}"
        )

    initial_reply = output_path.read_text(encoding="utf-8").strip()
    if initial_reply != EXPECTED_INITIAL_REPLY:
        raise RealSessionParityFixtureBroken(
            f"expected initial parity reply {EXPECTED_INITIAL_REPLY!r}, got {initial_reply!r}"
        )

    artifact_path = _find_matching_artifact(created_after=started_at - 2.0)
    return _build_fixture_from_artifact(artifact_path)
