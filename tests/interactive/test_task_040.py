from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import User, get_current_user
from backend.api.routes.sessions import router as sessions_router
from tests.interactive.fixtures import codex_fixture_path


class Task040InteractiveRouteSecurityRulesTests(unittest.TestCase):
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
    def _session_payload() -> dict[str, object]:
        return {
            "session_id": "sess-fixture-codex-001",
            "agent_type": "codex",
            "agent_name": "Codex",
            "cwd": "/home/pets/zoo/agents_sessions_dashboard",
            "status": "active",
            "resume_supported": True,
            "interactive_owner_id": "admin",
        }

    def test_green_accepts_same_origin_interactive_boot_and_sets_security_headers(self) -> None:
        app = self._app()

        with patch(
            "backend.api.routes.sessions._resolve_session_artifact_source",
            return_value=(self._session_payload(), codex_fixture_path()),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive",
                    headers={
                        "origin": "https://dashboard.test",
                        "host": "dashboard.test",
                        "x-forwarded-proto": "https",
                        "sec-fetch-site": "same-origin",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(response.headers["x-interactive-auth-token"], "session-cookie")
        self.assertEqual(response.headers["x-interactive-origin-policy"], "same-origin")
        self.assertEqual(
            response.headers["x-interactive-transport-security"],
            "cookie-bound-http",
        )
        self.assertIn("Origin", response.headers["vary"])

    def test_red_rejects_cross_origin_interactive_boot(self) -> None:
        app = self._app()

        with patch(
            "backend.api.routes.sessions._resolve_session_artifact_source",
            return_value=(self._session_payload(), codex_fixture_path()),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/session-artifacts/codex/rollout-interactive-fixture.jsonl/interactive",
                    headers={
                        "origin": "https://evil.example",
                        "host": "dashboard.test",
                        "x-forwarded-proto": "https",
                        "sec-fetch-site": "cross-site",
                    },
                )

        self.assertEqual(response.status_code, 403)
        self.assertIn("same-origin", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
