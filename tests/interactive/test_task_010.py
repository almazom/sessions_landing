from __future__ import annotations

import unittest
from backend.api.interactive_identity import (
    InteractiveIdentityNotFound,
    resolve_runtime_identity_from_artifact_route,
)


class Task010IdentityResolverHappyPathTests(unittest.TestCase):
    def test_green_resolves_runtime_identity_from_artifact_route(self) -> None:
        resolved = resolve_runtime_identity_from_artifact_route(
            harness="codex",
            artifact_route_id="rollout-interactive-fixture.jsonl",
        )

        self.assertEqual(resolved["artifact"]["harness"], "codex")
        self.assertEqual(resolved["artifact"]["route_id"], "rollout-interactive-fixture.jsonl")
        self.assertEqual(resolved["artifact"]["session_id"], "sess-fixture-codex-001")
        self.assertEqual(resolved["runtime"]["thread_id"], "thread-fixture-codex-001")
        self.assertEqual(resolved["runtime"]["transport"], "codex_exec_json")
        self.assertEqual(resolved["runtime"]["source"], "fixture")

    def test_red_missing_artifact_route_raises_not_found(self) -> None:
        with self.assertRaises(InteractiveIdentityNotFound):
            resolve_runtime_identity_from_artifact_route(
                harness="codex",
                artifact_route_id="missing-rollout.jsonl",
            )


if __name__ == "__main__":
    unittest.main()
