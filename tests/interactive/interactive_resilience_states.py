from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_HELPER_PATH = REPO_ROOT / "frontend" / "lib" / "interactive-state.ts"
SHELL_COMPONENT_PATH = REPO_ROOT / "frontend" / "components" / "InteractiveSessionShell.tsx"

REQUIRED_STATE_MARKERS = [
    "Reconnecting to runtime",
    "Session is busy",
    "Degraded snapshot",
    "runtime_identity.source === 'recovered'",
    "!payload.replay.history_complete",
]
REQUIRED_SHELL_MARKERS = [
    "Initialization failed",
    "Interactive bootstrap could not start for this session",
    "routeState.alerts.map",
    "alertToneClasses",
]


class InteractiveResilienceStatesBroken(FileNotFoundError):
    """Raised when the interactive resilience states are missing or incomplete."""


@dataclass(frozen=True)
class InteractiveResilienceStatesSnapshot:
    state_helper_path: Path
    shell_component_path: Path
    state_markers: list[str]
    shell_markers: list[str]


def _read_required_file(path: Path, *, label: str) -> str:
    if not path.exists():
        raise InteractiveResilienceStatesBroken(f"{label} is missing: {path}")
    return path.read_text(encoding="utf-8")


def build_interactive_resilience_states_snapshot(
    *,
    state_helper_path: Path | None = None,
    shell_component_path: Path | None = None,
) -> InteractiveResilienceStatesSnapshot:
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

    state_markers = [
        marker
        for marker in REQUIRED_STATE_MARKERS
        if marker in state_source
    ]
    if state_markers != REQUIRED_STATE_MARKERS:
        raise InteractiveResilienceStatesBroken(
            f"interactive resilience states are incomplete in helper: {resolved_state_helper_path}"
        )

    shell_markers = [
        marker
        for marker in REQUIRED_SHELL_MARKERS
        if marker in shell_source
    ]
    if shell_markers != REQUIRED_SHELL_MARKERS:
        raise InteractiveResilienceStatesBroken(
            f"interactive resilience states are incomplete in shell: {resolved_shell_component_path}"
        )

    return InteractiveResilienceStatesSnapshot(
        state_helper_path=resolved_state_helper_path,
        shell_component_path=resolved_shell_component_path,
        state_markers=state_markers,
        shell_markers=shell_markers,
    )
