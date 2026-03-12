import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MAIN = REPO_ROOT / "tools" / "nx-session-query" / "main.py"
MODULE_SPEC = importlib.util.spec_from_file_location("nx_session_query_main", CLI_MAIN)
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(MODULE)


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


class SessionQueryTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_MAIN), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_mode_returns_structured_local_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить detail page и добавить evidence matrix"},
                    {"role": "assistant", "content": "Сначала проверю SessionDetailClient.tsx"},
                    {"type": "tool_call", "description": "rg evidence matrix"},
                    {"role": "user", "content": "связать commits с files modified"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--question",
                "Какая была главная цель этой сессии?",
                "--harness-provider",
                "codex",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["meta"]["tool"], "nx-session-query")
            self.assertEqual(payload["meta"]["answer_source"], "local_artifact")
            self.assertEqual(payload["source"]["harness_provider"], "codex")
            self.assertEqual(payload["source"]["format"], "jsonl")
            self.assertEqual(payload["source"]["record_count"], 4)
            self.assertEqual(payload["source"]["user_message_count"], 2)
            self.assertEqual(payload["answer"]["mode"], "ask-only")
            self.assertIn("главный фокус", payload["answer"]["response"])
            self.assertGreaterEqual(payload["answer"]["confidence"], 0.5)
            self.assertEqual(payload["answer"]["evidence"][0]["kind"], "user_message")
            self.assertIn("detail page", payload["answer"]["evidence"][0]["excerpt"])

    def test_pretty_mode_renders_answer_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.json"
            source_path.write_text(
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "проверить ask flow"},
                            {"role": "assistant", "content": "Сначала соберу evidence"},
                        ],
                        "timeline": [
                            {"event_type": "tool_call", "description": "rg session query"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--question",
                "Что происходило в этой сессии?",
                "--pretty",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("🧠 Ask This Session", completed.stdout)
            self.assertIn("❓ Что происходило в этой сессии?", completed.stdout)
            self.assertIn("🔎 Evidence", completed.stdout)
            self.assertIn("[User message]", completed.stdout)

    def test_low_overlap_question_returns_limitations_about_weak_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "session.jsonl"
            write_jsonl(
                source_path,
                [
                    {"role": "user", "content": "починить detail page"},
                    {"role": "assistant", "content": "Добавлю timeline блок"},
                ],
            )

            completed = self.run_cli(
                "--input",
                str(source_path),
                "--question",
                "Какой внешний API ключ использовался?",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)

            self.assertLessEqual(payload["answer"]["confidence"], 0.65)
            self.assertTrue(any("token overlap" in item for item in payload["answer"]["limitations"]))


if __name__ == "__main__":
    unittest.main()
