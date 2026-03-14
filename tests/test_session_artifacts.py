import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.api.session_artifacts import (
    attach_session_route,
    build_session_detail_payload,
    build_message_anchors,
    list_session_git_commits,
    build_session_route,
)
from backend.api.interactive_identity import InteractiveIdentityNotFound
from backend.parsers.base import SessionParser


class SessionArtifactsTests(unittest.TestCase):
    def test_build_message_anchors_returns_first_middle_last(self) -> None:
        anchors = build_message_anchors([
            "старт",
            "старт",
            "собрать контекст",
            "собрать контекст",
            "починить detail page",
            "добавить message anchors",
            "проверить timeline",
            "проверить timeline",
            "финальный прогон",
        ])

        self.assertEqual(anchors["first"], "старт")
        self.assertEqual(anchors["last"], "финальный прогон")
        self.assertEqual(anchors["middle"], [
            "собрать контекст",
            "починить detail page",
            "добавить message anchors",
            "проверить timeline",
        ])

    def test_build_session_route_uses_filename_for_codex(self) -> None:
        route = build_session_route(
            "codex",
            "/home/pets/.codex/sessions/2026/03/12/rollout-demo.jsonl",
            "session-123",
        )

        self.assertEqual(route["harness"], "codex")
        self.assertEqual(route["id"], "rollout-demo.jsonl")
        self.assertEqual(route["href"], "/sessions/codex/rollout-demo.jsonl")

    def test_build_session_route_uses_parent_uuid_for_kimi(self) -> None:
        route = build_session_route(
            "kimi",
            "/home/pets/.kimi/sessions/hash-value/uuid-value/context.jsonl",
            "ignored",
        )

        self.assertEqual(route["id"], "uuid-value")
        self.assertEqual(route["href"], "/sessions/kimi/uuid-value")

    def test_attach_session_route_supports_latest_payload_shape(self) -> None:
        enriched = attach_session_route({
            "provider": "codex",
            "path": "/home/pets/.codex/sessions/2026/03/12/rollout-demo.jsonl",
            "session_id": "session-123",
        })

        self.assertEqual(enriched["route"]["id"], "rollout-demo.jsonl")

    def test_build_session_detail_payload_counts_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "rollout-demo.jsonl"
            file_path.write_text(
                "\n".join([
                    json.dumps({"type": "session_meta", "payload": {"id": "session-123"}}),
                    json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}),
                ]),
                encoding="utf-8",
            )

            with patch("backend.api.session_artifacts.build_session_git_commit_context", return_value={
                "repository_root": "/home/pets/zoo/agents_sessions_dashboard",
                "commits": [
                    {
                        "hash": "a" * 40,
                        "short_hash": "aaaaaaa",
                        "title": "Add session anchors block",
                        "author_name": "Pets",
                        "committed_at": "2026-03-12T08:04:00+00:00",
                        "committed_at_local": "2026-03-12 11:04:00 MSK",
                    },
                ],
            }):
                payload = build_session_detail_payload(
                    {
                        "session_id": "session-123",
                        "agent_type": "codex",
                        "agent_name": "Codex",
                        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
                        "timestamp_start": "2026-03-12T08:00:00+00:00",
                        "timestamp_end": "2026-03-12T08:05:00+00:00",
                        "status": "completed",
                        "first_user_message": "hello",
                        "last_user_message": "bye",
                        "user_messages": [
                            "hello",
                            "hello",
                            "collect diagnostics",
                            "patch session page",
                            "ship anchors",
                            "bye",
                        ],
                        "user_message_count": 2,
                        "intent_evolution": ["hello", "bye"],
                        "tool_calls": ["exec_command"],
                        "token_usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                        "files_modified": ["frontend/app/page.tsx"],
                        "timeline": [
                            {
                                "timestamp": "2026-03-12T08:00:00+00:00",
                                "event_type": "user_message",
                                "description": "hello",
                                "icon": "💬",
                            },
                            {
                                "timestamp": "2026-03-12T08:01:00+00:00",
                                "event_type": "tool_call",
                                "description": "rg session detail",
                                "icon": "🛠",
                            },
                            {
                                "timestamp": "2026-03-12T08:02:00+00:00",
                                "event_type": "tool_call",
                                "description": "apply_patch",
                                "icon": "🛠",
                            },
                            {
                                "timestamp": "2026-03-12T08:03:00+00:00",
                                "event_type": "file_edit",
                                "description": "frontend/components/SessionDetailClient.tsx",
                                "icon": "📝",
                            },
                            {
                                "timestamp": "2026-03-12T08:04:00+00:00",
                                "event_type": "tool_call",
                                "description": "pnpm test",
                                "icon": "🛠",
                            },
                        ],
                    },
                    file_path,
                )

            self.assertEqual(payload["session"]["record_count"], 2)
            self.assertEqual(payload["session"]["parse_errors"], 0)
            self.assertEqual(payload["session"]["route"]["id"], "rollout-demo.jsonl")
            self.assertEqual(payload["session"]["started_at"], "2026-03-12T08:00:00+00:00")
            self.assertEqual(payload["session"]["ended_at"], "2026-03-12T08:05:00+00:00")
            self.assertEqual(payload["session"]["ended_at_local"], "2026-03-12 11:05:00 MSK")
            self.assertEqual(payload["session"]["duration_human"], "5 мин")
            self.assertEqual(payload["session"]["time_window"]["ended_at"], "2026-03-12T08:05:00+00:00")
            self.assertIn("inside this session window", payload["session"]["time_window"]["scope_summary"])
            self.assertEqual(payload["session"]["message_anchors"]["first"], "hello")
            self.assertEqual(payload["session"]["message_anchors"]["last"], "bye")
            self.assertEqual(payload["session"]["message_anchors"]["middle"], [
                "collect diagnostics",
                "patch session page",
                "ship anchors",
            ])
            self.assertEqual(payload["session"]["topic_threads"], [
                "session detail",
                "session anchors",
                "session page",
                "diagnostics",
            ])
            self.assertEqual(payload["session"]["state_model"]["labels"], ["archived"])
            self.assertEqual(payload["session"]["state_model"]["safety_mode"], "read-only")
            self.assertIn("только для чтения", payload["session"]["state_model"]["summary"])
            self.assertFalse(payload["session"]["evidence_sparsity"]["is_sparse"])
            self.assertEqual(
                payload["session"]["evidence_sparsity"]["present_layers"],
                ["user messages", "artifact timeline", "files modified", "git commits"],
            )
            self.assertEqual(
                [event["event_type"] for event in payload["session"]["timeline"]],
                ["user_message", "tool_call", "tool_call", "file_edit", "tool_call"],
            )
            self.assertEqual(payload["session"]["git_repository_root"], "/home/pets/zoo/agents_sessions_dashboard")
            self.assertEqual(payload["session"]["git_commits"][0]["title"], "Add session anchors block")

    def test_build_session_detail_payload_uses_safe_ask_only_state_when_query_layer_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "rollout-demo.jsonl"
            file_path.write_text(json.dumps({"type": "session_meta"}), encoding="utf-8")

            with patch("backend.api.session_artifacts.build_session_git_commit_context", return_value={
                "repository_root": None,
                "commits": [],
            }):
                payload = build_session_detail_payload(
                    {
                        "session_id": "session-ask-only",
                        "agent_type": "codex",
                        "agent_name": "Codex",
                        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
                        "timestamp_start": "2026-03-12T08:00:00+00:00",
                        "timestamp_end": "2026-03-12T08:05:00+00:00",
                        "status": "completed",
                        "query_enabled": True,
                        "user_messages": ["спросить про timeline"],
                    },
                    file_path,
                )

        self.assertEqual(payload["session"]["state_model"]["labels"], ["archived", "queryable"])
        self.assertEqual(payload["session"]["state_model"]["safety_mode"], "ask-only")
        self.assertTrue(payload["session"]["state_model"]["capabilities"]["can_ask"])
        self.assertFalse(payload["session"]["state_model"]["capabilities"]["can_resume"])

    def test_build_session_detail_payload_uses_resume_allowed_state_when_resume_is_explicitly_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "rollout-demo.jsonl"
            file_path.write_text(json.dumps({"type": "session_meta"}), encoding="utf-8")

            with patch("backend.api.session_artifacts.build_session_git_commit_context", return_value={
                "repository_root": None,
                "commits": [],
            }):
                payload = build_session_detail_payload(
                    {
                        "session_id": "session-resume",
                        "agent_type": "codex",
                        "agent_name": "Codex",
                        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
                        "timestamp_start": "2026-03-12T08:00:00+00:00",
                        "timestamp_end": "2026-03-12T08:05:00+00:00",
                        "status": "active",
                        "resume_supported": True,
                    },
                    file_path,
                )

        self.assertEqual(payload["session"]["state_model"]["labels"], ["live", "restorable"])
        self.assertEqual(payload["session"]["state_model"]["safety_mode"], "resume-allowed")
        self.assertTrue(payload["session"]["state_model"]["capabilities"]["can_resume"])

    def test_build_session_detail_payload_derives_resume_support_for_real_codex_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "rollout-real.jsonl"
            file_path.write_text(json.dumps({"type": "session_meta"}), encoding="utf-8")

            with patch(
                "backend.api.session_artifacts.build_session_git_commit_context",
                return_value={"repository_root": None, "commits": []},
            ), patch(
                "backend.api.session_artifacts.resolve_runtime_identity_from_artifact_route",
                side_effect=InteractiveIdentityNotFound("missing mapping"),
            ):
                payload = build_session_detail_payload(
                    {
                        "session_id": "019ce72f-7e29-7150-8777-1462772b40fc",
                        "agent_type": "codex",
                        "agent_name": "Codex",
                        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
                        "timestamp_start": "2026-03-13T12:32:55+00:00",
                        "timestamp_end": "2026-03-13T12:39:19+00:00",
                        "status": "completed",
                    },
                    file_path,
                )

        self.assertTrue(payload["session"]["state_model"]["capabilities"]["can_resume"])
        self.assertEqual(payload["session"]["state_model"]["safety_mode"], "resume-allowed")
        self.assertEqual(payload["session"]["state_model"]["interactive_session"]["label"], "Interactive mode blocked")
        self.assertIn(
            "no runtime identity mapping",
            payload["session"]["state_model"]["interactive_session"]["detail"],
        )

    def test_build_session_detail_payload_treats_idle_active_session_as_archived_until_restore_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "rollout-demo.jsonl"
            file_path.write_text(json.dumps({"type": "session_meta"}), encoding="utf-8")

            with patch("backend.api.session_artifacts.build_session_git_commit_context", return_value={
                "repository_root": None,
                "commits": [],
            }):
                payload = build_session_detail_payload(
                    {
                        "session_id": "session-idle",
                        "agent_type": "gemini",
                        "agent_name": "Gemini",
                        "cwd": "~/.gemini/tmp/agents-sessions-dashboard",
                        "timestamp_start": "2026-03-10T08:00:00+00:00",
                        "timestamp_end": "2026-03-10T08:05:00+00:00",
                        "status": "active",
                        "user_messages": ["check published stack"],
                    },
                    file_path,
                    live_within_minutes=0,
                    active_within_minutes=0,
                )

        self.assertEqual(payload["session"]["activity_state"], "idle")
        self.assertEqual(payload["session"]["state_model"]["labels"], ["archived"])
        self.assertEqual(payload["session"]["state_model"]["safety_mode"], "read-only")
        self.assertIn("recent activity уже idle", payload["session"]["state_model"]["summary"])
        self.assertIn(
            "The source still says active, but the recent activity window is already cold.",
            payload["session"]["state_model"]["rationale"],
        )
        self.assertTrue(payload["session"]["evidence_sparsity"]["is_sparse"])
        self.assertEqual(payload["session"]["evidence_sparsity"]["present_layers"], ["user messages"])
        self.assertEqual(
            payload["session"]["evidence_sparsity"]["missing_layers"],
            ["artifact timeline", "files modified", "git commits"],
        )

    def test_build_timeline_keeps_non_consecutive_duplicate_event_types(self) -> None:
        class DummyParser(SessionParser):
            def parse_file(self, file_path: Path):  # pragma: no cover - helper stub
                raise NotImplementedError

            def parse_line(self, line: str, context: dict):  # pragma: no cover - helper stub
                raise NotImplementedError

        parser = DummyParser()
        timeline = parser.build_timeline([
            {
                "timestamp": "2026-03-12T08:00:00+00:00",
                "type": "tool_call",
                "description": "rg session detail",
            },
            {
                "timestamp": "2026-03-12T08:01:00+00:00",
                "type": "tool_call",
                "description": "rg session detail again",
            },
            {
                "timestamp": "2026-03-12T08:02:00+00:00",
                "type": "file_edit",
                "description": "update SessionDetailClient",
            },
            {
                "timestamp": "2026-03-12T08:03:00+00:00",
                "type": "tool_call",
                "description": "pnpm test",
            },
        ])

        self.assertEqual(
            [event.event_type for event in timeline],
            ["tool_call", "file_edit", "tool_call"],
        )

    def test_list_session_git_commits_reads_commit_titles_for_session_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            frontend_dir = repo_root / "frontend"
            frontend_dir.mkdir()

            with patch("backend.api.session_artifacts.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(
                        args=["git"],
                        returncode=0,
                        stdout=f"{repo_root}\n",
                        stderr="",
                    ),
                    subprocess.CompletedProcess(
                        args=["git"],
                        returncode=0,
                        stdout=(
                            "1234567890abcdef1234567890abcdef12345678\x1f1234567\x1f2026-03-12T08:02:00+00:00\x1fPets\x1fAdd session detail route\x1e"
                            "abcdef1234567890abcdef1234567890abcdef12\x1fabcdef1\x1f2026-03-12T08:04:00+00:00\x1fPets\x1fAdd git commit block\x1e"
                        ),
                        stderr="",
                    ),
                ]

                payload = list_session_git_commits(
                    cwd=str(frontend_dir),
                    started_at="2026-03-12T08:00:00+00:00",
                    ended_at="2026-03-12T08:05:00+00:00",
                    timezone_name="Europe/Moscow",
                )

        self.assertEqual(payload["repository_root"], str(repo_root))
        self.assertEqual(
            [commit["title"] for commit in payload["commits"]],
            ["Add session detail route", "Add git commit block"],
        )
        self.assertEqual(payload["commits"][0]["short_hash"], "1234567")
        self.assertEqual(payload["commits"][1]["author_name"], "Pets")


if __name__ == "__main__":
    unittest.main()
