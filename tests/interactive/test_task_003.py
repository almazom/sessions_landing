from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from backend.api.interactive_artifact_hash import (
    ArtifactHashMismatchError,
    build_artifact_hash_snapshot,
    verify_artifact_hash,
)
from tests.interactive.fixtures import codex_fixture_path


class Task003ArtifactHashTests(unittest.TestCase):
    def test_green_artifact_hash_snapshot_is_stable(self) -> None:
        fixture_path = codex_fixture_path()

        snapshot = build_artifact_hash_snapshot(fixture_path)
        verified = verify_artifact_hash(snapshot)

        self.assertEqual(snapshot["path"], str(fixture_path))
        self.assertEqual(snapshot["artifact_name"], fixture_path.name)
        self.assertEqual(
            snapshot["sha256"],
            "321a90865f6b304780dc9d90ba69cb5cb94ff04e6a3d24f2f664e6edd3d548de",
        )
        self.assertEqual(snapshot["byte_size"], 1614)
        self.assertEqual(verified, snapshot)

    def test_red_artifact_hash_detects_mutation(self) -> None:
        fixture_path = codex_fixture_path()
        with tempfile.TemporaryDirectory(prefix="interactive-artifact-hash-") as temp_dir:
            temp_path = Path(temp_dir) / fixture_path.name
            shutil.copy2(fixture_path, temp_path)

            snapshot = build_artifact_hash_snapshot(temp_path)
            with temp_path.open("a", encoding="utf-8") as handle:
                handle.write('\n{"type":"mutation","value":"unexpected"}\n')

            with self.assertRaises(ArtifactHashMismatchError):
                verify_artifact_hash(snapshot)


if __name__ == "__main__":
    unittest.main()
