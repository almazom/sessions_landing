from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .backend_harness import build_interactive_backend_harness
from .playwright_skeleton import (
    InteractivePlaywrightSkeletonNotFound,
    build_interactive_playwright_skeleton,
)


class InteractiveFixtureBundleBroken(RuntimeError):
    """Raised when the fixture milestone bundle no longer composes cleanly."""


@dataclass(frozen=True)
class InteractiveFixtureMilestoneBundle:
    harness: str
    fixture_artifact_id: str
    runtime_thread_id: str
    artifact_sha256: str
    detail_route: str
    interactive_route: str
    scenario_names: list[str]
    playwright_command: str


def build_fixture_milestone_bundle(
    *,
    artifact_path: Path | None = None,
    spec_path: Path | None = None,
    config_path: Path | None = None,
) -> InteractiveFixtureMilestoneBundle:
    try:
        harness = build_interactive_backend_harness(artifact_path=artifact_path)
        skeleton = build_interactive_playwright_skeleton(
            spec_path=spec_path,
            config_path=config_path,
        )
    except (FileNotFoundError, InteractivePlaywrightSkeletonNotFound) as error:
        raise InteractiveFixtureBundleBroken(str(error)) from error

    if harness.route["id"] != skeleton.fixture_artifact_id:
        raise InteractiveFixtureBundleBroken(
            "fixture bundle route id does not match Playwright skeleton"
        )
    if harness.route["href"] != skeleton.detail_route:
        raise InteractiveFixtureBundleBroken(
            "fixture bundle detail route does not match Playwright skeleton"
        )

    return InteractiveFixtureMilestoneBundle(
        harness=harness.harness,
        fixture_artifact_id=harness.artifact_path.name,
        runtime_thread_id=harness.runtime_identity["runtime"]["thread_id"],
        artifact_sha256=harness.artifact_hash["sha256"],
        detail_route=harness.route["href"],
        interactive_route=skeleton.interactive_route,
        scenario_names=skeleton.scenario_names,
        playwright_command=skeleton.command,
    )
