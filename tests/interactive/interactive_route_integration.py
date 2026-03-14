from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import User, get_current_user
from backend.api.routes.sessions import router as sessions_router
from tests.interactive.fixtures import codex_fixture_path
from tests.interactive.interactive_live_state import (
    InteractiveLiveStateSnapshot,
    build_interactive_live_state_snapshot,
)
from tests.interactive.interactive_page_shell import (
    InteractivePageShellSnapshot,
    build_interactive_page_shell_snapshot,
)
from tests.interactive.interactive_resilience_states import (
    InteractiveResilienceStatesSnapshot,
    build_interactive_resilience_states_snapshot,
)


class InteractiveRouteIntegrationBroken(RuntimeError):
    """Raised when the interactive route integration bundle is incomplete."""


@dataclass(frozen=True)
class InteractiveRouteIntegrationSnapshot:
    backend_path: str
    interactive_href: str
    transport: str
    thread_id: str | None
    available: bool
    page_snapshot: InteractivePageShellSnapshot
    live_state_snapshot: InteractiveLiveStateSnapshot
    resilience_snapshot: InteractiveResilienceStatesSnapshot


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_current_user] = lambda: User(
        username="admin",
        is_authenticated=True,
        auth_method="test",
    )
    return app


def _session_payload(*, resume_supported: bool, status: str) -> dict[str, object]:
    return {
        "session_id": "sess-fixture-codex-001",
        "agent_type": "codex",
        "agent_name": "Codex",
        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
        "status": status,
        "resume_supported": resume_supported,
    }


def build_interactive_route_integration_snapshot(
    *,
    resume_supported: bool = True,
    status: str = "active",
    page_path: Path | None = None,
) -> InteractiveRouteIntegrationSnapshot:
    app = _app()
    backend_path = "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive"

    with patch(
        "backend.api.routes.sessions._resolve_session_artifact_source",
        return_value=(
            _session_payload(resume_supported=resume_supported, status=status),
            codex_fixture_path(),
        ),
    ):
        with TestClient(app) as client:
            response = client.get(backend_path)

    if response.status_code != 200:
        raise InteractiveRouteIntegrationBroken(
            f"interactive boot endpoint returned {response.status_code}: {response.json().get('detail', '')}"
        )

    payload = response.json()
    try:
        page_snapshot = build_interactive_page_shell_snapshot(page_path=page_path)
        live_state_snapshot = build_interactive_live_state_snapshot()
        resilience_snapshot = build_interactive_resilience_states_snapshot()
    except (FileNotFoundError, RuntimeError) as error:
        raise InteractiveRouteIntegrationBroken(str(error)) from error

    interactive_href = payload["route"]["interactive_href"]
    if interactive_href != "/sessions/codex/rollout-interactive-fixture.jsonl/interactive":
        raise InteractiveRouteIntegrationBroken(
            f"interactive href mismatch from backend payload: {interactive_href}"
        )
    if not interactive_href.endswith(page_snapshot.route_suffix):
        raise InteractiveRouteIntegrationBroken(
            f"interactive href does not align with page route suffix: {interactive_href}"
        )
    return InteractiveRouteIntegrationSnapshot(
        backend_path=backend_path,
        interactive_href=interactive_href,
        transport=str(payload["interactive_session"]["transport"]),
        thread_id=(
            str(payload["runtime_identity"]["thread_id"])
            if isinstance(payload.get("runtime_identity"), dict)
            else None
        ),
        available=bool(payload["interactive_session"]["available"]),
        page_snapshot=page_snapshot,
        live_state_snapshot=live_state_snapshot,
        resilience_snapshot=resilience_snapshot,
    )
