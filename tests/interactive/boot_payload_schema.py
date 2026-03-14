from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOT_PAYLOAD_SCHEMA_PATH = REPO_ROOT / "contracts" / "interactive-boot-payload.schema.json"
BOOT_PAYLOAD_SAMPLE_PATH = REPO_ROOT / "contracts" / "examples" / "interactive-boot-payload.sample.json"
ROUTE_KEYS = ("harness", "route_id", "session_href", "interactive_href")
INTERACTIVE_SESSION_KEYS = ("available", "label", "detail", "href", "transport")
SESSION_KEYS = ("session_id", "agent_name", "cwd", "status", "resume_supported")
RUNTIME_IDENTITY_KEYS = ("thread_id", "session_id", "transport", "source")
ARTIFACT_KEYS = ("path", "artifact_name", "byte_size", "sha256")
TAIL_KEYS = ("items", "summary_hint", "has_more_before")
REPLAY_KEYS = ("items", "history_complete")


class InteractiveBootPayloadSchemaNotFound(FileNotFoundError):
    """Raised when the boot payload schema file is missing or incomplete."""


@dataclass(frozen=True)
class InteractiveBootPayloadSchema:
    path: Path
    version: str
    required_top_level_keys: list[str]
    capability_transport_values: list[str]
    runtime_transport_values: list[str]
    runtime_source_values: list[str]


def _load_json_object(path: Path, *, label: str) -> Dict[str, Any]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise InteractiveBootPayloadSchemaNotFound(f"{label} is missing: {resolved_path}")

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise InteractiveBootPayloadSchemaNotFound(f"{label} must be an object: {resolved_path}")
    return payload


def load_boot_payload_schema(
    schema_path: Path | None = None,
) -> InteractiveBootPayloadSchema:
    resolved_path = (schema_path or BOOT_PAYLOAD_SCHEMA_PATH).resolve()
    payload = _load_json_object(resolved_path, label="interactive boot payload schema")

    try:
        definitions = payload["definitions"]
        capability_transport_values = definitions["interactiveSession"]["properties"]["transport"]["enum"]
        runtime_properties = definitions["runtimeIdentity"]["properties"]
        runtime_transport_values = runtime_properties["transport"]["enum"]
        runtime_source_values = runtime_properties["source"]["enum"]
    except KeyError as error:
        raise InteractiveBootPayloadSchemaNotFound(
            f"interactive boot payload schema is incomplete: {resolved_path}"
        ) from error

    return InteractiveBootPayloadSchema(
        path=resolved_path,
        version=payload["version"],
        required_top_level_keys=payload["required"],
        capability_transport_values=[
            value for value in capability_transport_values if isinstance(value, str)
        ],
        runtime_transport_values=runtime_transport_values,
        runtime_source_values=runtime_source_values,
    )


def load_boot_payload_sample(sample_path: Path | None = None) -> Dict[str, Any]:
    return _load_json_object(
        sample_path or BOOT_PAYLOAD_SAMPLE_PATH,
        label="interactive boot payload sample",
    )


def validate_boot_payload_against_schema(
    payload: Dict[str, Any],
    schema: InteractiveBootPayloadSchema,
) -> bool:
    def has_string_keys(candidate: Dict[str, Any], keys: tuple[str, ...]) -> bool:
        return all(isinstance(candidate.get(key), str) for key in keys)

    if sorted(payload.keys()) != sorted(schema.required_top_level_keys):
        return False
    if not isinstance(payload.get("version"), int):
        return False

    route = payload.get("route")
    session = payload.get("session")
    interactive_session = payload.get("interactive_session")
    runtime_identity = payload.get("runtime_identity")
    artifact = payload.get("artifact")
    tail = payload.get("tail")
    replay = payload.get("replay")

    if not isinstance(route, dict) or not has_string_keys(route, ROUTE_KEYS):
        return False
    if not isinstance(session, dict):
        return False
    if not isinstance(interactive_session, dict):
        return False
    if runtime_identity is not None and not isinstance(runtime_identity, dict):
        return False
    if not isinstance(artifact, dict):
        return False
    if not isinstance(tail, dict):
        return False
    if not isinstance(replay, dict):
        return False

    if not all(key in session for key in SESSION_KEYS):
        return False
    if not all(isinstance(session.get(key), str) for key in SESSION_KEYS[:-1]):
        return False
    if not isinstance(session.get("resume_supported"), bool):
        return False

    if not all(key in interactive_session for key in INTERACTIVE_SESSION_KEYS):
        return False
    if not isinstance(interactive_session.get("available"), bool):
        return False
    if not all(isinstance(interactive_session.get(key), str) for key in ("label", "detail")):
        return False
    href = interactive_session.get("href")
    if href is not None and not isinstance(href, str):
        return False
    interactive_transport = interactive_session.get("transport")
    if interactive_transport is not None and interactive_transport not in schema.capability_transport_values:
        return False

    if runtime_identity is not None:
        if not has_string_keys(runtime_identity, RUNTIME_IDENTITY_KEYS):
            return False
        if runtime_identity["transport"] not in schema.runtime_transport_values:
            return False
        if runtime_identity["source"] not in schema.runtime_source_values:
            return False

    if not all(key in artifact for key in ARTIFACT_KEYS):
        return False
    if not all(isinstance(artifact.get(key), str) for key in ("path", "artifact_name", "sha256")):
        return False
    if not isinstance(artifact.get("byte_size"), int) or artifact["byte_size"] <= 0:
        return False
    if len(artifact["sha256"]) != 64:
        return False

    if not all(key in tail for key in TAIL_KEYS):
        return False
    if not isinstance(tail["items"], list):
        return False
    if tail["summary_hint"] is not None and not isinstance(tail["summary_hint"], str):
        return False
    if not isinstance(tail["has_more_before"], bool):
        return False
    for item in tail["items"]:
        if not isinstance(item, dict):
            return False
        if not all(isinstance(item.get(key), str) for key in ("kind", "text")):
            return False

    if not all(key in replay for key in REPLAY_KEYS):
        return False
    if not isinstance(replay["items"], list):
        return False
    if not isinstance(replay["history_complete"], bool):
        return False
    for item in replay["items"]:
        if not isinstance(item, dict):
            return False
        if not all(isinstance(item.get(key), str) for key in ("event_id", "event_type")):
            return False

    return True
