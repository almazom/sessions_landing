from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .runtime_status_schema import (
    InteractiveRuntimeStatusSchema,
    load_runtime_status_schema,
    validate_runtime_status_payload_against_schema,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OPERATIONAL_STORE_SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "interactive-operational-store.schema.json"
)
OPERATIONAL_STORE_SAMPLE_PATH = (
    REPO_ROOT / "contracts" / "examples" / "interactive-operational-store.sample.json"
)


class InteractiveOperationalStoreSchemaNotFound(FileNotFoundError):
    """Raised when the operational store schema or sample is missing or incomplete."""


@dataclass(frozen=True)
class InteractiveOperationalStoreSchema:
    path: Path
    version: str
    required_top_level_keys: list[str]
    supervisor_lock_status_values: list[str]
    runtime_status_schema: InteractiveRuntimeStatusSchema


def _load_json_object(path: Path, *, label: str) -> Dict[str, Any]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise InteractiveOperationalStoreSchemaNotFound(
            f"{label} is missing: {resolved_path}"
        )

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise InteractiveOperationalStoreSchemaNotFound(
            f"{label} must be an object: {resolved_path}"
        )
    return payload


def load_operational_store_schema(
    schema_path: Path | None = None,
) -> InteractiveOperationalStoreSchema:
    payload = _load_json_object(
        schema_path or OPERATIONAL_STORE_SCHEMA_PATH,
        label="interactive operational store schema",
    )
    try:
        supervisor_values = (
            payload["definitions"]["supervisorOwnership"]["properties"]["lock_status"]["enum"]
        )
    except KeyError as error:
        raise InteractiveOperationalStoreSchemaNotFound(
            "interactive operational store schema is incomplete"
        ) from error

    return InteractiveOperationalStoreSchema(
        path=(schema_path or OPERATIONAL_STORE_SCHEMA_PATH).resolve(),
        version=payload["version"],
        required_top_level_keys=payload["required"],
        supervisor_lock_status_values=supervisor_values,
        runtime_status_schema=load_runtime_status_schema(),
    )


def load_operational_store_sample(sample_path: Path | None = None) -> Dict[str, Any]:
    return _load_json_object(
        sample_path or OPERATIONAL_STORE_SAMPLE_PATH,
        label="interactive operational store sample",
    )


def validate_operational_store_payload_against_schema(
    payload: Dict[str, Any],
    schema: InteractiveOperationalStoreSchema,
) -> bool:
    if sorted(payload.keys()) != sorted(schema.required_top_level_keys):
        return False
    if not isinstance(payload.get("version"), int):
        return False
    if not isinstance(payload.get("updated_at"), str) or not payload["updated_at"]:
        return False

    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return False

    for record in records:
        if not isinstance(record, dict):
            return False
        route = record.get("route")
        runtime_identity = record.get("runtime_identity")
        runtime_status = record.get("runtime_status")
        supervisor = record.get("supervisor")
        if not isinstance(route, dict) or not isinstance(runtime_identity, dict):
            return False
        if not isinstance(runtime_status, dict) or not isinstance(supervisor, dict):
            return False
        if not all(
            isinstance(route.get(key), str) and route.get(key)
            for key in ("harness", "route_id")
        ):
            return False
        if not all(
            isinstance(runtime_identity.get(key), str) and runtime_identity.get(key)
            for key in ("thread_id", "session_id", "transport", "source")
        ):
            return False
        if not validate_runtime_status_payload_against_schema(
            runtime_status,
            schema.runtime_status_schema,
        ):
            return False
        if runtime_identity["thread_id"] != runtime_status["thread_id"]:
            return False
        if runtime_identity["session_id"] != runtime_status["session_id"]:
            return False
        if not all(
            isinstance(supervisor.get(key), str) and supervisor.get(key)
            for key in ("owner_id", "lease_id", "heartbeat_at", "lock_expires_at")
        ):
            return False
        if supervisor.get("lock_status") not in schema.supervisor_lock_status_values:
            return False

    return True
