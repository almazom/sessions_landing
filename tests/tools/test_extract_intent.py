import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MAIN = REPO_ROOT / "tools" / "extract-intent" / "main.py"


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
            self.assertEqual(payload["meta"]["summary_source"], "local_fallback")
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
            self.assertIn("① починить фильтр сегодня", completed.stdout)
            self.assertIn("② исправить latest карточку", completed.stdout)
            self.assertIn("③ показать полный путь", completed.stdout)
            self.assertNotIn('"meta"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
