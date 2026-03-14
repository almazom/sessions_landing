"""Session API routes."""

import asyncio
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.api.interactive_events import normalize_thread_event
from backend.api.logging_utils import get_logger, log_event
from backend.api.interactive_boot import (
    InteractiveBootPayloadUnavailable,
    build_interactive_boot_payload,
)
from backend.api.interactive_actions import build_prompt_submit_action
from backend.api.interactive_artifact_hash import build_artifact_hash_snapshot
from backend.api.interactive_backpressure import evaluate_interactive_backpressure
from backend.api.interactive_status import build_interactive_runtime_status
from backend.api.interactive_ownership import (
    enforce_interactive_session_ownership,
    resolve_interactive_actor_id,
)
from backend.api.interactive_request_security import (
    apply_interactive_security_headers,
    enforce_interactive_request_security,
)
from backend.api.scanner import session_store, session_scanner
from backend.api.interactive_store import (
    build_operational_store_snapshot,
    upsert_operational_store_record,
)
from backend.api.session_artifacts import (
    attach_session_route,
    build_session_detail_payload,
    build_session_route,
    derive_resume_supported,
    parse_session_file,
    resolve_session_file_fallback,
    resolve_session_file_from_store,
)
from ..deps import User, get_current_user
from .websocket import notify_interactive_route_event
from ..settings import settings

logger = get_logger("agent_nexus.sessions")
REPO_ROOT = Path(__file__).resolve().parents[3]
NX_COLLECT_PATH = REPO_ROOT / "tools" / "nx-collect" / "nx-collect"
NX_COLLECT_TIMEOUT_SECONDS = 40
SESSION_QUERY_TOOL_DIR = REPO_ROOT / "tools" / "nx-session-query"
SESSION_QUERY_CLI_PATH = SESSION_QUERY_TOOL_DIR / "nx-session-query"
SESSION_QUERY_MAIN_PATH = SESSION_QUERY_TOOL_DIR / "main.py"
SESSION_QUERY_TIMEOUT_SECONDS = 20
CODEX_RESUME_BINARY = os.environ.get("CODEX_BIN", "codex")
SCRIPT_BINARY = os.environ.get("SCRIPT_BIN", "script")
CODEX_RESUME_STARTUP_GRACE_SECONDS = 0.2
INTERACTIVE_PROMPT_TIMEOUT_SECONDS = int(
    os.environ.get("NEXUS_INTERACTIVE_PROMPT_TIMEOUT_SECONDS", "240")
)
INTERACTIVE_PROMPT_RECENT_WINDOW_SECONDS = float(
    os.environ.get("NEXUS_INTERACTIVE_PROMPT_RECENT_WINDOW_SECONDS", "300")
)
INTERACTIVE_PROMPT_STATE_LOCK = threading.Lock()
INTERACTIVE_PROMPT_STATE: dict[str, dict[str, Any]] = {}

router = APIRouter(
    prefix="/api",
    tags=["Sessions"],
    dependencies=[Depends(get_current_user)],
)


class SessionAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class InteractivePromptSubmitRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=12000)
    client_event_id: str | None = Field(default=None, max_length=200)


def _session_changed_timestamp(session: dict) -> str:
    """Use the most recent known session timestamp for sorting/filtering."""
    return session.get("timestamp_end") or session.get("timestamp_start", "")


def _validate_latest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = {"meta", "query", "latest", "errors"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"latest payload missing keys: {', '.join(sorted(missing))}")
    if not isinstance(payload["errors"], list):
        raise ValueError("latest payload errors must be a list")
    return payload


def _format_cli_error(detail: str) -> str:
    normalized = " ".join(detail.split())
    return normalized[:400] if len(normalized) > 400 else normalized


def _ensure_sessions_loaded() -> None:
    if session_store.count() == 0 and not session_scanner.has_loaded_once:
        session_scanner.ensure_loaded()


def _session_query_cli_available() -> bool:
    return SESSION_QUERY_CLI_PATH.exists() or SESSION_QUERY_MAIN_PATH.exists()


def _build_session_query_command(file_path: Path, question: str, harness_provider: str) -> list[str]:
    base_args = [
        "--input",
        str(file_path),
        "--question",
        question,
        "--harness-provider",
        harness_provider,
    ]

    if SESSION_QUERY_CLI_PATH.exists() and os.access(SESSION_QUERY_CLI_PATH, os.X_OK):
        return [str(SESSION_QUERY_CLI_PATH), *base_args]

    if SESSION_QUERY_MAIN_PATH.exists():
        return [sys.executable, str(SESSION_QUERY_MAIN_PATH), *base_args]

    raise FileNotFoundError("Session query CLI entrypoint is not available.")


