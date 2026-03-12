import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.api.routes import sessions as sessions_routes


def make_request(request_id: str = "req-test"):
    return SimpleNamespace(state=SimpleNamespace(request_id=request_id))


class SessionRoutesTests(unittest.TestCase):
    def test_resolve_session_artifact_marks_query_layer_available_when_cli_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            source_path = Path(tmp_dir) / "rollout-demo.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "session-123",
                        "query_enabled": False,
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes,
                "SESSION_QUERY_CLI_PATH",
                cli_path,
            ), patch.object(
                sessions_routes,
                "build_session_detail_payload",
                side_effect=lambda session_payload, file_path: {
                    "session": session_payload,
                    "file_path": str(file_path),
                },
            ):
                payload = sessions_routes._resolve_session_artifact("codex", "rollout-demo.jsonl")

        self.assertTrue(payload["session"]["query_enabled"])
        self.assertEqual(payload["file_path"], str(source_path))

    def test_run_session_query_cli_returns_structured_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            source_path = Path(tmp_dir) / "rollout-demo.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")
            expected_payload = {
                "meta": {
                    "tool": "nx-session-query",
                    "tool_version": "1.0.0",
                    "generated_at": "2026-03-12T08:06:00Z",
                    "answer_source": "local_artifact",
                    "reasoning_mode": "lexical_evidence_match",
                },
                "source": {
                    "harness_provider": "codex",
                    "format": "jsonl",
                    "record_count": 7,
                    "snippet_count": 5,
                    "user_message_count": 3,
                },
                "question": {
                    "text": "Какая была главная цель этой сессии?",
                },
                "answer": {
                    "mode": "ask-only",
                    "response": "Главный фокус: починить detail page.",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "kind": "user_message",
                            "label": "User message",
                            "excerpt": "починить detail page",
                            "score": 12,
                        }
                    ],
                    "limitations": [
                        "Local lexical matching only.",
                    ],
                },
            }

            completed = subprocess.CompletedProcess(
                args=[str(cli_path)],
                returncode=0,
                stdout=json.dumps(expected_payload, ensure_ascii=False),
                stderr="",
            )

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "session-123",
                        "agent_type": "codex",
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes,
                "SESSION_QUERY_CLI_PATH",
                cli_path,
            ), patch.object(
                sessions_routes.subprocess,
                "run",
                return_value=completed,
            ) as run_mock:
                payload = sessions_routes._run_session_query_cli(
                    "codex",
                    "rollout-demo.jsonl",
                    "Какая была главная цель этой сессии?",
                    make_request(),
                )

        self.assertEqual(payload["answer"]["mode"], "ask-only")
        self.assertEqual(payload["answer"]["response"], "Главный фокус: починить detail page.")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], str(cli_path))
        self.assertEqual(command[command.index("--input") + 1], str(source_path))
        self.assertEqual(command[command.index("--question") + 1], "Какая была главная цель этой сессии?")
        self.assertEqual(command[command.index("--harness-provider") + 1], "codex")

    def test_run_session_query_cli_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            source_path = Path(tmp_dir) / "rollout-demo.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")

            completed = subprocess.CompletedProcess(
                args=[str(cli_path)],
                returncode=0,
                stdout="{not-json}",
                stderr="",
            )

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "session-123",
                        "agent_type": "codex",
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes,
                "SESSION_QUERY_CLI_PATH",
                cli_path,
            ), patch.object(
                sessions_routes.subprocess,
                "run",
                return_value=completed,
            ):
                with self.assertRaises(HTTPException) as context:
                    sessions_routes._run_session_query_cli(
                        "codex",
                        "rollout-demo.jsonl",
                        "Какая была главная цель этой сессии?",
                        make_request(),
                    )

        self.assertEqual(context.exception.status_code, 502)
        self.assertEqual(context.exception.detail, "Session query CLI returned invalid JSON.")


if __name__ == "__main__":
    unittest.main()
