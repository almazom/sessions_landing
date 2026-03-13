from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .backend_harness import build_interactive_backend_harness


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYWRIGHT_CONFIG_PATH = REPO_ROOT / "frontend" / "playwright.config.ts"
PLAYWRIGHT_SPEC_PATH = REPO_ROOT / "frontend" / "e2e" / "interactive-session.spec.ts"
PLAYWRIGHT_COMMAND = "cd frontend && npx playwright test e2e/interactive-session.spec.ts"
SCENARIO_PATTERN = re.compile(r"""test\.skip\(\s*['"]([^'"]+)['"]""")


class InteractivePlaywrightSkeletonNotFound(FileNotFoundError):
    """Raised when the interactive Playwright skeleton files are missing."""


@dataclass(frozen=True)
class InteractivePlaywrightSkeleton:
    spec_path: Path
    config_path: Path
    fixture_artifact_id: str
    detail_route: str
    interactive_route: str
    scenario_names: list[str]
    command: str


def _extract_scenario_names(spec_path: Path) -> list[str]:
    return SCENARIO_PATTERN.findall(spec_path.read_text(encoding="utf-8"))


def build_interactive_playwright_skeleton(
    *,
    spec_path: Path | None = None,
    config_path: Path | None = None,
) -> InteractivePlaywrightSkeleton:
    resolved_spec_path = (spec_path or PLAYWRIGHT_SPEC_PATH).resolve()
    if not resolved_spec_path.exists():
        raise InteractivePlaywrightSkeletonNotFound(
            f"interactive Playwright spec is missing: {resolved_spec_path}"
        )

    resolved_config_path = (config_path or PLAYWRIGHT_CONFIG_PATH).resolve()
    if not resolved_config_path.exists():
        raise InteractivePlaywrightSkeletonNotFound(
            f"interactive Playwright config is missing: {resolved_config_path}"
        )

    harness = build_interactive_backend_harness()
    scenario_names = _extract_scenario_names(resolved_spec_path)
    if not scenario_names:
        raise InteractivePlaywrightSkeletonNotFound(
            f"interactive Playwright spec has no skeleton scenarios: {resolved_spec_path}"
        )

    return InteractivePlaywrightSkeleton(
        spec_path=resolved_spec_path,
        config_path=resolved_config_path,
        fixture_artifact_id=harness.artifact_path.name,
        detail_route=harness.route["href"],
        interactive_route=f"{harness.route['href']}/interactive",
        scenario_names=scenario_names,
        command=PLAYWRIGHT_COMMAND,
    )