def _resolve_session_artifact_source(harness: str, artifact_id: str) -> tuple[Dict[str, Any], Path]:
    _ensure_sessions_loaded()
    session, file_path = resolve_session_file_from_store(session_store.get_all(), harness, artifact_id)

    if session is None or file_path is None or not file_path.exists():
        file_path = resolve_session_file_fallback(harness, artifact_id)
        if file_path is None:
            raise HTTPException(status_code=404, detail=f"Session artifact {harness}/{artifact_id} was not found.")
        session = attach_session_route(parse_session_file(harness, file_path))

    return session, file_path


def _resolve_session_artifact(harness: str, artifact_id: str) -> Dict[str, Any]:
    session, file_path = _resolve_session_artifact_source(harness, artifact_id)
    session_payload = dict(session)
    session_payload["query_enabled"] = bool(session_payload.get("query_enabled")) or _session_query_cli_available()
    session_payload["resume_supported"] = derive_resume_supported(session_payload)
    return build_session_detail_payload(session_payload, file_path)


def _resolve_interactive_artifact_boot(
    harness: str,
    artifact_id: str,
    *,
    actor_id: str | None = None,
) -> Dict[str, Any]:
    session, file_path = _resolve_session_artifact_source(harness, artifact_id)
    session_payload = dict(session)
    session_payload["resume_supported"] = derive_resume_supported(session_payload)
    if actor_id is not None:
        try:
            enforce_interactive_session_ownership(session_payload, actor_id=actor_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        return build_interactive_boot_payload(session_payload, file_path)
    except InteractiveBootPayloadUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _build_session_resume_command(session_id: str) -> list[str]:
    return [CODEX_RESUME_BINARY, "resume", session_id]


def _build_session_prompt_submit_command(*, session_id: str, output_path: Path) -> list[str]:
    return [
        CODEX_RESUME_BINARY,
        "exec",
        "resume",
        "--json",
        "-o",
        str(output_path),
        session_id,
        "-",
    ]


def _build_tty_resume_launcher(command: list[str], *, log_path: Path) -> list[str]:
    return [SCRIPT_BINARY, "-q", "-f", str(log_path), "-c", shlex.join(command)]


def _resume_log_path(artifact_id: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in artifact_id)
    return Path("/tmp") / f"agent-nexus-resume-{safe_name}.log"


def _interactive_prompt_output_path(artifact_id: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in artifact_id)
    token = uuid4().hex[:12]
    return Path(tempfile.gettempdir()) / f"agent-nexus-prompt-{safe_name}-{token}.txt"


def _read_resume_log_excerpt(log_path: Path) -> str:
    if not log_path.exists():
        return ""

    raw_bytes = log_path.read_bytes()[-800:]
    if not raw_bytes:
        return ""

    return raw_bytes.decode("utf-8", errors="replace").strip()


def _read_optional_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _artifact_snapshot_changed(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    return (
        before.get("sha256") != after.get("sha256")
        or before.get("byte_size") != after.get("byte_size")
    )


def _interactive_prompt_state_key(harness: str, artifact_id: str) -> str:
    return f"{harness}:{artifact_id}"


def _acquire_interactive_prompt_slot(
    *,
    harness: str,
    artifact_id: str,
    action: Dict[str, Any],
) -> Dict[str, Any]:
    state_key = _interactive_prompt_state_key(harness, artifact_id)
    now = time.time()

    with INTERACTIVE_PROMPT_STATE_LOCK:
        state = INTERACTIVE_PROMPT_STATE.setdefault(
            state_key,
            {
                "inflight_prompts": 0,
                "recent_prompt_timestamps": [],
            },
        )
        recent_prompt_timestamps = [
            timestamp
            for timestamp in state["recent_prompt_timestamps"]
            if now - float(timestamp) <= INTERACTIVE_PROMPT_RECENT_WINDOW_SECONDS
        ]
        verdict = evaluate_interactive_backpressure(
            action,
            inflight_prompts=int(state["inflight_prompts"]),
            queued_prompts=0,
            recent_prompt_count=len(recent_prompt_timestamps),
        )
        if verdict["disposition"] != "dispatch_now":
            raise OverflowError("interactive runtime already has a prompt in flight")

        state["inflight_prompts"] = int(state["inflight_prompts"]) + 1
        recent_prompt_timestamps.append(now)
        state["recent_prompt_timestamps"] = recent_prompt_timestamps
        return verdict


def _release_interactive_prompt_slot(*, harness: str, artifact_id: str) -> None:
    state_key = _interactive_prompt_state_key(harness, artifact_id)
    with INTERACTIVE_PROMPT_STATE_LOCK:
        state = INTERACTIVE_PROMPT_STATE.get(state_key)
        if state is None:
            return
        state["inflight_prompts"] = max(0, int(state.get("inflight_prompts", 0)) - 1)


def _publish_interactive_route_event(
    *,
    harness: str,
    route_id: str,
    event: Dict[str, Any],
) -> None:
    try:
        from_thread.run(
            notify_interactive_route_event,
            harness,
            route_id,
            event,
        )
    except RuntimeError:
        try:
            asyncio.run(
                notify_interactive_route_event(
                    harness,
                    route_id,
                    event,
                )
            )
        except RuntimeError:
            return


def _build_prompt_submitted_event(*, client_event_id: str, prompt_text: str) -> Dict[str, Any]:
    return {
        "event_id": client_event_id,
        "kind": "user_prompt",
        "status": "submitted",
        "summary": "Browser prompt submitted",
        "payload": {"text": prompt_text},
        "source_event_type": "prompt.submit",
    }


def _build_prompt_failed_event(*, client_event_id: str, detail: str) -> Dict[str, Any]:
    return {
        "event_id": f"{client_event_id}:failed",
        "kind": "error",
        "status": "failed",
        "summary": "Prompt submit failed",
        "payload": {"message": detail},
        "source_event_type": "prompt.failed",
    }


def _publish_resumed_runtime_identity(
    *,
    harness: str,
    file_path: Path,
    session_id: str,
    started_at: str,
) -> None:
    route = build_session_route(harness, str(file_path), session_id)
    runtime_identity = {
        "thread_id": session_id,
        "session_id": session_id,
        "transport": "codex_app_server",
        "source": "operational_live",
    }
    runtime_status = build_interactive_runtime_status(
        thread_id=session_id,
        session_id=session_id,
        raw_status={"type": "notLoaded", "active_flags": []},
        source="boot",
        transport_state="reconnecting",
        reconnect_reason="resume_after_boot",
        observed_at=started_at,
    )
    snapshot = build_operational_store_snapshot(
        route=route,
        runtime_identity=runtime_identity,
        runtime_status=runtime_status,
        supervisor={
            "owner_id": "agent-nexus-resume",
            "lease_id": f"resume-{session_id}",
            "lock_status": "claimed",
            "heartbeat_at": started_at,
            "lock_expires_at": started_at,
        },
        updated_at=started_at,
    )
    upsert_operational_store_record(
        output_path=None,
        record=snapshot["records"][0],
        updated_at=started_at,
    )


def _run_session_resume_cli(
    harness: str,
    artifact_id: str,
    request: Request,
) -> Dict[str, Any]:
    session, file_path = _resolve_session_artifact_source(harness, artifact_id)
    session_payload = dict(session)
    session_payload["resume_supported"] = derive_resume_supported(session_payload)

    if harness != "codex":
        raise HTTPException(status_code=409, detail="Session artifact is not resumable for this harness.")

    if not session_payload["resume_supported"]:
        raise HTTPException(status_code=409, detail="Session artifact is not resumable.")

    session_id = str(session_payload.get("session_id") or "").strip()
    cwd = str(session_payload.get("cwd") or "").strip()
    cwd_path = Path(cwd).expanduser()

    if not session_id or not cwd:
        raise HTTPException(status_code=409, detail="Session artifact is not resumable.")
    if not cwd_path.exists() or not cwd_path.is_dir():
        raise HTTPException(status_code=409, detail="Recorded session cwd is missing or not a directory.")

    command = _build_session_resume_command(session_id)
    log_path = _resume_log_path(artifact_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_command = _build_tty_resume_launcher(command, log_path=log_path)

    process = subprocess.Popen(
        launcher_command,
        cwd=str(cwd_path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    time.sleep(CODEX_RESUME_STARTUP_GRACE_SECONDS)
    return_code = process.poll()
    if return_code is not None:
        detail = _read_resume_log_excerpt(log_path) or "Codex resume exited immediately."
        raise HTTPException(status_code=502, detail=_format_cli_error(detail))

    started_at = datetime.now().isoformat()
    _publish_resumed_runtime_identity(
        harness=harness,
        file_path=file_path,
        session_id=session_id,
        started_at=started_at,
    )

    route = build_session_route(harness, str(file_path), session_id)
    return {
        "status": "started",
        "session_id": session_id,
        "cwd": str(cwd_path),
        "pid": process.pid,
        "log_path": str(log_path),
        "interactive_href": f"{route['href']}/interactive",
        "started_at": started_at,
    }


def _run_session_prompt_submit_cli(
    harness: str,
    artifact_id: str,
    *,
    prompt_text: str,
    actor_id: str,
    client_event_id: str | None,
    request: Request,
) -> Dict[str, Any]:
    session, file_path = _resolve_session_artifact_source(harness, artifact_id)
    session_payload = dict(session)
    session_payload["resume_supported"] = derive_resume_supported(session_payload)
    enforce_interactive_session_ownership(session_payload, actor_id=actor_id)

    if harness != "codex":
        raise HTTPException(status_code=409, detail="Interactive prompt submit is not supported for this harness.")

    if not session_payload["resume_supported"]:
        raise HTTPException(status_code=409, detail="Session artifact is not resumable.")

    session_id = str(session_payload.get("session_id") or "").strip()
    cwd = str(session_payload.get("cwd") or "").strip()
    cwd_path = Path(cwd).expanduser()
    normalized_prompt = prompt_text.strip()

    if not normalized_prompt:
        raise HTTPException(status_code=422, detail="Interactive prompt submit requires non-empty text.")
    if not session_id or not cwd:
        raise HTTPException(status_code=409, detail="Session artifact is missing resume metadata.")
    if not cwd_path.exists() or not cwd_path.is_dir():
        raise HTTPException(status_code=409, detail="Recorded session cwd is missing or not a directory.")

    request_id = getattr(request.state, "request_id", "")
    effective_client_event_id = client_event_id or request_id or f"interactive-prompt-{uuid4().hex}"
    action = build_prompt_submit_action(
        thread_id=session_id,
        supervisor_owner_id=actor_id,
        text=normalized_prompt,
        client_event_id=effective_client_event_id,
    )

    try:
        verdict = _acquire_interactive_prompt_slot(
            harness=harness,
            artifact_id=artifact_id,
            action=action,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        output_path = _interactive_prompt_output_path(artifact_id)
        before_artifact = build_artifact_hash_snapshot(file_path)
        route = build_session_route(harness, str(file_path), session_id)
        command = _build_session_prompt_submit_command(
            session_id=session_id,
            output_path=output_path,
        )

        log_event(
            logger,
            "info",
            "sessions.interactive.prompt.started",
            request_id=request_id,
            harness=harness,
            artifact_id=artifact_id,
            session_id=session_id,
            actor_id=actor_id,
            command=command,
            cwd=str(cwd_path),
            queue_disposition=verdict.get("disposition"),
            timeout_seconds=INTERACTIVE_PROMPT_TIMEOUT_SECONDS,
        )
        _publish_interactive_route_event(
            harness=harness,
            route_id=route["id"],
            event=_build_prompt_submitted_event(
                client_event_id=effective_client_event_id,
                prompt_text=normalized_prompt,
            ),
        )

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(cwd_path),
                bufsize=1,
            )
        except OSError as exc:
            failure_detail = "Failed to start interactive prompt submit."
            _publish_interactive_route_event(
                harness=harness,
                route_id=route["id"],
                event=_build_prompt_failed_event(
                    client_event_id=effective_client_event_id,
                    detail=failure_detail,
                ),
            )
            raise HTTPException(status_code=500, detail=failure_detail) from exc

        stdout_lines: list[str] = []
        stream_errors: list[Exception] = []

        def _stdout_reader() -> None:
            stdout_handle = process.stdout
            if stdout_handle is None:
                return
            for raw_line in stdout_handle:
                line = raw_line.strip()
                if not line:
                    continue
                stdout_lines.append(line)
                try:
                    normalized_event = normalize_thread_event(json.loads(line))
                except (json.JSONDecodeError, ValueError) as exc:
                    stream_errors.append(exc)
                    continue
                _publish_interactive_route_event(
                    harness=harness,
                    route_id=route["id"],
                    event=normalized_event,
                )

        reader_thread = threading.Thread(
            target=_stdout_reader,
            name=f"interactive-prompt-stream-{route['id']}",
            daemon=True,
        )
        reader_thread.start()

        try:
            if process.stdin is not None:
                process.stdin.write(normalized_prompt)
                if not normalized_prompt.endswith("\n"):
                    process.stdin.write("\n")
                process.stdin.close()
            return_code = process.wait(timeout=INTERACTIVE_PROMPT_TIMEOUT_SECONDS)
            reader_thread.join(timeout=2)
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
        except subprocess.TimeoutExpired as exc:
            process.kill()
            reader_thread.join(timeout=2)
            failure_detail = "Interactive prompt submit timed out."
            _publish_interactive_route_event(
                harness=harness,
                route_id=route["id"],
                event=_build_prompt_failed_event(
                    client_event_id=effective_client_event_id,
                    detail=failure_detail,
                ),
            )
            raise HTTPException(status_code=504, detail=failure_detail) from exc
        except OSError as exc:
            process.kill()
            reader_thread.join(timeout=2)
            failure_detail = "Failed to execute interactive prompt submit."
            _publish_interactive_route_event(
                harness=harness,
                route_id=route["id"],
                event=_build_prompt_failed_event(
                    client_event_id=effective_client_event_id,
                    detail=failure_detail,
                ),
            )
            raise HTTPException(status_code=500, detail=failure_detail) from exc

        stdout = "\n".join(stdout_lines).strip()
        assistant_message = _read_optional_text_file(output_path)

        if stream_errors:
            detail = f"Interactive prompt stream returned unsupported event: {stream_errors[0]}"
            _publish_interactive_route_event(
                harness=harness,
                route_id=route["id"],
                event=_build_prompt_failed_event(
                    client_event_id=effective_client_event_id,
                    detail=detail,
                ),
            )
            raise HTTPException(status_code=502, detail=_format_cli_error(detail))

        if return_code != 0:
            detail = stderr or stdout or assistant_message or "Interactive prompt submit failed."
            _publish_interactive_route_event(
                harness=harness,
                route_id=route["id"],
                event=_build_prompt_failed_event(
                    client_event_id=effective_client_event_id,
                    detail=detail,
                ),
            )
            raise HTTPException(status_code=502, detail=_format_cli_error(detail))

        after_artifact = build_artifact_hash_snapshot(file_path)
        if not _artifact_snapshot_changed(before_artifact, after_artifact):
            raise HTTPException(
                status_code=502,
                detail="Interactive prompt submit finished, but the shared session artifact did not change.",
            )

        refreshed_session_payload = attach_session_route(parse_session_file(harness, file_path))
        refreshed_session_payload["resume_supported"] = derive_resume_supported(refreshed_session_payload)
        refreshed_boot_payload = build_interactive_boot_payload(refreshed_session_payload, file_path)
        completed_at = datetime.now().isoformat()

        log_event(
            logger,
            "info",
            "sessions.interactive.prompt.completed",
            request_id=request_id,
            harness=harness,
            artifact_id=artifact_id,
            session_id=session_id,
            actor_id=actor_id,
            artifact_before_sha256=before_artifact.get("sha256"),
            artifact_after_sha256=after_artifact.get("sha256"),
            assistant_message_preview=_format_cli_error(assistant_message) if assistant_message else None,
        )

        return {
            "status": "completed",
            "session_id": session_id,
            "cwd": str(cwd_path),
            "submitted_text": normalized_prompt,
            "artifact_updated": True,
            "artifact_before": before_artifact,
            "artifact_after": after_artifact,
            "assistant_message": assistant_message,
            "boot_payload": refreshed_boot_payload,
            "completed_at": completed_at,
        }
    finally:
        _release_interactive_prompt_slot(harness=harness, artifact_id=artifact_id)


def _validate_session_query_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = {"meta", "source", "question", "answer"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"session query payload missing keys: {', '.join(sorted(missing))}")
    return payload


def _run_session_query_cli(
    harness: str,
    artifact_id: str,
    question: str,
    request: Request,
) -> Dict[str, Any]:
    request_id = getattr(request.state, "request_id", "")

    if not _session_query_cli_available():
        log_event(
            logger,
            "error",
            "sessions.ask.cli_missing",
            request_id=request_id,
            cli_path=str(SESSION_QUERY_CLI_PATH),
            main_path=str(SESSION_QUERY_MAIN_PATH),
        )
        raise HTTPException(status_code=500, detail="Session query CLI is not available.")

    session, file_path = _resolve_session_artifact_source(harness, artifact_id)
    try:
        command = _build_session_query_command(
            file_path,
            question,
            str(session.get("agent_type") or harness),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Session query CLI is not available.") from exc

    log_event(
        logger,
        "info",
        "sessions.ask.cli_started",
        request_id=request_id,
        command=command,
        timeout_seconds=SESSION_QUERY_TIMEOUT_SECONDS,
        harness=harness,
        artifact_id=artifact_id,
    )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=SESSION_QUERY_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        log_event(
            logger,
            "error",
            "sessions.ask.cli_timeout",
            request_id=request_id,
            timeout_seconds=SESSION_QUERY_TIMEOUT_SECONDS,
            harness=harness,
            artifact_id=artifact_id,
        )
        raise HTTPException(status_code=504, detail="Session ask flow timed out.") from exc
    except OSError as exc:
        log_event(
            logger,
            "error",
            "sessions.ask.cli_failed_to_start",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to start session query CLI.") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stderr:
        log_event(
            logger,
            "warning" if completed.returncode == 0 else "error",
            "sessions.ask.cli_stderr",
            request_id=request_id,
            return_code=completed.returncode,
            stderr=_format_cli_error(stderr),
        )

    if completed.returncode != 0:
        detail = stderr or stdout or "Session query CLI failed."
        raise HTTPException(status_code=502, detail=_format_cli_error(detail))

    try:
        payload = _validate_session_query_payload(json.loads(stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        log_event(
            logger,
            "error",
            "sessions.ask.cli_invalid_json",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(status_code=502, detail="Session query CLI returned invalid JSON.") from exc

    log_event(
        logger,
        "info",
        "sessions.ask.cli_completed",
        request_id=request_id,
        harness=harness,
        artifact_id=artifact_id,
        confidence=((payload.get("answer") or {}).get("confidence")),
    )
    return payload


def _run_latest_cli(request: Request) -> Dict[str, Any]:
    request_id = getattr(request.state, "request_id", "")

    if not NX_COLLECT_PATH.exists():
        log_event(
            logger,
            "error",
            "sessions.latest.cli_missing",
            request_id=request_id,
            cli_path=str(NX_COLLECT_PATH),
        )
        raise HTTPException(status_code=500, detail="Latest session CLI is not available.")

    command = [str(NX_COLLECT_PATH), "--latest"]
    log_event(
        logger,
        "info",
        "sessions.latest.cli_started",
        request_id=request_id,
        command=command,
        timeout_seconds=NX_COLLECT_TIMEOUT_SECONDS,
    )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=NX_COLLECT_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        log_event(
            logger,
            "error",
            "sessions.latest.cli_timeout",
            request_id=request_id,
            timeout_seconds=NX_COLLECT_TIMEOUT_SECONDS,
        )
        raise HTTPException(status_code=504, detail="Latest session lookup timed out.") from exc
    except OSError as exc:
        log_event(
            logger,
            "error",
            "sessions.latest.cli_failed_to_start",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to start latest session CLI.") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if stderr:
        log_event(
            logger,
            "warning" if completed.returncode == 0 else "error",
            "sessions.latest.cli_stderr",
            request_id=request_id,
            return_code=completed.returncode,
            stderr=_format_cli_error(stderr),
        )

    payload: Optional[Dict[str, Any]] = None
    if stdout:
        try:
            payload = _validate_latest_payload(json.loads(stdout))
        except (json.JSONDecodeError, ValueError) as exc:
            log_event(
                logger,
                "error",
                "sessions.latest.cli_invalid_json",
                request_id=request_id,
                return_code=completed.returncode,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise HTTPException(status_code=502, detail="Latest session CLI returned invalid JSON.") from exc

    if completed.returncode == 0 and payload is not None:
        if payload.get("latest"):
            payload["latest"] = attach_session_route(payload["latest"])
        log_event(
            logger,
            "info",
            "sessions.latest.cli_completed",
            request_id=request_id,
            provider=(payload.get("latest") or {}).get("provider"),
            has_latest=bool(payload.get("latest")),
        )
        return payload

    if completed.returncode == 3 and payload is not None and payload.get("latest") is None:
        log_event(
            logger,
            "info",
            "sessions.latest.cli_empty",
            request_id=request_id,
            errors=payload.get("errors"),
        )
        return payload

    error_detail = stderr or "Latest session CLI failed."
    raise HTTPException(status_code=502, detail=_format_cli_error(error_detail))


@router.get("/sessions")
async def list_sessions(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: active, completed, error"),
    agent: Optional[str] = Query(None, description="Filter by agent type"),
    changed_date: Optional[str] = Query(None, description="Filter by changed date YYYY-MM-DD"),
    limit: int = Query(settings.default_session_limit, ge=1, le=settings.max_session_limit),
    offset: int = Query(0, ge=0),
):
    """
    📋 Получить список всех сессий
    
    - **status**: Фильтр по статусу (active, completed, error, paused)
    - **agent**: Фильтр по типу агента (codex, kimi, gemini, qwen, claude, pi)
    - **limit**: Максимальное количество результатов
    - **offset**: Смещение для пагинации
    """
    # Сканируем сессии если магазин пуст
    if session_store.count() == 0 and not session_scanner.has_loaded_once:
        log_event(
            logger,
            "info",
            "sessions.autoscan.triggered",
            request_id=getattr(request.state, "request_id", ""),
            reason="empty_store",
        )
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    sessions = session_store.get_all()
    
    # Фильтрация
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    
    if agent:
        sessions = [s for s in sessions if s.get("agent_type") == agent]

    if changed_date:
        sessions = [
            s for s in sessions
            if _session_changed_timestamp(s)[:10] == changed_date
        ]
    
    # Сортировка по последнему изменению (новые первыми)
    sessions.sort(key=_session_changed_timestamp, reverse=True)
    
    # Пагинация
    total = len(sessions)
    sessions = sessions[offset:offset + limit]

    log_event(
        logger,
        "info",
        "sessions.list.completed",
        request_id=getattr(request.state, "request_id", ""),
        status_filter=status,
        agent_filter=agent,
        changed_date=changed_date,
        total=total,
        returned=len(sessions),
        limit=limit,
        offset=offset,
    )
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sessions": [attach_session_route(session) for session in sessions],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """
    🔍 Получить детали сессии по ID
    
    - **session_id**: UUID сессии
    """
    # Сканируем если пусто
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    session = session_store.get(session_id)
    
    if not session:
        log_event(
            logger,
            "warning",
            "sessions.detail.not_found",
            request_id=getattr(request.state, "request_id", ""),
            session_id=session_id,
        )
        raise HTTPException(status_code=404, detail=f"Сессия {session_id} не найдена")

    log_event(
        logger,
        "info",
        "sessions.detail.completed",
        request_id=getattr(request.state, "request_id", ""),
        session_id=session_id,
        session_status=session.get("status"),
        agent_type=session.get("agent_type"),
    )
    
    return attach_session_route(session)


@router.get("/session-artifacts/{harness}/{artifact_id}")
async def get_session_artifact_detail(harness: str, artifact_id: str, request: Request):
    """Return one rich session detail payload addressable by harness and stable route id."""
    payload = await run_in_threadpool(_resolve_session_artifact, harness, artifact_id)
    log_event(
        logger,
        "info",
        "sessions.artifact.completed",
        request_id=getattr(request.state, "request_id", ""),
        harness=harness,
        artifact_id=artifact_id,
        session_id=(payload.get("session") or {}).get("session_id"),
    )
    return payload


@router.get("/session-artifacts/{harness}/{artifact_id}/interactive")
async def get_session_artifact_interactive_boot(
    harness: str,
    artifact_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    """Return the initial backend boot payload for the dedicated interactive route."""
    try:
        enforce_interactive_request_security(request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    actor_id = resolve_interactive_actor_id(user)
    payload = await run_in_threadpool(
        _resolve_interactive_artifact_boot,
        harness,
        artifact_id,
        actor_id=actor_id,
    )
    apply_interactive_security_headers(response)
    log_event(
        logger,
        "info",
        "sessions.artifact.interactive.completed",
        request_id=getattr(request.state, "request_id", ""),
        harness=harness,
        artifact_id=artifact_id,
        session_id=(payload.get("session") or {}).get("session_id"),
        actor_id=actor_id,
        transport=(payload.get("interactive_session") or {}).get("transport"),
    )
    return payload


@router.post("/session-artifacts/{harness}/{artifact_id}/resume")
async def resume_session_artifact(
    harness: str,
    artifact_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Start a resumable Codex artifact from its recorded working directory."""
    result = await run_in_threadpool(_run_session_resume_cli, harness, artifact_id, request)
    log_event(
        logger,
        "info",
        "sessions.resume.started",
        request_id=getattr(request.state, "request_id", ""),
        harness=harness,
        artifact_id=artifact_id,
        session_id=result.get("session_id"),
        username=user.username,
        pid=result.get("pid"),
    )
    return result


@router.post("/session-artifacts/{harness}/{artifact_id}/interactive/prompt")
async def submit_session_artifact_interactive_prompt(
    harness: str,
    artifact_id: str,
    payload: InteractivePromptSubmitRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    """Submit one real continuation prompt against the shared Codex session artifact."""
    try:
        enforce_interactive_request_security(request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    actor_id = resolve_interactive_actor_id(user)
    result = await run_in_threadpool(
        _run_session_prompt_submit_cli,
        harness,
        artifact_id,
        prompt_text=payload.text,
        actor_id=actor_id,
        client_event_id=payload.client_event_id,
        request=request,
    )
    apply_interactive_security_headers(response)
    return result


@router.post("/session-artifacts/{harness}/{artifact_id}/ask")
async def ask_session_artifact(
    harness: str,
    artifact_id: str,
    payload: SessionAskRequest,
    request: Request,
):
    """Run the safe ask-only query flow for one session artifact."""
    result = await run_in_threadpool(_run_session_query_cli, harness, artifact_id, payload.question, request)
    log_event(
        logger,
        "info",
        "sessions.ask.completed",
        request_id=getattr(request.state, "request_id", ""),
        harness=harness,
        artifact_id=artifact_id,
    )
    return result


@router.get("/latest-session")
async def get_latest_session(request: Request):
    """Return one global latest session from the nx-collect CLI."""
    return await run_in_threadpool(_run_latest_cli, request)


@router.get("/metrics")
async def get_metrics(request: Request):
    """
    📊 Агрегированные метрики по всем сессиям
    
    Возвращает:
    - Общее количество сессий
    - Распределение по агентам
    - Распределение по статусам
    - Общее количество токенов
    """
    # Сканируем если пусто
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    metrics = session_store.metrics()

    log_event(
        logger,
        "info",
        "sessions.metrics.completed",
        request_id=getattr(request.state, "request_id", ""),
        total_sessions=metrics.get("total_sessions"),
        total_tokens=metrics.get("total_tokens"),
    )
    
    return {
        "success": True,
        "data": metrics,
    }


@router.post("/sessions/scan")
async def rescan_sessions(request: Request):
    """
    🔄 Принудительное пересканирование всех директорий агентов
    
    Полезно когда появились новые сессии
    """
    log_event(
        logger,
        "info",
        "sessions.rescan.started",
        request_id=getattr(request.state, "request_id", ""),
    )
    
    # Очищаем старые данные
    session_store.sessions.clear()
    
    # Сканируем заново
    count = session_scanner.scan_all()
    errors = session_scanner.get_errors()

    log_event(
        logger,
        "info",
        "sessions.rescan.completed",
        request_id=getattr(request.state, "request_id", ""),
        sessions_found=count,
        errors=errors if errors else None,
    )
    
    return {
        "success": True,
        "sessions_found": count,
        "errors": errors if errors else None,
        "scanned_at": datetime.now().isoformat(),
    }


@router.get("/agents")
async def list_agents(request: Request):
    """
    🤖 Получить список поддерживаемых агентов и их статусов
    """
    from ...parsers import PARSER_REGISTRY
    from ..scanner import SessionScanner
    
    agents = []
    
    for agent_type in PARSER_REGISTRY.keys():
        watch_path = Path(SessionScanner.WATCH_PATHS.get(agent_type, "")).expanduser()
        
        agents.append({
            "type": agent_type,
            "watch_path": str(watch_path),
            "path_exists": watch_path.exists(),
            "session_count": len([
                s for s in session_store.get_all() 
                if s.get("agent_type") == agent_type
            ]),
        })
    
    response = {
        "total": len(agents),
        "agents": agents,
    }

    log_event(
        logger,
        "info",
        "sessions.agents.completed",
        request_id=getattr(request.state, "request_id", ""),
        total=response["total"],
    )

    return response
