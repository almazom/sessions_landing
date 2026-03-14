from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.interactive.real_session_parity_fixture import build_real_session_parity_fixture


REPO_ROOT = Path(__file__).resolve().parents[2]
START_PUBLISHED_SCRIPT = REPO_ROOT / "scripts" / "start_published.sh"
FRONTEND_DIR = REPO_ROOT / "frontend"
PLAYWRIGHT_COMMAND = [
    "npx",
    "playwright",
    "test",
    "e2e/interactive-session.spec.ts",
]
DEFAULT_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class InteractiveBrowserE2EResult:
    base_url: str
    returncode: int
    stdout: str
    stderr: str


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def ensure_published_stack() -> None:
    env = os.environ.copy()
    env["NEXUS_PLAYWRIGHT_CHECK_ENABLED"] = "0"
    completed = _run_command(
        [str(START_PUBLISHED_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"failed to start published stack: {detail}")


def run_interactive_browser_e2e(
    *,
    base_url: str,
    ensure_stack: bool = True,
    grep: str | None = None,
) -> InteractiveBrowserE2EResult:
    parity_fixture = build_real_session_parity_fixture()

    if ensure_stack:
        ensure_published_stack()

    env = os.environ.copy()
    env["NEXUS_PUBLIC_URL"] = base_url
    env["NEXUS_INTERACTIVE_PARITY_ARTIFACT_ID"] = parity_fixture.artifact_id
    env["NEXUS_INTERACTIVE_PARITY_ARTIFACT_PATH"] = str(parity_fixture.artifact_path)
    env["NEXUS_INTERACTIVE_PARITY_SESSION_ID"] = parity_fixture.session_id
    env["NEXUS_INTERACTIVE_PARITY_PROMPT"] = parity_fixture.browser_prompt
    env["NEXUS_INTERACTIVE_PARITY_EXPECTED_REPLY"] = parity_fixture.expected_browser_reply
    command = list(PLAYWRIGHT_COMMAND)
    if grep:
        command.extend(["--grep", grep])
    completed = _run_command(
        command,
        cwd=FRONTEND_DIR,
        env=env,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    )

    return InteractiveBrowserE2EResult(
        base_url=base_url,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
