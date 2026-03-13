from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import User, get_current_user
from backend.api.routes.sessions import router as sessions_router
from tests.interactive.fixtures import codex_fixture_path


class Task034BackendInteractiveRouteLoaderTests(unittest.TestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(sessions_router)
        app.dependency_overrides[get_current_user] = lambda: User(
            username="admin",
            is_authenticated=True,
            auth_method="test",
        )
        return app

    @staticmethod
    def _session_payload(*, resume_supported: bool, status: str) -> dict[str, object]:
        return {
            "session_id": "sess-fixture-codex-001",
            "agent_type": "codex",
            "agent_name": "Codex",
            "cwd": "/home/pets/zoo/agents_sessions_dashboard",
            "status": status,
            "resume_supported": resume_supported,
        }

    def test_green_returns_boot_payload_for_supported_interactive_route(self) -> None:
        app = self._app()

        with patch(
            "backend.api.routes.sessions._resolve_session_artifact_source",
            return_value=(
                self._session_payload(resume_supported=True, status="active"),
                codex_fixture_path(),
            ),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive"
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"]["route_id"], "rollout-interactive-fixture.jsonl")
        self.assertEqual(
            payload["route"]["interactive_href"],
            "/sessions/codex/rollout-interactive-fixture.jsonl/interactive",
        )
        self.assertTrue(payload["interactive_session"]["available"])
        self.assertEqual(payload["interactive_session"]["transport"], "codex_app_server")
        self.assertEqual(payload["runtime_identity"]["thread_id"], "thread-fixture-codex-001")

    def test_red_rejects_interactive_route_when_resume_is_disabled(self) -> None:
        app = self._app()

        with patch(
            "backend.api.routes.sessions._resolve_session_artifact_source",
            return_value=(
                self._session_payload(resume_supported=False, status="idle"),
                codex_fixture_path(),
            ),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive"
                )

        self.assertEqual(response.status_code, 409)
        self.assertIn("disabled", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
