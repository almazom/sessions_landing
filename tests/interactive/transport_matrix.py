from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
SSOT_KANBAN_PATH = REPO_ROOT / "docs" / "plans" / "ssot_kanban_20260313_062127.json"


class InteractiveTransportMatrixReferenceNotFound(FileNotFoundError):
    """Raised when a required local reference for the transport matrix is missing."""


@dataclass(frozen=True)
class TransportMatrixEntry:
    key: str
    role: str
    transport: str
    continuation_fit: str
    direct_browser_transport: bool
    supports_resume: bool
    supports_live_status: bool
    evidence_paths: tuple[str, ...]
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class KimiBrowserReference:
    live_attach_transport: str
    history_complete_method: str
    evidence_paths: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CodexTransportMatrix:
    primary_transport: str
    entries: dict[str, TransportMatrixEntry]
    kimi_reference: KimiBrowserReference


def _load_reference_inputs(board_path: Path) -> dict[str, str]:
    payload = json.loads(board_path.read_text(encoding="utf-8"))
    return {
        item["id"]: item["path"]
        for item in payload["session"]["reference_inputs"]
        if "path" in item
    }


def _require_reference_path(
    reference_inputs: Mapping[str, str],
    reference_id: str,
) -> Path:
    raw_path = reference_inputs.get(reference_id)
    if not raw_path:
        raise InteractiveTransportMatrixReferenceNotFound(
            f"interactive transport matrix reference is missing: {reference_id}"
        )

    resolved_path = Path(raw_path).resolve()
    if not resolved_path.exists():
        raise InteractiveTransportMatrixReferenceNotFound(
            f"interactive transport matrix file is missing: {resolved_path}"
        )
    return resolved_path


def _require_reference_text(path: Path, needle: str) -> None:
    if needle not in path.read_text(encoding="utf-8"):
        raise InteractiveTransportMatrixReferenceNotFound(
            f"interactive transport matrix evidence is missing in: {path}"
        )


def build_codex_transport_matrix(
    *,
    board_path: Path | None = None,
    reference_overrides: Mapping[str, str] | None = None,
) -> CodexTransportMatrix:
    resolved_board_path = (board_path or SSOT_KANBAN_PATH).resolve()
    reference_inputs = _load_reference_inputs(resolved_board_path)
    if reference_overrides:
        reference_inputs.update(reference_overrides)

    app_server_readme = _require_reference_path(reference_inputs, "local-codex-app-server-readme")
    thread_resume_params = _require_reference_path(reference_inputs, "local-codex-thread-resume-params")
    thread_resume_response = _require_reference_path(
        reference_inputs, "local-codex-thread-resume-response"
    )
    thread_status_notification = _require_reference_path(
        reference_inputs, "local-codex-thread-status-notification"
    )
    sdk_readme = _require_reference_path(reference_inputs, "local-codex-sdk-readme")
    sdk_thread = _require_reference_path(reference_inputs, "local-codex-sdk-thread")
    sdk_events = _require_reference_path(reference_inputs, "local-codex-sdk-events")
    sdk_items = _require_reference_path(reference_inputs, "local-codex-sdk-items")
    kimi_web_reference = _require_reference_path(reference_inputs, "local-kimi-web-reference")
    kimi_sessions_api = _require_reference_path(reference_inputs, "local-kimi-sessions-api")

    _require_reference_text(app_server_readme, "typed channels")
    _require_reference_text(thread_resume_params, '"threadId"')
    _require_reference_text(thread_resume_response, '"Current runtime status for the thread."')
    _require_reference_text(thread_status_notification, '"activeFlags"')
    _require_reference_text(sdk_readme, "exchanges JSONL events over stdin/stdout")
    _require_reference_text(sdk_thread, "runStreamed")
    _require_reference_text(sdk_events, 'type: "thread.started"')
    _require_reference_text(sdk_items, 'type: "command_execution"')
    _require_reference_text(kimi_web_reference, "Switching from terminal to Web UI")
    _require_reference_text(kimi_sessions_api, "send_history_complete")

    entries = {
        "codex_app_server": TransportMatrixEntry(
            key="codex_app_server",
            role="primary continuation contract for the backend interactive runtime",
            transport="typed channels in-process, with JSON only at stdio/websocket boundaries",
            continuation_fit="primary_backend_protocol",
            direct_browser_transport=False,
            supports_resume=True,
            supports_live_status=True,
            evidence_paths=(
                str(app_server_readme),
                str(thread_resume_params),
                str(thread_resume_response),
                str(thread_status_notification),
            ),
            constraints=(
                "requires a server-side lifecycle owner instead of a browser-only client",
                "bootstrap may reconcile the immediate thread response with later session events",
                "the hot path stays typed even when external boundaries serialize JSON",
            ),
        ),
        "codex_exec_jsonl": TransportMatrixEntry(
            key="codex_exec_jsonl",
            role="raw streamed event transport for a Node sidecar or fixture probe",
            transport="stdin/stdout JSONL emitted by `codex exec --experimental-json`",
            continuation_fit="node_sidecar_stream",
            direct_browser_transport=False,
            supports_resume=True,
            supports_live_status=False,
            evidence_paths=(
                str(sdk_thread),
                str(sdk_events),
                str(sdk_items),
            ),
            constraints=(
                "resume is thread-id based rather than app-server thread lifecycle messaging",
                "stream exposes turn and item events but not the app-server status notification contract",
                "requires a spawned local CLI process rather than a direct browser session",
            ),
        ),
        "codex_sdk_ts": TransportMatrixEntry(
            key="codex_sdk_ts",
            role="node sidecar adapter that wraps codex exec and normalizes streamed events",
            transport="Node wrapper over spawned `codex exec --experimental-json`",
            continuation_fit="node_sidecar_wrapper",
            direct_browser_transport=False,
            supports_resume=True,
            supports_live_status=False,
            evidence_paths=(
                str(sdk_readme),
                str(sdk_thread),
                str(sdk_events),
                str(sdk_items),
            ),
            constraints=(
                "not a browser transport by itself because it spawns the local CLI",
                "best suited for backend orchestration, fixture seeding, and event normalization",
                "inherits raw exec limitations around live status semantics",
            ),
        ),
    }

    kimi_reference = KimiBrowserReference(
        live_attach_transport="websocket_replay_then_live",
        history_complete_method="history_complete",
        evidence_paths=(
            str(kimi_web_reference),
            str(kimi_sessions_api),
        ),
        notes=(
            "use Kimi as a UX and session-flow reference, not as a direct Codex transport implementation",
            "history replay finishes with an explicit completion marker before live attach continues",
            "interactive continuation is exposed through a dedicated browser route backed by a server runtime",
        ),
    )

    return CodexTransportMatrix(
        primary_transport="codex_app_server",
        entries=entries,
        kimi_reference=kimi_reference,
    )
