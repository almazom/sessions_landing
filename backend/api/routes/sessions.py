"""Session API routes."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.logging_utils import get_logger, log_event
from backend.api.scanner import session_store, session_scanner
from ..deps import get_current_user
from ..settings import settings

logger = get_logger("agent_nexus.sessions")
REPO_ROOT = Path(__file__).resolve().parents[3]
NX_COLLECT_PATH = REPO_ROOT / "tools" / "nx-collect" / "nx-collect"
NX_COLLECT_TIMEOUT_SECONDS = 40

router = APIRouter(
    prefix="/api",
    tags=["Sessions"],
    dependencies=[Depends(get_current_user)],
)


def _session_changed_timestamp(session: dict) -> str:
    """Use the most recent known session timestamp for sorting/filtering."""
    return session.get("timestamp_end") or session.get("timestamp_start", "")


def _validate_latest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = {"meta", "query", "latest", "errors"}
    missing = required.difference(payload.keys())
    if missing:
        raise ValueError(f"latest payload missing keys: {', '.join(sorted(missing))}")
    if not isinstance(payload["errors"], list):
        raise ValueError("latest payload errors must be a list")
    return payload


def _format_cli_error(detail: str) -> str:
    normalized = " ".join(detail.split())
    return normalized[:400] if len(normalized) > 400 else normalized


def _run_latest_cli(request: Request) -> Dict[str, Any]:
    request_id = getattr(request.state, "request_id", "")

    if not NX_COLLECT_PATH.exists():
        log_event(
            logger,
            "error",
            "sessions.latest.cli_missing",
            request_id=request_id,
            cli_path=str(NX_COLLECT_PATH),
        )
        raise HTTPException(status_code=500, detail="Latest session CLI is not available.")

    command = [str(NX_COLLECT_PATH), "--latest"]
    log_event(
        logger,
        "info",
        "sessions.latest.cli_started",
        request_id=request_id,
        command=command,
        timeout_seconds=NX_COLLECT_TIMEOUT_SECONDS,
    )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=NX_COLLECT_TIMEOUT_SECONDS,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        log_event(
            logger,
            "error",
            "sessions.latest.cli_timeout",
            request_id=request_id,
            timeout_seconds=NX_COLLECT_TIMEOUT_SECONDS,
        )
        raise HTTPException(status_code=504, detail="Latest session lookup timed out.") from exc
    except OSError as exc:
        log_event(
            logger,
            "error",
            "sessions.latest.cli_failed_to_start",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to start latest session CLI.") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if stderr:
        log_event(
            logger,
            "warning" if completed.returncode == 0 else "error",
            "sessions.latest.cli_stderr",
            request_id=request_id,
            return_code=completed.returncode,
            stderr=_format_cli_error(stderr),
        )

    payload: Optional[Dict[str, Any]] = None
    if stdout:
        try:
            payload = _validate_latest_payload(json.loads(stdout))
        except (json.JSONDecodeError, ValueError) as exc:
            log_event(
                logger,
                "error",
                "sessions.latest.cli_invalid_json",
                request_id=request_id,
                return_code=completed.returncode,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise HTTPException(status_code=502, detail="Latest session CLI returned invalid JSON.") from exc

    if completed.returncode == 0 and payload is not None:
        log_event(
            logger,
            "info",
            "sessions.latest.cli_completed",
            request_id=request_id,
            provider=(payload.get("latest") or {}).get("provider"),
            has_latest=bool(payload.get("latest")),
        )
        return payload

    if completed.returncode == 3 and payload is not None and payload.get("latest") is None:
        log_event(
            logger,
            "info",
            "sessions.latest.cli_empty",
            request_id=request_id,
            errors=payload.get("errors"),
        )
        return payload

    error_detail = stderr or "Latest session CLI failed."
    raise HTTPException(status_code=502, detail=_format_cli_error(error_detail))


@router.get("/sessions")
async def list_sessions(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: active, completed, error"),
    agent: Optional[str] = Query(None, description="Filter by agent type"),
    changed_date: Optional[str] = Query(None, description="Filter by changed date YYYY-MM-DD"),
    limit: int = Query(settings.default_session_limit, ge=1, le=settings.max_session_limit),
    offset: int = Query(0, ge=0),
):
    """
    📋 Получить список всех сессий
    
    - **status**: Фильтр по статусу (active, completed, error, paused)
    - **agent**: Фильтр по типу агента (codex, kimi, gemini, qwen, claude, pi)
    - **limit**: Максимальное количество результатов
    - **offset**: Смещение для пагинации
    """
    # Сканируем сессии если магазин пуст
    if session_store.count() == 0 and not session_scanner.has_loaded_once:
        log_event(
            logger,
            "info",
            "sessions.autoscan.triggered",
            request_id=getattr(request.state, "request_id", ""),
            reason="empty_store",
        )
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    sessions = session_store.get_all()
    
    # Фильтрация
    if status:
        sessions = [s for s in sessions if s.get("status") == status]
    
    if agent:
        sessions = [s for s in sessions if s.get("agent_type") == agent]

    if changed_date:
        sessions = [
            s for s in sessions
            if _session_changed_timestamp(s)[:10] == changed_date
        ]
    
    # Сортировка по последнему изменению (новые первыми)
    sessions.sort(key=_session_changed_timestamp, reverse=True)
    
    # Пагинация
    total = len(sessions)
    sessions = sessions[offset:offset + limit]

    log_event(
        logger,
        "info",
        "sessions.list.completed",
        request_id=getattr(request.state, "request_id", ""),
        status_filter=status,
        agent_filter=agent,
        changed_date=changed_date,
        total=total,
        returned=len(sessions),
        limit=limit,
        offset=offset,
    )
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sessions": sessions,
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """
    🔍 Получить детали сессии по ID
    
    - **session_id**: UUID сессии
    """
    # Сканируем если пусто
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    session = session_store.get(session_id)
    
    if not session:
        log_event(
            logger,
            "warning",
            "sessions.detail.not_found",
            request_id=getattr(request.state, "request_id", ""),
            session_id=session_id,
        )
        raise HTTPException(status_code=404, detail=f"Сессия {session_id} не найдена")

    log_event(
        logger,
        "info",
        "sessions.detail.completed",
        request_id=getattr(request.state, "request_id", ""),
        session_id=session_id,
        session_status=session.get("status"),
        agent_type=session.get("agent_type"),
    )
    
    return session


@router.get("/latest-session")
async def get_latest_session(request: Request):
    """Return one global latest session from the nx-collect CLI."""
    return _run_latest_cli(request)


@router.get("/metrics")
async def get_metrics(request: Request):
    """
    📊 Агрегированные метрики по всем сессиям
    
    Возвращает:
    - Общее количество сессий
    - Распределение по агентам
    - Распределение по статусам
    - Общее количество токенов
    """
    # Сканируем если пусто
    if session_store.count() == 0:
        session_scanner.ensure_loaded()
    
    metrics = session_store.metrics()

    log_event(
        logger,
        "info",
        "sessions.metrics.completed",
        request_id=getattr(request.state, "request_id", ""),
        total_sessions=metrics.get("total_sessions"),
        total_tokens=metrics.get("total_tokens"),
    )
    
    return {
        "success": True,
        "data": metrics,
    }


@router.post("/sessions/scan")
async def rescan_sessions(request: Request):
    """
    🔄 Принудительное пересканирование всех директорий агентов
    
    Полезно когда появились новые сессии
    """
    log_event(
        logger,
        "info",
        "sessions.rescan.started",
        request_id=getattr(request.state, "request_id", ""),
    )
    
    # Очищаем старые данные
    session_store.sessions.clear()
    
    # Сканируем заново
    count = session_scanner.scan_all()
    errors = session_scanner.get_errors()

    log_event(
        logger,
        "info",
        "sessions.rescan.completed",
        request_id=getattr(request.state, "request_id", ""),
        sessions_found=count,
        errors=errors if errors else None,
    )
    
    return {
        "success": True,
        "sessions_found": count,
        "errors": errors if errors else None,
        "scanned_at": datetime.now().isoformat(),
    }


@router.get("/agents")
async def list_agents(request: Request):
    """
    🤖 Получить список поддерживаемых агентов и их статусов
    """
    from ...parsers import PARSER_REGISTRY
    from ..scanner import SessionScanner
    
    agents = []
    
    for agent_type in PARSER_REGISTRY.keys():
        watch_path = Path(SessionScanner.WATCH_PATHS.get(agent_type, "")).expanduser()
        
        agents.append({
            "type": agent_type,
            "watch_path": str(watch_path),
            "path_exists": watch_path.exists(),
            "session_count": len([
                s for s in session_store.get_all() 
                if s.get("agent_type") == agent_type
            ]),
        })
    
    response = {
        "total": len(agents),
        "agents": agents,
    }

    log_event(
        logger,
        "info",
        "sessions.agents.completed",
        request_id=getattr(request.state, "request_id", ""),
        total=response["total"],
    )

    return response
