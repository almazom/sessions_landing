from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_HELPER_PATH = REPO_ROOT / "frontend" / "lib" / "interactive-state.ts"
SHELL_COMPONENT_PATH = REPO_ROOT / "frontend" / "components" / "InteractiveSessionShell.tsx"

REQUIRED_PHASES = ["ready", "blocked"]
REQUIRED_STATE_MARKERS = [
    "buildInteractiveRouteState",
    "Live timeline",
    "textarea",
    "Send prompt",
    "composer.enabled",
]


class InteractiveLiveStateBroken(FileNotFoundError):
    """Raised when the interactive live timeline/composer state files are missing or incomplete."""


@dataclass(frozen=True)
class InteractiveLiveStateSnapshot:
    state_helper_path: Path
    shell_component_path: Path
    phases: list[str]
    state_markers: list[str]
    has_composer_form: bool


def _read_required_file(path: Path, *, label: str) -> str:
    if not path.exists():
        raise InteractiveLiveStateBroken(f"{label} is missing: {path}")
    return path.read_text(encoding="utf-8")


def build_interactive_live_state_snapshot(
    *,
    state_helper_path: Path | None = None,
    shell_component_path: Path | None = None,
) -> InteractiveLiveStateSnapshot:
    resolved_state_helper_path = (state_helper_path or STATE_HELPER_PATH).resolve()
    resolved_shell_component_path = (shell_component_path or SHELL_COMPONENT_PATH).resolve()

    state_source = _read_required_file(
        resolved_state_helper_path,
        label="interactive state helper",
    )
    shell_source = _read_required_file(
        resolved_shell_component_path,
        label="interactive shell component",
    )

    phases = [phase for phase in REQUIRED_PHASES if f"'{phase}'" in state_source]
    if phases != REQUIRED_PHASES:
        raise InteractiveLiveStateBroken(
            f"interactive state helper is missing required phases: {resolved_state_helper_path}"
        )

    state_markers = [
        marker
        for marker in REQUIRED_STATE_MARKERS
        if marker in state_source or marker in shell_source
    ]
    if state_markers != REQUIRED_STATE_MARKERS:
        raise InteractiveLiveStateBroken(
            f"interactive live state markers are incomplete: {resolved_shell_component_path}"
        )

    return InteractiveLiveStateSnapshot(
        state_helper_path=resolved_state_helper_path,
        shell_component_path=resolved_shell_component_path,
        phases=phases,
        state_markers=state_markers,
        has_composer_form="<form" in shell_source,
    )
