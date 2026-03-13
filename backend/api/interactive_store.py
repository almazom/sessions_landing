"""Helpers for building an operational store snapshot for interactive runtime state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


SUPERVISOR_LOCK_STATUS_VALUES = {"claimed", "released", "expired"}


def _require_non_empty_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"operational store requires {label}")
    return value


def build_operational_store_snapshot(
    *,
    route: Dict[str, Any],
    runtime_identity: Dict[str, Any],
    runtime_status: Dict[str, Any],
    supervisor: Dict[str, Any],
    updated_at: str,
) -> Dict[str, Any]:
    route_payload = {
        "harness": _require_non_empty_text(route.get("harness"), label="route harness"),
        "route_id": _require_non_empty_text(
            route.get("id") or route.get("route_id"),
            label="route id",
        ),
    }
    runtime_identity_payload = {
        "thread_id": _require_non_empty_text(
            runtime_identity.get("thread_id"),
            label="runtime identity thread_id",
        ),
        "session_id": _require_non_empty_text(
            runtime_identity.get("session_id"),
            label="runtime identity session_id",
        ),
        "transport": _require_non_empty_text(
            runtime_identity.get("transport"),
            label="runtime identity transport",
        ),
        "source": _require_non_empty_text(
            runtime_identity.get("source"),
            label="runtime identity source",
        ),
    }
    runtime_status_payload = dict(runtime_status)
    if runtime_identity_payload["thread_id"] != runtime_status_payload.get("thread_id"):
        raise ValueError(
            "operational store runtime status must match runtime identity thread_id"
        )
    if runtime_identity_payload["session_id"] != runtime_status_payload.get("session_id"):
        raise ValueError(
            "operational store runtime status must match runtime identity session_id"
        )

    lock_status = _require_non_empty_text(
        supervisor.get("lock_status"),
        label="supervisor lock status",
    )
    if lock_status not in SUPERVISOR_LOCK_STATUS_VALUES:
        raise ValueError(
            "operational store does not support this supervisor lock status"
        )

    supervisor_payload = {
        "owner_id": _require_non_empty_text(
            supervisor.get("owner_id"),
            label="supervisor owner_id",
        ),
        "lease_id": _require_non_empty_text(
            supervisor.get("lease_id"),
            label="supervisor lease_id",
        ),
        "lock_status": lock_status,
        "heartbeat_at": _require_non_empty_text(
            supervisor.get("heartbeat_at"),
            label="supervisor heartbeat_at",
        ),
        "lock_expires_at": _require_non_empty_text(
            supervisor.get("lock_expires_at"),
            label="supervisor lock_expires_at",
        ),
    }

    return {
        "version": 1,
        "updated_at": _require_non_empty_text(updated_at, label="updated_at"),
        "records": [
            {
                "route": route_payload,
                "runtime_identity": runtime_identity_payload,
                "runtime_status": runtime_status_payload,
                "supervisor": supervisor_payload,
            }
        ],
    }


def save_operational_store_snapshot(
    output_path: str | Path,
    snapshot: Dict[str, Any],
) -> Path:
    resolved_path = Path(output_path).expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(snapshot, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved_path


def load_operational_store_snapshot(
    snapshot_path: str | Path,
) -> Dict[str, Any]:
    resolved_path = Path(snapshot_path).expanduser().resolve()
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"operational store snapshot is corrupted: {resolved_path}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError(
            f"operational store snapshot must be an object: {resolved_path}"
        )

    return payload


def prune_operational_store_snapshot(
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    records = snapshot.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("operational store GC requires at least one record")

    kept_records = []
    removed_route_ids = []
    for record in records:
        supervisor = record.get("supervisor") or {}
        lock_status = supervisor.get("lock_status")
        route = record.get("route") or {}
        route_id = route.get("route_id")
        if lock_status in {"expired", "released"}:
            if isinstance(route_id, str) and route_id:
                removed_route_ids.append(route_id)
            continue
        kept_records.append(record)

    return {
        "version": snapshot.get("version", 1),
        "updated_at": snapshot.get("updated_at"),
        "records": kept_records,
        "gc_summary": {
            "removed_route_ids": removed_route_ids,
            "removed_count": len(removed_route_ids),
            "kept_count": len(kept_records),
        },
    }


def acquire_operational_store_lock(
    record: Dict[str, Any],
    *,
    owner_id: str,
    lease_id: str,
    heartbeat_at: str,
    lock_expires_at: str,
) -> Dict[str, Any]:
    supervisor = dict(record.get("supervisor") or {})
    current_owner_id = supervisor.get("owner_id")
    current_lock_status = supervisor.get("lock_status")

    if (
        current_lock_status == "claimed"
        and isinstance(current_owner_id, str)
        and current_owner_id
        and current_owner_id != owner_id
    ):
        raise PermissionError(
            "operational store lock is already claimed by another owner"
        )

    next_record = dict(record)
    next_record["supervisor"] = {
        **supervisor,
        "owner_id": _require_non_empty_text(owner_id, label="lock owner_id"),
        "lease_id": _require_non_empty_text(lease_id, label="lock lease_id"),
        "lock_status": "claimed",
        "heartbeat_at": _require_non_empty_text(
            heartbeat_at,
            label="lock heartbeat_at",
        ),
        "lock_expires_at": _require_non_empty_text(
            lock_expires_at,
            label="lock lock_expires_at",
        ),
    }
    return next_record


def release_operational_store_lock(
    record: Dict[str, Any],
    *,
    owner_id: str,
    released_at: str,
) -> Dict[str, Any]:
    supervisor = dict(record.get("supervisor") or {})
    current_owner_id = supervisor.get("owner_id")
    if current_owner_id != owner_id:
        raise PermissionError(
            "operational store lock may only be released by the owner"
        )

    next_record = dict(record)
    next_record["supervisor"] = {
        **supervisor,
        "lock_status": "released",
        "heartbeat_at": _require_non_empty_text(
            released_at,
            label="release timestamp",
        ),
    }
    return next_record
