#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TERMINAL_STATUSES = ("passed", "failed", "blocked")


@dataclass(frozen=True)
class TaskView:
    task_id: str
    title: str
    raw_status: str
    effective_status: str
    reproduce_status: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _tracker_lock_path(path: Path) -> Path:
    suffix = f"{path.suffix}.lock" if path.suffix else ".lock"
    return path.with_suffix(suffix)


@contextmanager
def _locked_tracker_payload(path: Path):
    lock_path = _tracker_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield _load_json(path)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _ssot_task_ids(ssot_payload: dict[str, Any]) -> list[str]:
    tasks = ssot_payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("SSOT payload must contain a tasks list")

    task_ids: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        task_id = item.get("id") or item.get("task_id")
        if isinstance(task_id, str):
            task_ids.append(task_id)
    return task_ids


def _tracker_task_map(tracker_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = tracker_payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("Tracker payload must contain a tasks list")

    mapping: dict[str, dict[str, Any]] = {}
    for item in tasks:
        if not isinstance(item, dict):
            continue
        task_id = item.get("task_id") or item.get("id")
        if isinstance(task_id, str):
            mapping[task_id] = item
    return mapping


def _task_view(task_id: str, tracker_task: dict[str, Any]) -> TaskView:
    return TaskView(
        task_id=task_id,
        title=str(tracker_task.get("title") or ""),
        raw_status=str(tracker_task.get("raw_status") or ""),
        effective_status=str(tracker_task.get("effective_status") or ""),
        reproduce_status=str(tracker_task.get("reproduce_sweep_status") or "pending"),
    )


def _is_terminal_reproduce_status(
    reproduce_status: str,
    terminal_statuses: tuple[str, ...],
) -> bool:
    return reproduce_status in terminal_statuses


def _is_pending_reproduce_task(
    task: TaskView,
    terminal_statuses: tuple[str, ...],
) -> bool:
    return not _is_terminal_reproduce_status(task.reproduce_status, terminal_statuses)


def _ordered_tracker_tasks(
    ssot_payload: dict[str, Any],
    tracker_payload: dict[str, Any],
) -> list[TaskView]:
    task_ids = _ssot_task_ids(ssot_payload)
    tracker_map = _tracker_task_map(tracker_payload)
    ordered: list[TaskView] = []
    for task_id in task_ids:
        tracker_task = tracker_map.get(task_id)
        if tracker_task is None:
            continue
        ordered.append(_task_view(task_id, tracker_task))
    return ordered


def _next_tasks(
    ordered_tasks: list[TaskView],
    terminal_statuses: tuple[str, ...],
) -> tuple[str | None, str | None]:
    current_validation: str | None = None
    next_staged: str | None = None
    eligible_tasks = [task for task in ordered_tasks if task.effective_status == "done"]

    for index, task in enumerate(eligible_tasks):
        if task.reproduce_status == "in_progress":
            current_validation = task.task_id
            for later in eligible_tasks[index + 1 :]:
                if _is_pending_reproduce_task(later, terminal_statuses) and later.reproduce_status != "in_progress":
                    next_staged = later.task_id
                    break
            break

    if current_validation is None:
        for task in eligible_tasks:
            if _is_pending_reproduce_task(task, terminal_statuses):
                current_validation = task.task_id
                break

        if current_validation is not None:
            seen_current = False
            for task in eligible_tasks:
                if task.task_id == current_validation:
                    seen_current = True
                    continue
                if seen_current and _is_pending_reproduce_task(task, terminal_statuses):
                    next_staged = task.task_id
                    break

    return current_validation, next_staged


def _non_terminal_tasks(
    ordered_tasks: list[TaskView],
    terminal_statuses: tuple[str, ...],
) -> list[TaskView]:
    return [
        task
        for task in ordered_tasks
        if task.effective_status == "done" and _is_pending_reproduce_task(task, terminal_statuses)
    ]


def _task_window(
    ordered_tasks: list[TaskView],
    terminal_statuses: tuple[str, ...],
    *,
    depth: int,
) -> dict[str, Any]:
    non_terminal = _non_terminal_tasks(ordered_tasks, terminal_statuses)
    active = [task for task in non_terminal if task.reproduce_status == "in_progress"]
    pending = [task for task in non_terminal if task.reproduce_status != "in_progress"]

    return {
        "active_task_ids": [task.task_id for task in active],
        "active_count": len(active),
        "pending_task_ids": [task.task_id for task in pending[:depth]],
        "pending_preview_count": min(len(pending), depth),
        "combined_window_task_ids": [
            task.task_id for task in (active + pending[:depth])
        ],
    }


def _counts(ordered_tasks: list[TaskView]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in ordered_tasks:
        counts[task.reproduce_status] = counts.get(task.reproduce_status, 0) + 1
    return counts


def _count_effective_done_tasks(ordered_tasks: list[TaskView]) -> int:
    return sum(1 for task in ordered_tasks if task.effective_status == "done")


def _count_effective_done_terminal_tasks(
    ordered_tasks: list[TaskView],
    terminal_statuses: tuple[str, ...],
) -> int:
    return sum(
        1
        for task in ordered_tasks
        if task.effective_status == "done" and task.reproduce_status in terminal_statuses
    )


def _progress_percent(completed: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round((completed / total) * 100, 1)


def _progress_bar(completed: int, total: int, *, width: int = 20) -> str:
    if total <= 0:
        return "[" + ("#" * width) + "]"
    filled = min(width, int((completed / total) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _apply_queue_control(
    *,
    ssot_payload: dict[str, Any],
    tracker_payload: dict[str, Any],
) -> dict[str, Any]:
    ordered_tasks = _ordered_tracker_tasks(ssot_payload, tracker_payload)
    current_validation, next_staged = _next_tasks(
        ordered_tasks,
        DEFAULT_TERMINAL_STATUSES,
    )

    queue_control = tracker_payload.setdefault("queue_control", {})
    queue_control["continue_non_stop"] = True
    queue_control["scan_next_task_before_current_finishes"] = True
    queue_control["next_task_source"] = "source_ssot.tasks"
    queue_control["lookahead_depth"] = 2
    window = _task_window(
        ordered_tasks,
        DEFAULT_TERMINAL_STATUSES,
        depth=max(int(queue_control["lookahead_depth"]), 2),
    )
    queue_control["terminal_reproduce_statuses"] = list(DEFAULT_TERMINAL_STATUSES)
    queue_control["current_validation_task"] = current_validation
    queue_control["next_staged_task"] = next_staged
    queue_control["active_task_ids"] = window["active_task_ids"]
    queue_control["pending_preview_task_ids"] = window["pending_task_ids"]
    queue_control["combined_window_task_ids"] = window["combined_window_task_ids"]
    queue_control["last_scan_at"] = _utc_now()
    queue_control["pending_reproduce_count"] = sum(
        1 for task in ordered_tasks if _is_pending_reproduce_task(task, DEFAULT_TERMINAL_STATUSES)
    )
    queue_control["reproduce_status_counts"] = _counts(ordered_tasks)
    total_task_count = len(ordered_tasks)
    effective_done_task_count = _count_effective_done_tasks(ordered_tasks)
    effective_done_reproduced_count = _count_effective_done_terminal_tasks(
        ordered_tasks,
        DEFAULT_TERMINAL_STATUSES,
    )
    blocked_not_done_count = queue_control["reproduce_status_counts"].get("blocked_not_done", 0)
    overall_accounted_count = effective_done_reproduced_count + blocked_not_done_count
    queue_control["total_task_count"] = total_task_count
    queue_control["effective_done_task_count"] = effective_done_task_count
    queue_control["effective_done_reproduced_count"] = effective_done_reproduced_count
    queue_control["blocked_not_done_count"] = blocked_not_done_count
    queue_control["overall_accounted_count"] = overall_accounted_count
    queue_control["effective_done_progress_percent"] = _progress_percent(
        effective_done_reproduced_count,
        effective_done_task_count,
    )
    queue_control["overall_accounted_progress_percent"] = _progress_percent(
        overall_accounted_count,
        total_task_count,
    )
    queue_control["effective_done_progress_bar"] = _progress_bar(
        effective_done_reproduced_count,
        effective_done_task_count,
    )
    queue_control["overall_accounted_progress_bar"] = _progress_bar(
        overall_accounted_count,
        total_task_count,
    )
    queue_control["progress_summary"] = (
        f"done-reproduced {effective_done_reproduced_count}/{effective_done_task_count} "
        f"{queue_control['effective_done_progress_bar']} "
        f"({queue_control['effective_done_progress_percent']}%), "
        f"overall-accounted {overall_accounted_count}/{total_task_count} "
        f"{queue_control['overall_accounted_progress_bar']} "
        f"({queue_control['overall_accounted_progress_percent']}%)"
    )
    queue_control["should_continue"] = queue_control["pending_reproduce_count"] > 0
    queue_control["final_reply_allowed"] = queue_control["pending_reproduce_count"] == 0
    queue_control["must_keep_running_reason"] = (
        "Non-terminal SSOT reproduce tasks still exist."
        if queue_control["should_continue"]
        else "Every in-scope SSOT reproduce task is terminal."
    )
    queue_control["stage_gap_detected"] = (
        queue_control["should_continue"]
        and len(queue_control["pending_preview_task_ids"]) == 0
    )
    queue_control["pre_reply_guard"] = (
        "Before any user-facing closeout, rescan the queue. "
        "If final_reply_allowed is false, stage the next task and continue."
    )
    queue_control["stop_condition"] = (
        "Only stop when every in-scope SSOT task has a terminal reproduce status "
        "and browser-required tasks also have Playwright/browser evidence."
    )

    return {
        "tracker": str(Path(tracker_payload.get("source_ssot") or "")),
        "current_validation_task": current_validation,
        "next_staged_task": next_staged,
        "active_task_ids": queue_control["active_task_ids"],
        "pending_preview_task_ids": queue_control["pending_preview_task_ids"],
        "final_reply_allowed": queue_control["final_reply_allowed"],
        "pending_reproduce_count": queue_control["pending_reproduce_count"],
        "reproduce_status_counts": queue_control["reproduce_status_counts"],
        "total_task_count": queue_control["total_task_count"],
        "effective_done_task_count": queue_control["effective_done_task_count"],
        "effective_done_reproduced_count": queue_control["effective_done_reproduced_count"],
        "blocked_not_done_count": queue_control["blocked_not_done_count"],
        "progress_summary": queue_control["progress_summary"],
    }


def scan_queue(
    *,
    ssot_path: Path,
    tracker_path: Path,
    write: bool,
) -> dict[str, Any]:
    ssot_payload = _load_json(ssot_path)
    if write:
        with _locked_tracker_payload(tracker_path) as tracker_payload:
            result = _apply_queue_control(ssot_payload=ssot_payload, tracker_payload=tracker_payload)
            _write_json(tracker_path, tracker_payload)
    else:
        tracker_payload = _load_json(tracker_path)
        result = _apply_queue_control(ssot_payload=ssot_payload, tracker_payload=tracker_payload)

    result["tracker"] = str(tracker_path)
    result["ssot"] = str(ssot_path)
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def _tracker_task_or_error(
    tracker_payload: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    tracker_map = _tracker_task_map(tracker_payload)
    task = tracker_map.get(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found in tracker")
    return task


def _task_reproduce_artifacts(task: dict[str, Any]) -> dict[str, Any]:
    return task.setdefault("reproduce_skill_artifacts", {})


def start_task(
    *,
    tracker_path: Path,
    task_id: str,
    tracker_note: str,
) -> dict[str, Any]:
    with _locked_tracker_payload(tracker_path) as tracker_payload:
        task = _tracker_task_or_error(tracker_payload, task_id)

        task["reproduce_sweep_status"] = "in_progress"
        task["reproduce_skill_run"] = True
        task["reproduce_skill_started_at"] = task.get("reproduce_skill_started_at") or _utc_now()
        task["reproduce_skill_completed_at"] = None
        artifacts = _task_reproduce_artifacts(task)
        artifacts["tracker_note"] = tracker_note

        _write_json(tracker_path, tracker_payload)
        return {
            "tracker": str(tracker_path),
            "task_id": task_id,
            "reproduce_sweep_status": task["reproduce_sweep_status"],
            "reproduce_skill_started_at": task["reproduce_skill_started_at"],
        }


def finish_task(
    *,
    tracker_path: Path,
    task_id: str,
    final_status: str,
    reproduce_map: str,
    reproduce_report: str,
    reproduce_map_ru_simplified: str | None,
    note: str | None,
) -> dict[str, Any]:
    with _locked_tracker_payload(tracker_path) as tracker_payload:
        task = _tracker_task_or_error(tracker_payload, task_id)

        task["reproduce_sweep_status"] = "passed"
        task["reproduce_skill_run"] = True
        task["reproduce_skill_started_at"] = task.get("reproduce_skill_started_at") or _utc_now()
        task["reproduce_skill_completed_at"] = _utc_now()
        artifacts = _task_reproduce_artifacts(task)
        artifacts["reproduce_map"] = reproduce_map
        if reproduce_map_ru_simplified:
            artifacts["reproduce_map_ru_simplified"] = reproduce_map_ru_simplified
        artifacts["reproduce_report"] = reproduce_report
        artifacts["final_status"] = final_status
        if note:
            artifacts["note"] = note
        elif "note" in artifacts:
            del artifacts["note"]

        _write_json(tracker_path, tracker_payload)
        return {
            "tracker": str(tracker_path),
            "task_id": task_id,
            "reproduce_sweep_status": task["reproduce_sweep_status"],
            "reproduce_skill_completed_at": task["reproduce_skill_completed_at"],
            "final_status": final_status,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh nonstop reproduce queue control and task states from SSOT/tracker JSON."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Refresh queue_control fields from SSOT order.")
    scan_parser.add_argument(
        "--ssot",
        default="docs/plans/ssot_kanban_20260313_062127.json",
        help="Path to the SSOT kanban JSON.",
    )
    scan_parser.add_argument(
        "--tracker",
        default="/tmp/repro.json",
        help="Path to the reproduce tracker JSON.",
    )
    scan_parser.add_argument(
        "--write",
        action="store_true",
        help="Write refreshed queue_control fields back into the tracker.",
    )

    start_parser = subparsers.add_parser("start", help="Mark one task as an active reproduce run.")
    start_parser.add_argument("--tracker", default="/tmp/repro.json", help="Path to the reproduce tracker JSON.")
    start_parser.add_argument("--task", required=True, help="Task id to mark in progress.")
    start_parser.add_argument(
        "--tracker-note",
        default="Started via reproduce-skill sweep",
        help="Short tracker note stored under reproduce_skill_artifacts.tracker_note.",
    )

    finish_parser = subparsers.add_parser("finish", help="Mark one task as reproduced with evidence.")
    finish_parser.add_argument("--tracker", default="/tmp/repro.json", help="Path to the reproduce tracker JSON.")
    finish_parser.add_argument("--task", required=True, help="Task id to mark passed.")
    finish_parser.add_argument("--final-status", required=True, help="Validator final status text.")
    finish_parser.add_argument("--reproduce-map", required=True, help="Absolute path to reproduce_map.md.")
    finish_parser.add_argument("--reproduce-report", required=True, help="Absolute path to reproduce_report.md.")
    finish_parser.add_argument(
        "--reproduce-map-ru-simplified",
        help="Absolute path to reproduce_map.ru.simplified.md.",
    )
    finish_parser.add_argument("--note", help="Optional validator note stored in tracker artifacts.")

    args = parser.parse_args()

    if args.command == "scan":
        result = scan_queue(
            ssot_path=Path(args.ssot).resolve(),
            tracker_path=Path(args.tracker).resolve(),
            write=args.write,
        )
    elif args.command == "start":
        result = start_task(
            tracker_path=Path(args.tracker).resolve(),
            task_id=args.task,
            tracker_note=args.tracker_note,
        )
    else:
        result = finish_task(
            tracker_path=Path(args.tracker).resolve(),
            task_id=args.task,
            final_status=args.final_status,
            reproduce_map=args.reproduce_map,
            reproduce_report=args.reproduce_report,
            reproduce_map_ru_simplified=args.reproduce_map_ru_simplified,
            note=args.note,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
