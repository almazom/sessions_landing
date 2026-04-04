import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MAIN = REPO_ROOT / "tools" / "extract-intent" / "main.py"
MODULE_SPEC = importlib.util.spec_from_file_location("extract_intent_main", CLI_MAIN)
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(MODULE)


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


class ExtractIntentTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_mode_returns_json_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                    {"role": "user", "content": "проверить published flow через playwright"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--provider-chain",
                "local",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["meta"]["tool"], "extract-intent")
            self.assertEqual(payload["meta"]["selected_provider"], "local")
            self.assertEqual(payload["meta"]["processing_provider"], "local")
            self.assertEqual(payload["meta"]["summary_source"], "local_fallback")
            self.assertNotIn("path", payload["source"])
            self.assertEqual(payload["source"]["harness_provider"], "")
            self.assertEqual(
                payload["intent"]["summary"],
                "Пользователь хочет починить фильтр сегодня, исправить latest карточку и показать полный путь.",
            )
            self.assertEqual(payload["intent"]["steps"], [
                "починить фильтр сегодня",
                "исправить latest карточку",
                "показать полный путь",
                "проверить published flow",
            ])

    def test_pretty_mode_renders_numbered_terminal_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--provider-chain",
                "local",
                "--state-file",
                str(state_path),
                "--pretty",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("🧭 Вектор намерений", completed.stdout)
            self.assertIn("📝 Пользователь хочет", completed.stdout)
            self.assertNotIn("📁", completed.stdout)
            self.assertNotIn("🤖", completed.stdout)
            self.assertIn("① починить фильтр сегодня", completed.stdout)
            self.assertIn("② исправить latest карточку", completed.stdout)
            self.assertIn("③ показать полный путь", completed.stdout)
            self.assertNotIn('"meta"', completed.stdout)

    def test_project_mode_resolves_latest_session_before_extracting_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_path = root / "sessions_landing"
            qwen_root = root / "qwen"
            session_path = qwen_root / "-tmp" / f"-{project_path.as_posix().strip('/').replace('/', '-')}" / "chats" / "latest.jsonl"
            state_path = root / "provider-state.json"

            write_jsonl(
                session_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            config_path = root / "providers.json"
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "default_providers": ["qwen"],
                        "providers": {
                            "qwen": {
                                "root": str(qwen_root),
                                "include": ["**/chats/*.jsonl"],
                                "exclude": [],
                            }
                        },
                    },
                    handle,
                    ensure_ascii=False,
                )

            completed = self.run_cli(
                "--project",
                str(project_path),
                "--providers-config",
                str(config_path),
                "--provider-chain",
                "local",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["meta"]["selected_provider"], "local")
            self.assertEqual(payload["source"]["harness_provider"], "qwen")
            self.assertEqual(payload["source"]["provider"], "qwen")
            self.assertEqual(
                payload["intent"]["summary"],
                "Пользователь хочет починить фильтр сегодня, исправить latest карточку и показать полный путь.",
            )

    def test_project_mode_accepts_single_provider_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_path = root / "sessions_landing"
            qwen_root = root / "qwen"
            session_path = qwen_root / "-tmp" / f"-{project_path.as_posix().strip('/').replace('/', '-')}" / "chats" / "latest.jsonl"
            state_path = root / "provider-state.json"

            write_jsonl(
                session_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            config_path = root / "providers.json"
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "default_providers": ["qwen"],
                        "providers": {
                            "qwen": {
                                "root": str(qwen_root),
                                "include": ["**/chats/*.jsonl"],
                                "exclude": [],
                            }
                        },
                    },
                    handle,
                    ensure_ascii=False,
                )

            completed = self.run_cli(
                "--project",
                str(project_path),
                "--hp",
                "qwen",
                "--providers-config",
                str(config_path),
                "--provider-chain",
                "local",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["source"]["harness_provider"], "qwen")
            self.assertEqual(payload["source"]["provider"], "qwen")

    def test_pretty_project_mode_shows_harness_and_processing_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_path = root / "sessions_landing"
            qwen_root = root / "qwen"
            session_path = qwen_root / "-tmp" / f"-{project_path.as_posix().strip('/').replace('/', '-')}" / "chats" / "latest.jsonl"
            state_path = root / "provider-state.json"

            write_jsonl(
                session_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            config_path = root / "providers.json"
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "default_providers": ["qwen"],
                        "providers": {
                            "qwen": {
                                "root": str(qwen_root),
                                "include": ["**/chats/*.jsonl"],
                                "exclude": [],
                            }
                        },
                    },
                    handle,
                    ensure_ascii=False,
                )

            completed = self.run_cli(
                "--project",
                str(project_path),
                "--hp",
                "qwen",
                "--pp",
                "local",
                "--providers-config",
                str(config_path),
                "--state-file",
                str(state_path),
                "--pretty",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("🧩 harness: qwen · processing: local", completed.stdout)

    def test_processing_provider_alias_maps_to_single_summarizer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--processing-provider",
                "local",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["meta"]["selected_provider"], "local")
            self.assertEqual(payload["meta"]["processing_provider"], "local")

    def test_pp_alias_maps_to_processing_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить фильтр сегодня"},
                    {"role": "user", "content": "исправить latest карточку"},
                    {"role": "user", "content": "показать полный путь файла"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--pp",
                "local",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["meta"]["selected_provider"], "local")
            self.assertEqual(payload["meta"]["processing_provider"], "local")

    def test_auto_processing_chain_excludes_same_harness_provider(self) -> None:
        resolved = MODULE.resolve_effective_processing_chain(
            base_dir=CLI_MAIN.parent,
            processing_provider=None,
            provider_chain="auto",
            harness_provider="pi",
        )
        self.assertEqual(resolved, "gemini,claude,qwen")

    def test_root_wrapper_can_be_copied_to_local_bin_after_repo_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            launcher_dir = home / ".local" / "bin"
            launcher_path = launcher_dir / "extract-intent"
            launcher_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "scripts" / "extract-intent", launcher_path)
            launcher_path.chmod(0o755)

            repo_root = home / "zoo" / "renamed_agent_nexus"
            tool_path = repo_root / "tools" / "extract-intent" / "extract-intent"
            tool_path.parent.mkdir(parents=True, exist_ok=True)
            (repo_root / "PROTOCOL.json").write_text("{}\n", encoding="utf-8")
            tool_path.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'resolved:%s\\n' \"$0\"\n",
                encoding="utf-8",
            )
            tool_path.chmod(0o755)

            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{launcher_dir}:{env.get('PATH', '')}"

            completed = subprocess.run(
                [str(launcher_path)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(str(tool_path), completed.stdout.strip())

    def test_track_json_mode_creates_baseline_then_reports_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            track_path = root / "state.json"
            track_state_dir = root / "track-state"
            track_path.write_text(
                json.dumps({"status": "ready", "count": 1, "meta": {"updated_at": "t1"}}, ensure_ascii=False),
                encoding="utf-8",
            )

            first = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertEqual(first_payload["change"]["summary"], "Базовая точка сохранена.")
            self.assertEqual(first_payload["change"]["stats"]["status"], "baseline_created")
            self.assertEqual(first_payload["change"]["steps"], [])

            track_path.write_text(
                json.dumps(
                    {"status": "failed", "count": 4, "meta": {"updated_at": "t2"}, "errors": ["auth failed"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            second = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
                "--ignore-path",
                "meta.updated_at",
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            payload = json.loads(second.stdout)
            self.assertEqual(payload["meta"]["summary_source"], "local_fallback")
            self.assertEqual(payload["source"]["kind"], "json")
            self.assertEqual(payload["change"]["stats"]["added_paths"], 1)
            self.assertEqual(payload["change"]["stats"]["changed_paths"], 2)
            self.assertIn("ошибки авторизации", payload["change"]["steps"])

    def test_track_log_mode_ignores_noise_and_auto_advances_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            track_path = root / "app.log"
            track_state_dir = root / "track-state"
            track_path.write_text("INFO boot\n", encoding="utf-8")

            first = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(first.returncode, 0, first.stderr)

            with open(track_path, "a", encoding="utf-8") as handle:
                handle.write("heartbeat ok\n")
                handle.write("heartbeat ok\n")

            second = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
                "--ignore-line",
                "heartbeat",
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertEqual(second_payload["meta"]["summary_source"], "deterministic")
            self.assertEqual(second_payload["change"]["summary"], "Содержательных изменений нет.")
            self.assertEqual(second_payload["change"]["stats"]["status"], "no_material_changes")
            self.assertEqual(second_payload["change"]["stats"]["appended_lines"], 2)

            third = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
                "--ignore-line",
                "heartbeat",
            )
            self.assertEqual(third.returncode, 0, third.stderr)
            third_payload = json.loads(third.stdout)
            self.assertEqual(third_payload["change"]["stats"]["appended_lines"], 0)

    def test_track_log_no_advance_keeps_previous_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            track_path = root / "app.log"
            track_state_dir = root / "track-state"
            track_path.write_text("INFO boot\n", encoding="utf-8")

            baseline = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            with open(track_path, "a", encoding="utf-8") as handle:
                handle.write("ERROR auth failed\n")

            first_change = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
                "--no-advance",
            )
            self.assertEqual(first_change.returncode, 0, first_change.stderr)
            first_payload = json.loads(first_change.stdout)
            self.assertEqual(first_payload["change"]["stats"]["appended_lines"], 1)
            self.assertIn("ошибки авторизации", first_payload["change"]["steps"])

            second_change = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(second_change.returncode, 0, second_change.stderr)
            second_payload = json.loads(second_change.stdout)
            self.assertEqual(second_payload["change"]["stats"]["appended_lines"], 1)

    def test_reset_track_replaces_saved_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            track_path = root / "state.json"
            track_state_dir = root / "track-state"
            track_path.write_text(json.dumps({"status": "ready"}, ensure_ascii=False), encoding="utf-8")

            first = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(first.returncode, 0, first.stderr)

            track_path.write_text(json.dumps({"status": "failed"}, ensure_ascii=False), encoding="utf-8")
            reset = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
                "--reset-track",
            )
            self.assertEqual(reset.returncode, 0, reset.stderr)
            reset_payload = json.loads(reset.stdout)
            self.assertEqual(reset_payload["change"]["summary"], "Базовая точка обновлена.")
            self.assertEqual(reset_payload["change"]["stats"]["status"], "baseline_reset")

            after_reset = self.run_cli(
                "--track",
                str(track_path),
                "--provider-chain",
                "local",
                "--track-state-dir",
                str(track_state_dir),
            )
            self.assertEqual(after_reset.returncode, 0, after_reset.stderr)
            after_reset_payload = json.loads(after_reset.stdout)
            self.assertEqual(after_reset_payload["change"]["summary"], "Содержательных изменений нет.")


if __name__ == "__main__":
    unittest.main()
