"""Authentication dependencies and utilities."""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Request, WebSocket, WebSocketException
from pydantic import BaseModel

from .logging_utils import get_logger, log_event, short_ref
from .settings import settings

# Конфигурация
NEXUS_PASSWORD = settings.password
SESSION_SECRET = settings.session_secret or secrets.token_hex(32)
SESSION_EXPIRE_HOURS = settings.session_expire_hours

# In-memory сессии (для продакшена использовать Redis)
active_sessions: dict = {}
logger = get_logger("agent_nexus.auth")


class User(BaseModel):
    """Модель пользователя."""
    username: str = "admin"
    is_authenticated: bool = False
    auth_method: str = "anonymous"
    telegram_id: Optional[str] = None


class SessionData(BaseModel):
    """Данные сессии."""
    session_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    username: str = "admin"
    auth_method: str = "password"
    telegram_id: Optional[str] = None


def _request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _client_ip_from_request(request: Request) -> str:
    client_ip = getattr(request.state, "client_ip", "")
    if client_ip:
        return client_ip
    if request.client:
        return request.client.host
    return "unknown"


def _should_log_auth_failure(path: str) -> bool:
    return path not in {"/api/auth/status", "/api/auth/me"}


def verify_password(password: str) -> bool:
    """Проверка пароля."""
    if not NEXUS_PASSWORD:
        return False
    return secrets.compare_digest(password, NEXUS_PASSWORD)


def create_session(
    ip_address: str = None,
    *,
    username: str = "admin",
    auth_method: str = "password",
    telegram_id: Optional[str] = None,
) -> str:
    """Создать новую сессию."""
    session_id = secrets.token_urlsafe(32)
    now = datetime.now()
    
    active_sessions[session_id] = SessionData(
        session_id=session_id,
        created_at=now,
        expires_at=now + timedelta(hours=SESSION_EXPIRE_HOURS),
        ip_address=ip_address,
        username=username,
        auth_method=auth_method,
        telegram_id=telegram_id,
    )

    log_event(
        logger,
        "info",
        "auth.session.created",
        session_ref=short_ref(session_id),
        username=username,
        auth_method=auth_method,
        telegram_id=telegram_id,
        ip_address=ip_address,
        expires_at=active_sessions[session_id].expires_at.isoformat(),
    )
    
    return session_id


def get_session(session_id: str) -> Optional[SessionData]:
    """Получить сессию по ID."""
    session = active_sessions.get(session_id)
    
    if not session:
        return None
    
    # Проверяем истечение
    if session.expires_at < datetime.now():
        del active_sessions[session_id]
        log_event(
            logger,
            "warning",
            "auth.session.expired",
            session_ref=short_ref(session_id),
            username=session.username,
            auth_method=session.auth_method,
        )
        return None
    
    return session


def delete_session(session_id: str):
    """Удалить сессию."""
    if session_id in active_sessions:
        session = active_sessions[session_id]
        del active_sessions[session_id]
        log_event(
            logger,
            "info",
            "auth.session.deleted",
            session_ref=short_ref(session_id),
            username=session.username,
            auth_method=session.auth_method,
        )


def clean_expired_sessions():
    """Очистить истёкшие сессии."""
    now = datetime.now()
    expired = [
        sid for sid, sess in active_sessions.items()
        if sess.expires_at < now
    ]
    for sid in expired:
        del active_sessions[sid]


async def get_current_user(request: Request) -> User:
    """
    Получить текущего пользователя из сессии.
    
    Проверяет:
    1. Cookie session_id
    2. Валидность сессии
    3. IP адрес (опционально)
    """
    # Получаем session_id из cookie
    session_id = request.cookies.get("session_id")
    
    # Если auth не включён - доступ разрешён
    if not settings.auth_required:
        return User(username="admin", is_authenticated=True, auth_method="none")
    
    if not session_id:
        if _should_log_auth_failure(request.url.path):
            log_event(
                logger,
                "warning",
                "auth.request.missing_session",
                request_id=_request_id_from_request(request),
                path=request.url.path,
                client_ip=_client_ip_from_request(request),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
        )
    
    session = get_session(session_id)
    
    if not session:
        if _should_log_auth_failure(request.url.path):
            log_event(
                logger,
                "warning",
                "auth.request.invalid_session",
                request_id=_request_id_from_request(request),
                path=request.url.path,
                client_ip=_client_ip_from_request(request),
                session_ref=short_ref(session_id),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла или недействительна",
        )

    log_event(
        logger,
        "info",
        "auth.request.authenticated",
        request_id=_request_id_from_request(request),
        path=request.url.path,
        client_ip=_client_ip_from_request(request),
        session_ref=short_ref(session_id),
        username=session.username,
        auth_method=session.auth_method,
    )
    
    return User(
        username=session.username or "admin",
        is_authenticated=True,
        auth_method=session.auth_method,
        telegram_id=session.telegram_id,
    )


async def get_current_websocket_user(websocket: WebSocket) -> User:
    """Authenticate a WebSocket connection using the session cookie."""
    if not settings.auth_required:
        return User(username="admin", is_authenticated=True, auth_method="none")

    session_id = websocket.cookies.get("session_id")
    if not session_id:
        log_event(
            logger,
            "warning",
            "auth.websocket.missing_session",
            path=websocket.url.path,
            client_ip=websocket.client.host if websocket.client else "unknown",
        )
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication required",
        )

    session = get_session(session_id)
    if not session:
        log_event(
            logger,
            "warning",
            "auth.websocket.invalid_session",
            path=websocket.url.path,
            client_ip=websocket.client.host if websocket.client else "unknown",
            session_ref=short_ref(session_id),
        )
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Session expired or invalid",
        )

    log_event(
        logger,
        "info",
        "auth.websocket.authenticated",
        path=websocket.url.path,
        client_ip=websocket.client.host if websocket.client else "unknown",
        session_ref=short_ref(session_id),
        username=session.username,
        auth_method=session.auth_method,
    )

    return User(
        username=session.username or "admin",
        is_authenticated=True,
        auth_method=session.auth_method,
        telegram_id=session.telegram_id,
    )


async def get_current_user_optional(request: Request) -> User:
    """Получить пользователя (опционально, без ошибки)."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return User(username="", is_authenticated=False)


# Зависимости для использования в роутах
RequireAuth = Depends(get_current_user)
OptionalAuth = Depends(get_current_user_optional)
