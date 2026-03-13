from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.api.interactive_boot import build_interactive_boot_payload
from .boot_payload_schema import (
    InteractiveBootPayloadSchemaNotFound,
    load_boot_payload_schema,
    validate_boot_payload_against_schema,
)
from .fixtures import codex_fixture_path, load_codex_runtime_identity
from .runtime_identity_schema import (
    InteractiveRuntimeIdentitySchemaNotFound,
    load_runtime_identity_schema,
    validate_runtime_identity_fixture_against_schema,
)
from .sdk_sidecar_probe import (
    CodexSdkSidecarProbeNotFound,
    build_codex_sdk_sidecar_probe,
)
from .transport_adr import (
    InteractiveTransportAdrNotFound,
    load_transport_adr,
)
from .transport_matrix import (
    InteractiveTransportMatrixReferenceNotFound,
    build_codex_transport_matrix,
)
from .transport_probe import (
    InteractiveTransportProbeNotReady,
    run_transport_probe,
)


class InteractiveTransportBootBundleBroken(RuntimeError):
    """Raised when the transport/identity/boot milestone bundle is incomplete."""


@dataclass(frozen=True)
class InteractiveTransportBootMilestoneBundle:
    primary_transport: str
    transport_keys: tuple[str, ...]
    sdk_sidecar_status: str
    sdk_rejects_browser_transport: bool
    runtime_identity_valid: bool
    runtime_identity_transport: str
    boot_payload_valid: bool
    boot_payload_transport: str
    evidence_paths: tuple[str, ...]


def _fixture_session_payload() -> dict[str, object]:
    return {
        "session_id": "sess-fixture-codex-001",
        "agent_type": "codex",
        "agent_name": "Codex",
        "cwd": "/home/pets/zoo/agents_sessions_dashboard",
        "status": "active",
        "resume_supported": True,
    }


def build_transport_boot_milestone_bundle(
    *,
    reference_overrides: Mapping[str, str] | None = None,
    artifact_path: Path | None = None,
) -> InteractiveTransportBootMilestoneBundle:
    resolved_artifact_path = (artifact_path or codex_fixture_path()).resolve()

    try:
        matrix = build_codex_transport_matrix(reference_overrides=reference_overrides)
        probe = run_transport_probe(
            artifact_path=resolved_artifact_path,
            reference_overrides=reference_overrides,
        )
        adr = load_transport_adr()
        sdk_verdict = build_codex_sdk_sidecar_probe(reference_overrides=reference_overrides)
        runtime_schema = load_runtime_identity_schema()
        runtime_fixture = load_codex_runtime_identity()
        boot_schema = load_boot_payload_schema()
        boot_payload = build_interactive_boot_payload(
            _fixture_session_payload(),
            resolved_artifact_path,
        )
    except (
        InteractiveBootPayloadSchemaNotFound,
        InteractiveRuntimeIdentitySchemaNotFound,
        InteractiveTransportAdrNotFound,
        InteractiveTransportMatrixReferenceNotFound,
        InteractiveTransportProbeNotReady,
        CodexSdkSidecarProbeNotFound,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as error:
        raise InteractiveTransportBootBundleBroken(str(error)) from error

    runtime_identity_valid = validate_runtime_identity_fixture_against_schema(
        runtime_fixture,
        runtime_schema,
    )
    boot_payload_valid = validate_boot_payload_against_schema(boot_payload, boot_schema)
    if not runtime_identity_valid:
        raise InteractiveTransportBootBundleBroken("runtime identity bundle validation failed")
    if not boot_payload_valid:
        raise InteractiveTransportBootBundleBroken("boot payload bundle validation failed")
    if matrix.primary_transport != adr.primary_browser_transport:
        raise InteractiveTransportBootBundleBroken("transport matrix and ADR disagree on primary transport")
    if probe.primary_transport != matrix.primary_transport:
        raise InteractiveTransportBootBundleBroken("transport probe and matrix disagree on primary transport")

    return InteractiveTransportBootMilestoneBundle(
        primary_transport=matrix.primary_transport,
        transport_keys=tuple(sorted(matrix.entries)),
        sdk_sidecar_status=sdk_verdict.status,
        sdk_rejects_browser_transport="browser_transport" in sdk_verdict.rejected_roles,
        runtime_identity_valid=runtime_identity_valid,
        runtime_identity_transport=runtime_fixture["mappings"][0]["runtime"]["transport"],
        boot_payload_valid=boot_payload_valid,
        boot_payload_transport=str(boot_payload["interactive_session"]["transport"]),
        evidence_paths=(
            str(adr.path),
            str(runtime_schema.path),
            str(boot_schema.path),
            str(resolved_artifact_path),
        )
        + tuple(sdk_verdict.evidence_paths),
    )
