from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .backend_harness import (
    InteractiveHarnessFixtureNotFound,
    build_interactive_backend_harness,
)
from .transport_matrix import (
    InteractiveTransportMatrixReferenceNotFound,
    build_codex_transport_matrix,
)


class InteractiveTransportProbeNotReady(RuntimeError):
    """Raised when the transport probe cannot build a truthful verdict set."""


@dataclass(frozen=True)
class TransportProbeVerdict:
    key: str
    probe_support: str
    direct_browser_transport: bool
    runtime_requirement: str
    summary: str


@dataclass(frozen=True)
class CodexTransportProbe:
    session_id: str
    primary_transport: str
    verdicts: dict[str, TransportProbeVerdict]


def _build_probe_verdict(
    key: str,
    *,
    direct_browser_transport: bool,
    runtime_requirement: str,
    summary: str,
) -> TransportProbeVerdict:
    return TransportProbeVerdict(
        key=key,
        probe_support="supported",
        direct_browser_transport=direct_browser_transport,
        runtime_requirement=runtime_requirement,
        summary=summary,
    )


def run_transport_probe(
    artifact_path: Path | None = None,
    *,
    reference_overrides: Mapping[str, str] | None = None,
) -> CodexTransportProbe:
    try:
        harness = build_interactive_backend_harness(artifact_path=artifact_path)
        matrix = build_codex_transport_matrix(reference_overrides=reference_overrides)
    except (
        InteractiveHarnessFixtureNotFound,
        InteractiveTransportMatrixReferenceNotFound,
    ) as error:
        raise InteractiveTransportProbeNotReady(str(error)) from error

    thread_id = harness.runtime_identity["runtime"]["thread_id"]
    app_server = matrix.entries["codex_app_server"]
    raw_exec = matrix.entries["codex_exec_jsonl"]
    sdk = matrix.entries["codex_sdk_ts"]
    verdicts = {
        "codex_app_server": _build_probe_verdict(
            "codex_app_server",
            direct_browser_transport=app_server.direct_browser_transport,
            runtime_requirement="live_app_server",
            summary=(
                "App-server is probe-ready through contract evidence plus fixture identity, "
                "but still needs a live backend runtime owner."
            ),
        ),
        "codex_exec_jsonl": _build_probe_verdict(
            "codex_exec_jsonl",
            direct_browser_transport=raw_exec.direct_browser_transport,
            runtime_requirement="local_cli_process",
            summary=(
                "Raw exec is probe-ready because the fixture artifact + thread id map cleanly to "
                f"a resumable local CLI process ({thread_id})."
            ),
        ),
        "codex_sdk_ts": _build_probe_verdict(
            "codex_sdk_ts",
            direct_browser_transport=sdk.direct_browser_transport,
            runtime_requirement="node_wrapper_process",
            summary=(
                "SDK path is probe-ready as a Node sidecar over raw exec, not as a direct browser "
                "transport."
            ),
        ),
    }

    return CodexTransportProbe(
        session_id=harness.summary.session_id,
        primary_transport=matrix.primary_transport,
        verdicts=verdicts,
    )
