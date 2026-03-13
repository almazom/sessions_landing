"""Helpers for proving an interactive source artifact stays immutable."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

READ_CHUNK_SIZE = 65536


class ArtifactHashMismatchError(RuntimeError):
    """Raised when an artifact no longer matches its stored hash snapshot."""


def _coerce_artifact_path(path: str | Path) -> Path:
    artifact_path = Path(path).expanduser().resolve()
    if not artifact_path.exists():
        raise FileNotFoundError(f"artifact path does not exist: {artifact_path}")
    if not artifact_path.is_file():
        raise ValueError(f"artifact path is not a file: {artifact_path}")
    return artifact_path


def _digest_artifact_file(artifact_path: Path) -> str:
    digest = hashlib.sha256()
    with artifact_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_artifact_sha256(path: str | Path) -> str:
    artifact_path = _coerce_artifact_path(path)
    return _digest_artifact_file(artifact_path)


def build_artifact_hash_snapshot(path: str | Path) -> Dict[str, Any]:
    artifact_path = _coerce_artifact_path(path)
    return {
        "path": str(artifact_path),
        "artifact_name": artifact_path.name,
        "byte_size": artifact_path.stat().st_size,
        "sha256": _digest_artifact_file(artifact_path),
    }


def verify_artifact_hash(
    snapshot: Dict[str, Any],
    artifact_path: str | Path | None = None,
) -> Dict[str, Any]:
    expected_path = artifact_path or snapshot.get("path")
    if not expected_path:
        raise ValueError("artifact hash snapshot must include a path or explicit artifact_path")

    current = build_artifact_hash_snapshot(expected_path)
    expected_hash = snapshot.get("sha256")
    if not expected_hash:
        raise ValueError("artifact hash snapshot must include sha256")

    if current["sha256"] != expected_hash:
        raise ArtifactHashMismatchError(
            f"artifact hash changed for {current['path']}: "
            f"expected {expected_hash}, got {current['sha256']}"
        )

    return current
