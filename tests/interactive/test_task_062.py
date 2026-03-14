from __future__ import annotations

import unittest

from tests.interactive.browser_e2e_runner import run_interactive_browser_e2e
from tests.interactive.real_session_browser_fixture import build_real_session_browser_fixture


class Task062LocalLiveMotionE2ETests(unittest.TestCase):
    def test_local_live_motion_e2e(self) -> None:
        fixture = build_real_session_browser_fixture()
        result = run_interactive_browser_e2e(
            base_url=fixture.local_base_url,
            grep="interactive prompt roundtrip mutates the real artifact",
        )

        combined_output = "\n".join((result.stdout, result.stderr))
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("interactive prompt roundtrip mutates the real artifact", combined_output)
        self.assertRegex(combined_output, r"\b1 passed\b")

    def test_local_live_motion_e2e_broken(self) -> None:
        result = run_interactive_browser_e2e(
            base_url="http://127.0.0.1:1",
            ensure_stack=False,
            grep="interactive prompt roundtrip mutates the real artifact",
        )

        combined_output = "\n".join((result.stdout, result.stderr))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(
            "ECONNREFUSED" in combined_output
            or "ERR_CONNECTION_REFUSED" in combined_output
            or "net::ERR_CONNECTION_REFUSED" in combined_output,
            combined_output,
        )


if __name__ == "__main__":
    unittest.main()
