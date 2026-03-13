from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from backend.api.interactive_artifact_hash import build_artifact_hash_snapshot
from backend.api.interactive_identity import (
    load_runtime_identity_fixture,
    resolve_runtime_identity,
)
from backend.api.session_artifacts import build_session_route
from backend.parsers.base import SessionSummary
from backend.parsers.codex_parser import CodexParser

from .fixtures import codex_fixture_path


class InteractiveHarnessFixtureNotFound(FileNotFoundError):
    """Raised when the backend interactive harness fixture artifact is missing."""


@dataclass(frozen=True)
class InteractiveBackendHarness:
    harness: str
    artifact_path: Path
    summary: SessionSummary
    route: Dict[str, str]
    runtime_identity: Dict[str, Any]
    artifact_hash: Dict[str, Any]


def build_interactive_backend_harness(
    artifact_path: Path | None = None,
    *,
    harness: str = "codex",
) -> InteractiveBackendHarness:
    if harness != "codex":
        raise ValueError(f"unsupported interactive backend harness: {harness}")

    resolved_artifact_path = (artifact_path or codex_fixture_path()).resolve()
    if not resolved_artifact_path.exists():
        raise InteractiveHarnessFixtureNotFound(
            f"interactive backend harness fixture is missing: {resolved_artifact_path}"
        )

    summary = CodexParser().parse_file(resolved_artifact_path)
    route = build_session_route(harness, str(resolved_artifact_path), summary.session_id)
    runtime_identity = resolve_runtime_identity(
        load_runtime_identity_fixture(),
        harness=harness,
        artifact_route_id=route["id"],
    )
    artifact_hash = build_artifact_hash_snapshot(resolved_artifact_path)

    return InteractiveBackendHarness(
        harness=harness,
        artifact_path=resolved_artifact_path,
        summary=summary,
        route=route,
        runtime_identity=runtime_identity,
        artifact_hash=artifact_hash,
    )
