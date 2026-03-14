import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.deps import User, get_current_user
from backend.api.routes import sessions as sessions_routes


def make_request(request_id: str = "req-test"):
    return SimpleNamespace(state=SimpleNamespace(request_id=request_id))


class SessionRoutesTests(unittest.TestCase):
    @staticmethod
    def _interactive_app(username: str = "admin") -> FastAPI:
        app = FastAPI()
        app.include_router(sessions_routes.router)
        app.dependency_overrides[get_current_user] = lambda: User(
            username=username,
            is_authenticated=True,
            auth_method="test",
        )
        return app

    def test_resolve_session_artifact_derives_resume_support_for_real_codex_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes,
                "build_session_detail_payload",
                side_effect=lambda session_payload, file_path: {
                    "session": session_payload,
                    "file_path": str(file_path),
                },
            ):
                payload = sessions_routes._resolve_session_artifact("codex", "rollout-real.jsonl")

        self.assertTrue(payload["session"]["resume_supported"])
        self.assertEqual(payload["file_path"], str(source_path))

    def test_resolve_session_artifact_marks_query_layer_available_when_cli_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            main_path = Path(tmp_dir) / "main.py"
            main_path.write_text("print('ok')\n", encoding="utf-8")
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
                "SESSION_QUERY_MAIN_PATH",
                main_path,
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

    def test_build_session_query_command_falls_back_to_python_main_when_wrapper_is_not_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            main_path = Path(tmp_dir) / "main.py"
            main_path.write_text("print('ok')\n", encoding="utf-8")
            source_path = Path(tmp_dir) / "rollout-demo.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")

            with patch.object(
                sessions_routes,
                "SESSION_QUERY_CLI_PATH",
                cli_path,
            ), patch.object(
                sessions_routes,
                "SESSION_QUERY_MAIN_PATH",
                main_path,
            ), patch.object(
                sessions_routes.os,
                "access",
                return_value=False,
            ):
                command = sessions_routes._build_session_query_command(
                    source_path,
                    "Какая была главная цель этой сессии?",
                    "codex",
                )

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], str(main_path))
        self.assertEqual(command[command.index("--input") + 1], str(source_path))
        self.assertEqual(command[command.index("--harness-provider") + 1], "codex")

    def test_run_session_query_cli_returns_structured_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cli_path = Path(tmp_dir) / "nx-session-query"
            cli_path.write_text("#!/bin/sh\n", encoding="utf-8")
            main_path = Path(tmp_dir) / "main.py"
            main_path.write_text("print('ok')\n", encoding="utf-8")
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
                sessions_routes,
                "SESSION_QUERY_MAIN_PATH",
                main_path,
            ), patch.object(
                sessions_routes.os,
                "access",
                return_value=True,
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
            main_path = Path(tmp_dir) / "main.py"
            main_path.write_text("print('ok')\n", encoding="utf-8")
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
                sessions_routes,
                "SESSION_QUERY_MAIN_PATH",
                main_path,
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

    def test_run_session_resume_cli_starts_codex_resume_from_recorded_cwd(self) -> None:
        class FakeProcess:
            pid = 4321

            @staticmethod
            def poll():
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")
            cwd_path = Path(tmp_dir) / "workspace"
            cwd_path.mkdir()

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "cwd": str(cwd_path),
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes.subprocess,
                "Popen",
                return_value=FakeProcess(),
            ) as popen_mock, patch.object(
                sessions_routes.time,
                "sleep",
                return_value=None,
            ), patch.object(
                sessions_routes,
                "_publish_resumed_runtime_identity",
                return_value=None,
            ):
                payload = sessions_routes._run_session_resume_cli(
                    "codex",
                    "rollout-real.jsonl",
                    make_request(),
                )

        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["session_id"], "019ce72f-7e29-7150-8777-1462772b40fc")
        self.assertEqual(payload["cwd"], str(cwd_path))
        self.assertEqual(
            payload["interactive_href"],
            "/sessions/codex/rollout-real.jsonl/interactive",
        )
        self.assertTrue(payload["log_path"].endswith(".log"))
        command = popen_mock.call_args.args[0]
        self.assertEqual(command[:4], ["script", "-q", "-f", payload["log_path"]])
        self.assertEqual(command[4:], ["-c", "codex resume 019ce72f-7e29-7150-8777-1462772b40fc"])
        self.assertEqual(popen_mock.call_args.kwargs["cwd"], str(cwd_path))
        self.assertEqual(popen_mock.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(popen_mock.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(popen_mock.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertTrue(popen_mock.call_args.kwargs["start_new_session"])

    def test_run_session_resume_cli_publishes_runtime_identity_after_start(self) -> None:
        class FakeProcess:
            pid = 4321

            @staticmethod
            def poll():
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")
            cwd_path = Path(tmp_dir) / "workspace"
            cwd_path.mkdir()

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "cwd": str(cwd_path),
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes.subprocess,
                "Popen",
                return_value=FakeProcess(),
            ), patch.object(
                sessions_routes.time,
                "sleep",
                return_value=None,
            ), patch.object(
                sessions_routes,
                "_publish_resumed_runtime_identity",
                return_value=None,
            ) as publish_mock:
                payload = sessions_routes._run_session_resume_cli(
                    "codex",
                    "rollout-real.jsonl",
                    make_request(),
                )

        self.assertEqual(payload["status"], "started")
        publish_mock.assert_called_once()
        self.assertEqual(publish_mock.call_args.kwargs["harness"], "codex")
        self.assertEqual(publish_mock.call_args.kwargs["file_path"], source_path)
        self.assertEqual(
            publish_mock.call_args.kwargs["session_id"],
            "019ce72f-7e29-7150-8777-1462772b40fc",
        )
        self.assertEqual(publish_mock.call_args.kwargs["started_at"], payload["started_at"])

    def test_run_session_resume_cli_rejects_non_resumable_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text("{}\n", encoding="utf-8")

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "",
                        "agent_type": "codex",
                        "cwd": "",
                    },
                    source_path,
                ),
            ):
                with self.assertRaises(HTTPException) as context:
                    sessions_routes._run_session_resume_cli(
                        "codex",
                        "rollout-real.jsonl",
                        make_request(),
                    )

        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("not resumable", context.exception.detail)

    def test_build_session_prompt_submit_command_uses_exec_resume_and_stdin_prompt(self) -> None:
        output_path = Path("/tmp/interactive-prompt.txt")

        command = sessions_routes._build_session_prompt_submit_command(
            session_id="019ce72f-7e29-7150-8777-1462772b40fc",
            output_path=output_path,
        )

        self.assertEqual(
            command,
            [
                "codex",
                "exec",
                "resume",
                "--json",
                "-o",
                str(output_path),
                "019ce72f-7e29-7150-8777-1462772b40fc",
                "-",
            ],
        )

    def test_run_session_prompt_submit_cli_requires_artifact_mutation(self) -> None:
        class FakeStdIO:
            def __init__(self, lines: list[str] | None = None):
                self._lines = list(lines or [])
                self.writes: list[str] = []

            def __iter__(self):
                return iter(self._lines)

            def write(self, value: str) -> None:
                self.writes.append(value)

            def close(self) -> None:
                return None

            def read(self) -> str:
                return ""

        class FakeProcess:
            def __init__(self):
                self.stdin = FakeStdIO()
                self.stdout = FakeStdIO([
                    '{"type":"thread.started","thread_id":"019ce72f-7e29-7150-8777-1462772b40fc"}\n',
                    '{"type":"turn.started"}\n',
                    '{"type":"turn.completed","usage":{"output_tokens":4}}\n',
                ])
                self.stderr = FakeStdIO()

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text('{"type":"session_meta","payload":{"id":"019ce72f-7e29-7150-8777-1462772b40fc","cwd":"%s"}}\n' % tmp_dir, encoding="utf-8")

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "cwd": tmp_dir,
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes.subprocess,
                "Popen",
                return_value=FakeProcess(),
            ):
                with self.assertRaises(HTTPException) as context:
                    sessions_routes._run_session_prompt_submit_cli(
                        "codex",
                        "rollout-real.jsonl",
                        prompt_text="Add 2 to the previous result.",
                        actor_id="admin",
                        client_event_id="browser-event-055",
                        request=make_request(),
                    )

        self.assertEqual(context.exception.status_code, 502)
        self.assertIn("did not change", context.exception.detail)

    def test_run_session_prompt_submit_cli_returns_boot_payload_after_artifact_update(self) -> None:
        class FakeStdIO:
            def __init__(self, lines: list[str] | None = None):
                self._lines = list(lines or [])
                self.writes: list[str] = []

            def __iter__(self):
                return iter(self._lines)

            def write(self, value: str) -> None:
                self.writes.append(value)

            def close(self) -> None:
                return None

            def read(self) -> str:
                return ""

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "rollout-real.jsonl"
            source_path.write_text(
                '{"timestamp":"2026-03-14T08:00:00Z","type":"session_meta","payload":{"id":"019ce72f-7e29-7150-8777-1462772b40fc","cwd":"%s","agent_nickname":"Codex"}}\n'
                '{"timestamp":"2026-03-14T08:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Reply with only the final integer. What is 1 + 2?"}]}}\n'
                '{"timestamp":"2026-03-14T08:00:02Z","type":"event_msg","payload":{"type":"task_complete"}}\n'
                % tmp_dir,
                encoding="utf-8",
            )
            output_path = Path(tmp_dir) / "prompt-output.txt"

            class FakeProcess:
                def __init__(self):
                    self.stdin = FakeStdIO()
                    self.stdout = FakeStdIO([
                        '{"type":"thread.started","thread_id":"019ce72f-7e29-7150-8777-1462772b40fc"}\n',
                        '{"type":"turn.started"}\n',
                        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"5"}}\n',
                        '{"type":"turn.completed","usage":{"output_tokens":5}}\n',
                    ])
                    self.stderr = FakeStdIO()

                def wait(self, timeout=None):
                    source_path.write_text(
                        source_path.read_text(encoding="utf-8")
                        + '{"timestamp":"2026-03-14T08:05:00Z","type":"event_msg","payload":{"type":"user_message","message":"Add 2 to the previous result. Reply with only the final integer."}}\n'
                        + '{"timestamp":"2026-03-14T08:05:01Z","type":"event_msg","payload":{"type":"task_complete"}}\n',
                        encoding="utf-8",
                    )
                    output_path.write_text("5\n", encoding="utf-8")
                    return 0

            def fake_popen(*args, **kwargs):
                source_path.write_text(
                    source_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                return FakeProcess()

            with patch.object(
                sessions_routes,
                "_resolve_session_artifact_source",
                return_value=(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "cwd": tmp_dir,
                    },
                    source_path,
                ),
            ), patch.object(
                sessions_routes,
                "_interactive_prompt_output_path",
                return_value=output_path,
            ), patch.object(
                sessions_routes.subprocess,
                "Popen",
                side_effect=fake_popen,
            ):
                payload = sessions_routes._run_session_prompt_submit_cli(
                    "codex",
                    "rollout-real.jsonl",
                    prompt_text="Add 2 to the previous result. Reply with only the final integer.",
                    actor_id="admin",
                    client_event_id="browser-event-056",
                    request=make_request(),
                )

        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["artifact_updated"])
        self.assertEqual(payload["assistant_message"], "5")
        self.assertEqual(
            payload["boot_payload"]["tail"]["items"][0]["text"],
            "Add 2 to the previous result. Reply with only the final integer.",
        )

    def test_interactive_prompt_endpoint_rejects_cross_origin_requests(self) -> None:
        app = self._interactive_app()

        with TestClient(app) as client:
            response = client.post(
                "/api/session-artifacts/codex/rollout-real.jsonl/interactive/prompt",
                json={"text": "Add 2 to the previous result."},
                headers={
                    "origin": "https://evil.example",
                    "host": "dashboard.test",
                    "x-forwarded-proto": "https",
                    "sec-fetch-site": "cross-site",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn("same-origin", response.json()["detail"])

    def test_interactive_prompt_endpoint_returns_updated_artifact_payload(self) -> None:
        app = self._interactive_app()

        with patch.object(
            sessions_routes,
            "_run_session_prompt_submit_cli",
            return_value={
                "status": "completed",
                "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                "cwd": "/tmp/workspace",
                "submitted_text": "Add 2 to the previous result.",
                "artifact_updated": True,
                "artifact_before": {"path": "/tmp/a.jsonl", "artifact_name": "a.jsonl", "byte_size": 10, "sha256": "a" * 64},
                "artifact_after": {"path": "/tmp/a.jsonl", "artifact_name": "a.jsonl", "byte_size": 20, "sha256": "b" * 64},
                "assistant_message": "5",
                "boot_payload": {"version": 1},
                "completed_at": "2026-03-14T09:00:00Z",
            },
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/session-artifacts/codex/rollout-real.jsonl/interactive/prompt",
                    json={"text": "Add 2 to the previous result."},
                    headers={
                        "origin": "https://dashboard.test",
                        "host": "dashboard.test",
                        "x-forwarded-proto": "https",
                        "sec-fetch-site": "same-origin",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assistant_message"], "5")
        self.assertTrue(response.json()["artifact_updated"])
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")


if __name__ == "__main__":
    unittest.main()
