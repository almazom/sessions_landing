"""Helpers for building an operational store snapshot for interactive runtime state."""

from __future__ import annotations

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
        raise ValueError("operational store does not support this supervisor lock status")

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
