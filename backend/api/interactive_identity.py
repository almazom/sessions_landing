"""Helpers for mapping an artifact route to a resumable runtime identity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "interactive" / "codex" / "runtime_identity.json"
RUNTIME_IDENTITY_SCHEMA_PATH = REPO_ROOT / "contracts" / "interactive-runtime-identity.schema.json"
ARTIFACT_IDENTITY_KEYS = ("harness", "route_id", "session_id", "source_file")
RUNTIME_IDENTITY_KEYS = ("thread_id", "session_id", "transport", "source")


class InteractiveIdentityNotFound(LookupError):
    """Raised when no runtime identity mapping exists for the artifact route."""


def _load_json_object(path: Path, *, label: str) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")

    return payload


def load_runtime_identity_schema(path: Path | None = None) -> Dict[str, Any]:
    schema_path = path or RUNTIME_IDENTITY_SCHEMA_PATH
    return _load_json_object(schema_path, label="runtime identity schema")


def load_runtime_identity_fixture(path: Path | None = None) -> Dict[str, Any]:
    fixture_path = path or DEFAULT_FIXTURE_PATH
    payload = _load_json_object(fixture_path, label="runtime identity fixture")

    if not isinstance(payload.get("mappings"), list):
        raise ValueError("runtime identity fixture must be an object with a mappings list")

    return payload


def validate_runtime_identity_fixture(
    fixture_payload: Dict[str, Any],
    *,
    schema_payload: Dict[str, Any],
) -> None:
    if sorted(fixture_payload.keys()) != sorted(schema_payload.get("required", [])):
        raise ValueError("runtime identity fixture does not match schema top-level keys")

    mappings = fixture_payload.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("runtime identity fixture must contain at least one mapping")

    runtime_properties = (
        schema_payload.get("definitions", {})
        .get("runtimeIdentity", {})
        .get("properties", {})
    )
    valid_transports = runtime_properties.get("transport", {}).get("enum", [])
    valid_sources = runtime_properties.get("source", {}).get("enum", [])

    for mapping in mappings:
        artifact = mapping.get("artifact")
        runtime = mapping.get("runtime")
        if not isinstance(artifact, dict) or not isinstance(runtime, dict):
            raise ValueError("runtime identity mapping must contain artifact and runtime objects")
        if not all(isinstance(artifact.get(key), str) for key in ARTIFACT_IDENTITY_KEYS):
            raise ValueError("runtime identity artifact payload is incomplete")
        if not all(isinstance(runtime.get(key), str) for key in RUNTIME_IDENTITY_KEYS):
            raise ValueError("runtime identity runtime payload is incomplete")
        if runtime["transport"] not in valid_transports:
            raise ValueError("runtime identity transport is not allowed by schema")
        if runtime["source"] not in valid_sources:
            raise ValueError("runtime identity source is not allowed by schema")


def resolve_runtime_identity(
    fixture_payload: Dict[str, Any],
    *,
    harness: str,
    artifact_route_id: str,
) -> Dict[str, Any]:
    for mapping in fixture_payload.get("mappings", []):
        artifact = mapping.get("artifact") or {}
        if artifact.get("harness") != harness:
            continue
        if artifact.get("route_id") != artifact_route_id:
            continue
        return mapping

    raise InteractiveIdentityNotFound(
        f"missing runtime identity mapping for {harness}/{artifact_route_id}"
    )


def resolve_runtime_identity_from_artifact_route(
    *,
    harness: str,
    artifact_route_id: str,
    fixture_path: Path | None = None,
    schema_path: Path | None = None,
) -> Dict[str, Any]:
    schema_payload = load_runtime_identity_schema(schema_path)
    fixture_payload = load_runtime_identity_fixture(fixture_path)
    validate_runtime_identity_fixture(fixture_payload, schema_payload=schema_payload)
    return resolve_runtime_identity(
        fixture_payload,
        harness=harness,
        artifact_route_id=artifact_route_id,
    )
