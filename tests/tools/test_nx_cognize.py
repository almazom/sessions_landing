import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MAIN = REPO_ROOT / "tools" / "nx-cognize" / "main.py"


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


class NxCognizeTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_intent_vector_ru_prompt_returns_semantic_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить latest карточку"},
                    {"role": "assistant", "content": "working"},
                    {"role": "user", "content": "показывать полный путь файла"},
                    {"role": "user", "content": "проверить published flow через playwright"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--provider-chain",
                "local",
                "--prompt-id",
                "intent-vector-ru",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["meta"]["prompt_id"], "intent-vector-ru")
            self.assertEqual(payload["meta"]["selected_provider"], "local")
            self.assertEqual(payload["summary"]["intent_bullets"], payload["summary"]["intent_steps_ru"])
            self.assertEqual(
                payload["summary"]["summary"],
                "Пользователь хочет исправить latest карточку, показать полный путь и проверить published flow.",
            )
            self.assertEqual(
                payload["summary"]["intent_steps_ru"],
                [
                    "исправить latest карточку",
                    "показать полный путь",
                    "проверить published flow",
                ],
            )

    def test_session_summary_prompt_keeps_compatibility_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            state_path = root / "provider-state.json"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "исправить фильтр сегодня"},
                    {"role": "user", "content": "сделать latest корректным"},
                    {"role": "user", "content": "усилить e2e проверку"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--provider-chain",
                "local",
                "--prompt-id",
                "session-summary",
                "--state-file",
                str(state_path),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["meta"]["prompt_id"], "session-summary")
            self.assertIn("intent_steps_ru", payload["summary"])
            self.assertGreaterEqual(len(payload["summary"]["intent_steps_ru"]), 3)
            self.assertEqual(payload["summary"]["intent_bullets"], payload["summary"]["intent_steps_ru"])


if __name__ == "__main__":
    unittest.main()
