"""Authentication routes."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..deps import (
    verify_password,
    create_session,
    delete_session,
    get_current_user,
    get_current_user_optional,
    User,
    NEXUS_PASSWORD,
)
from ..logging_utils import get_logger, log_event
from ..settings import settings


router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = get_logger("agent_nexus.auth_routes")

TELEGRAM_OIDC_ISSUER = "https://oauth.telegram.org"
TELEGRAM_AUTH_ENDPOINT = "https://oauth.telegram.org/auth"
TELEGRAM_TOKEN_ENDPOINT = "https://oauth.telegram.org/token"
TELEGRAM_JWKS_URI = "https://oauth.telegram.org/.well-known/jwks.json"
TELEGRAM_STATE_COOKIE = "telegram_oauth_state"
TELEGRAM_VERIFIER_COOKIE = "telegram_oauth_verifier"
TELEGRAM_OAUTH_COOKIE_MAX_AGE = 600


def _request_log_fields(request: Request) -> dict[str, Any]:
    client_ip = getattr(request.state, "client_ip", "")
    if not client_ip and request.client:
        client_ip = request.client.host
    return {
        "request_id": getattr(request.state, "request_id", ""),
        "client_ip": client_ip or "unknown",
        "path": request.url.path,
    }


def _telegram_identity_fields(claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "telegram_user_id": str(claims.get("sub") or claims.get("id") or "") or None,
        "telegram_username": claims.get("preferred_username") or claims.get("username"),
        "telegram_name": claims.get("name") or claims.get("first_name"),
    }


def _request_is_https(request: Request) -> bool:
    """Detect HTTPS correctly when running behind a reverse proxy."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip() == "https"
    return request.url.scheme == "https"


def _request_origin(request: Request) -> str:
    """Build the public request origin respecting reverse-proxy headers."""
    scheme = "https" if _request_is_https(request) else "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _normalize_phone_number(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _cookie_options(request: Request) -> dict:
    return {
        "httponly": True,
        "secure": _request_is_https(request),
        "samesite": "lax",
    }


def _clear_telegram_oauth_cookies(response: Response, request: Request) -> None:
    for name in (TELEGRAM_STATE_COOKIE, TELEGRAM_VERIFIER_COOKIE):
        response.delete_cookie(name, **_cookie_options(request))


def _telegram_login_target(request: Request, error: Optional[str] = None) -> str:
    target = f"{_request_origin(request)}/"
    if error:
        target = f"{target}?{urlencode({'auth_error': error})}"
    return target


def _telegram_callback_url(request: Request) -> str:
    return f"{_request_origin(request)}/api/auth/telegram/callback"


def _telegram_widget_callback_url(request: Request) -> str:
    return f"{_request_origin(request)}/api/auth/telegram/widget/callback"


def _telegram_requests_phone() -> bool:
    return settings.telegram_request_phone or bool(settings.telegram_allowed_phone_numbers)


def _telegram_scopes() -> str:
    scopes = ["openid", "profile"]
    if _telegram_requests_phone():
        scopes.append("phone")
    return " ".join(scopes)


def _telegram_login_available() -> bool:
    return settings.telegram_login_enabled


def _base64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding_length = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding_length))


def _decode_json_segment(value: str) -> Any:
    try:
        return json.loads(_base64url_decode(value).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token payload is invalid",
        ) from exc


async def _fetch_telegram_jwks() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(TELEGRAM_JWKS_URI)
        response.raise_for_status()
        return response.json()


def _ensure_telegram_user_allowed(claims: dict) -> None:
    user_id = str(claims.get("sub") or claims.get("id") or "")
    username = str(claims.get("preferred_username") or claims.get("username") or "").lower().lstrip("@")
    phone_number = _normalize_phone_number(str(claims.get("phone_number", "")))

    if settings.telegram_allowed_user_ids and user_id not in settings.telegram_allowed_user_ids:
        log_event(
            logger,
            "warning",
            "auth.telegram.allowlist.denied",
            reason="user_id_not_allowed",
            telegram_user_id=user_id,
            telegram_username=username or None,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Telegram user is not allowed")

    if settings.telegram_allowed_usernames and username not in settings.telegram_allowed_usernames:
        log_event(
            logger,
            "warning",
            "auth.telegram.allowlist.denied",
            reason="username_not_allowed",
            telegram_user_id=user_id or None,
            telegram_username=username or None,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Telegram username is not allowed")

    if settings.telegram_allowed_phone_numbers and phone_number not in settings.telegram_allowed_phone_numbers:
        log_event(
            logger,
            "warning",
            "auth.telegram.allowlist.denied",
            reason="phone_not_allowed",
            telegram_user_id=user_id or None,
            telegram_username=username or None,
            telegram_phone=phone_number or None,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Telegram phone is not allowed")


def _telegram_public_key_from_jwk(key_data: dict) -> rsa.RSAPublicKey:
    if key_data.get("kty") != "RSA":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram signing key type is unsupported",
        )

    try:
        modulus = int.from_bytes(_base64url_decode(key_data["n"]), "big")
        exponent = int.from_bytes(_base64url_decode(key_data["e"]), "big")
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram signing key is malformed",
        ) from exc

    return rsa.RSAPublicNumbers(exponent, modulus).public_key()


def _validate_telegram_claims(claims: dict) -> None:
    now = int(time.time())
    issuer = claims.get("iss")
    audience = claims.get("aud")

    if issuer != TELEGRAM_OIDC_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token issuer is invalid",
        )

    valid_audience = False
    if isinstance(audience, list):
        valid_audience = settings.telegram_client_id in [str(item) for item in audience]
    else:
        valid_audience = str(audience) == settings.telegram_client_id

    if not valid_audience:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token audience is invalid",
        )

    try:
        expires_at = int(claims.get("exp", 0))
        issued_at = int(claims.get("iat", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token timestamps are invalid",
        ) from exc

    if expires_at <= now - 30:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token has expired",
        )

    if issued_at > now + 300:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token issue time is invalid",
        )

    if not str(claims.get("sub", "")).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token subject is missing",
        )


async def _decode_telegram_id_token(id_token: str) -> dict:
    token_segments = id_token.split(".")
    if len(token_segments) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token is malformed",
        )

    encoded_header, encoded_payload, encoded_signature = token_segments
    header = _decode_json_segment(encoded_header)
    claims = _decode_json_segment(encoded_payload)

    if header.get("alg") != "RS256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token algorithm is unsupported",
        )

    jwks = await _fetch_telegram_jwks()
    kid = header.get("kid")
    key_data = next((entry for entry in jwks.get("keys", []) if entry.get("kid") == kid), None)

    if key_data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram signing key was not found")

    public_key = _telegram_public_key_from_jwk(key_data)

    try:
        signature = _base64url_decode(encoded_signature)
        public_key.verify(
            signature,
            f"{encoded_header}.{encoded_payload}".encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram token signature is invalid",
        ) from exc

    _validate_telegram_claims(claims)
    return claims


def _telegram_widget_secret_key() -> bytes:
    return hashlib.sha256(settings.telegram_bot_token.encode("utf-8")).digest()


def _verify_telegram_widget_auth(auth_data: dict) -> dict:
    if not settings.telegram_widget_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram widget login is not configured",
        )

    received_hash = str(auth_data.get("hash", "")).strip().lower()
    if not received_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram widget hash is missing",
        )

    normalized_data = {
        key: value
        for key, value in auth_data.items()
        if key != "hash" and value not in (None, "")
    }
    data_check_string = "\n".join(
        f"{key}={normalized_data[key]}"
        for key in sorted(normalized_data)
    )
    expected_hash = hmac.new(
        _telegram_widget_secret_key(),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram widget hash is invalid",
        )

    try:
        auth_date = int(auth_data.get("auth_date", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram widget auth date is invalid",
        ) from exc

    now = int(time.time())
    if auth_date < now - settings.telegram_auth_max_age_seconds or auth_date > now + 300:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram widget auth data has expired",
        )

    if not str(auth_data.get("id", "")).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram widget user id is missing",
        )

    return auth_data


def _set_session_cookie(response: Response, request: Request, session_id: str) -> None:
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=_request_is_https(request),
        samesite="strict",
        max_age=settings.auth_cookie_max_age_seconds,
    )


class LoginRequest(BaseModel):
    """Запрос на вход."""
    password: str


class LoginResponse(BaseModel):
    """Ответ на вход."""
    success: bool
    message: str
    expires_at: Optional[str] = None


class TelegramLoginRequest(BaseModel):
    """Telegram ID token returned by the official Telegram login SDK."""
    id_token: str


class TelegramWidgetAuthPayload(BaseModel):
    """Auth payload returned by the official Telegram Login Widget."""
    id: int
    first_name: str
    auth_date: int
    hash: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None


class UserResponse(BaseModel):
    """Информация о пользователе."""
    username: str
    is_authenticated: bool
    password_required: bool
    auth_required: bool
    password_enabled: bool
    telegram_enabled: bool
    telegram_configured: bool
    telegram_mode: Optional[str] = None
    telegram_client_id: Optional[str] = None
    telegram_bot_username: Optional[str] = None
    telegram_widget_auth_url: Optional[str] = None
    telegram_request_phone: bool = False
    auth_method: str = "anonymous"


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
):
    """
    🔐 Вход в систему
    
    Устанавливает httpOnly cookie с session_id
    """
    if not NEXUS_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password login is not configured",
        )

    if not verify_password(request.password):
        log_event(
            logger,
            "warning",
            "auth.password.login_failed",
            **_request_log_fields(http_request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль",
        )
    
    # Создаём сессию
    client_ip = http_request.client.host if http_request.client else None
    session_id = create_session(ip_address=client_ip, auth_method="password")
    
    # Устанавливаем cookie
    _set_session_cookie(response, http_request, session_id)

    log_event(
        logger,
        "info",
        "auth.password.login_succeeded",
        **_request_log_fields(http_request),
    )
    
    return LoginResponse(
        success=True,
        message="Успешный вход",
        expires_at=datetime.now().isoformat(),  # Упрощённо
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    """
    🚪 Выход из системы
    
    Удаляет сессию и очищает cookie
    """
    session_id = request.cookies.get("session_id")
    
    if session_id:
        delete_session(session_id)
    
    response.delete_cookie(
        "session_id",
        samesite="strict",
        secure=_request_is_https(request),
    )

    log_event(
        logger,
        "info",
        "auth.logout.completed",
        **_request_log_fields(request),
        username=user.username,
        auth_method=user.auth_method,
    )
    
    return {"success": True, "message": "Успешный выход"}


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request, user: User = Depends(get_current_user_optional)):
    """
    👤 Информация о текущем пользователе
    
    Возвращает статус авторизации
    """
    return UserResponse(
        username=user.username if user.is_authenticated else "",
        is_authenticated=user.is_authenticated,
        password_required=bool(NEXUS_PASSWORD),
        auth_required=settings.auth_required,
        password_enabled=bool(NEXUS_PASSWORD),
        telegram_enabled=_telegram_login_available(),
        telegram_configured=settings.telegram_login_configured,
        telegram_mode=settings.telegram_auth_mode or None,
        telegram_client_id=settings.telegram_client_id or None,
        telegram_bot_username=settings.telegram_bot_username or None,
        telegram_widget_auth_url=_telegram_widget_callback_url(request) if settings.telegram_widget_configured else None,
        telegram_request_phone=_telegram_requests_phone(),
        auth_method=user.auth_method,
    )


@router.get("/status")
async def auth_status(request: Request, user: User = Depends(get_current_user_optional)):
    """
    🔍 Статус авторизации (упрощённый)
    
    Полезно для проверки фронтом
    """
    return {
        "authenticated": user.is_authenticated,
        "password_required": bool(NEXUS_PASSWORD),
        "auth_required": settings.auth_required,
        "password_enabled": bool(NEXUS_PASSWORD),
        "telegram_enabled": _telegram_login_available(),
        "telegram_configured": settings.telegram_login_configured,
        "telegram_mode": settings.telegram_auth_mode or None,
        "telegram_client_id": settings.telegram_client_id or None,
        "telegram_bot_username": settings.telegram_bot_username or None,
        "telegram_widget_auth_url": _telegram_widget_callback_url(request) if settings.telegram_widget_configured else None,
        "telegram_request_phone": _telegram_requests_phone(),
        "auth_method": user.auth_method,
    }


@router.post("/telegram/login", response_model=LoginResponse)
async def telegram_login(
    request: TelegramLoginRequest,
    http_request: Request,
    response: Response,
):
    """Complete Telegram login from the official Telegram JS callback."""
    if not settings.telegram_oidc_configured or not settings.telegram_allowlist_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram OIDC login is not configured",
        )

    try:
        claims = await _decode_telegram_id_token(request.id_token)
        _ensure_telegram_user_allowed(claims)
    except HTTPException as exc:
        log_event(
            logger,
            "warning",
            "auth.telegram.oidc_login_failed",
            **_request_log_fields(http_request),
            status_code=exc.status_code,
            reason=exc.detail,
        )
        raise

    client_ip = http_request.client.host if http_request.client else None
    username = claims.get("preferred_username") or claims.get("name") or "telegram"
    session_id = create_session(
        ip_address=client_ip,
        username=username,
        auth_method="telegram",
        telegram_id=str(claims.get("sub", "")) or None,
    )

    _set_session_cookie(response, http_request, session_id)
    log_event(
        logger,
        "info",
        "auth.telegram.oidc_login_succeeded",
        **_request_log_fields(http_request),
        **_telegram_identity_fields(claims),
    )
    return LoginResponse(
        success=True,
        message="Успешный вход через Telegram",
        expires_at=datetime.now().isoformat(),
    )


@router.get("/telegram/widget/callback")
async def telegram_widget_callback(
    request: Request,
    id: int,
    first_name: str,
    auth_date: int,
    hash: str,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    photo_url: Optional[str] = None,
):
    """Finish Telegram Login Widget flow and mint the local auth session."""
    try:
        auth_data = _verify_telegram_widget_auth(
            TelegramWidgetAuthPayload(
                id=id,
                first_name=first_name,
                auth_date=auth_date,
                hash=hash,
                last_name=last_name,
                username=username,
                photo_url=photo_url,
            ).model_dump(exclude_none=True)
        )
        _ensure_telegram_user_allowed(auth_data)
    except HTTPException as exc:
        log_event(
            logger,
            "warning",
            "auth.telegram.widget_login_failed",
            **_request_log_fields(request),
            status_code=exc.status_code,
            reason=exc.detail,
            telegram_user_id=id,
            telegram_username=username,
        )
        error_code = "telegram_access_denied" if exc.status_code == status.HTTP_403_FORBIDDEN else "telegram_login_failed"
        return RedirectResponse(
            _telegram_login_target(request, error_code),
            status_code=status.HTTP_302_FOUND,
        )

    client_ip = request.client.host if request.client else None
    username = auth_data.get("username") or auth_data.get("first_name") or "telegram"
    session_id = create_session(
        ip_address=client_ip,
        username=username,
        auth_method="telegram",
        telegram_id=str(auth_data.get("id", "")) or None,
    )

    response = RedirectResponse(_telegram_login_target(request), status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, request, session_id)
    log_event(
        logger,
        "info",
        "auth.telegram.widget_login_succeeded",
        **_request_log_fields(request),
        telegram_user_id=auth_data.get("id"),
        telegram_username=auth_data.get("username"),
        telegram_name=auth_data.get("first_name"),
    )
    return response


@router.get("/telegram/start")
async def telegram_start(request: Request):
    """Start Telegram OIDC login flow."""
    if not settings.telegram_oidc_configured or not settings.telegram_allowlist_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram OIDC login is not configured",
        )

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    callback_url = _telegram_callback_url(request)

    query = urlencode({
        "client_id": settings.telegram_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": _telegram_scopes(),
        "state": state,
        "code_challenge": _base64url_sha256(code_verifier),
        "code_challenge_method": "S256",
    })

    response = RedirectResponse(f"{TELEGRAM_AUTH_ENDPOINT}?{query}", status_code=status.HTTP_302_FOUND)
    cookie_options = _cookie_options(request)
    response.set_cookie(
        TELEGRAM_STATE_COOKIE,
        state,
        max_age=TELEGRAM_OAUTH_COOKIE_MAX_AGE,
        **cookie_options,
    )
    response.set_cookie(
        TELEGRAM_VERIFIER_COOKIE,
        code_verifier,
        max_age=TELEGRAM_OAUTH_COOKIE_MAX_AGE,
        **cookie_options,
    )
    log_event(
        logger,
        "info",
        "auth.telegram.oidc_start",
        **_request_log_fields(request),
        callback_url=callback_url,
        scopes=_telegram_scopes(),
    )
    return response


@router.get("/telegram/callback", name="telegram_callback")
async def telegram_callback(
    request: Request,
    state: Optional[str] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    """Finish Telegram OIDC login flow and mint the local auth session."""
    redirect_target = _telegram_login_target(request)

    if error:
        log_event(
            logger,
            "warning",
            "auth.telegram.oidc_callback_failed",
            **_request_log_fields(request),
            reason=error,
        )
        response = RedirectResponse(
            _telegram_login_target(request, f"telegram_{error}"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_telegram_oauth_cookies(response, request)
        return response

    cookie_state = request.cookies.get(TELEGRAM_STATE_COOKIE)
    code_verifier = request.cookies.get(TELEGRAM_VERIFIER_COOKIE)

    if not state or not code or not cookie_state or not code_verifier or state != cookie_state:
        log_event(
            logger,
            "warning",
            "auth.telegram.oidc_callback_failed",
            **_request_log_fields(request),
            reason="state_mismatch",
        )
        response = RedirectResponse(
            _telegram_login_target(request, "telegram_state_mismatch"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_telegram_oauth_cookies(response, request)
        return response

    callback_url = _telegram_callback_url(request)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                TELEGRAM_TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": callback_url,
                    "client_id": settings.telegram_client_id,
                    "code_verifier": code_verifier,
                },
                auth=(settings.telegram_client_id, settings.telegram_client_secret),
            )
            token_response.raise_for_status()
            token_payload = token_response.json()

        claims = await _decode_telegram_id_token(token_payload["id_token"])
        _ensure_telegram_user_allowed(claims)
    except HTTPException as exc:
        log_event(
            logger,
            "warning",
            "auth.telegram.oidc_callback_failed",
            **_request_log_fields(request),
            status_code=exc.status_code,
            reason=exc.detail,
        )
        error_code = "telegram_access_denied" if exc.status_code == status.HTTP_403_FORBIDDEN else "telegram_login_failed"
        response = RedirectResponse(
            _telegram_login_target(request, error_code),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_telegram_oauth_cookies(response, request)
        return response
    except Exception as exc:
        log_event(
            logger,
            "error",
            "auth.telegram.oidc_callback_failed",
            **_request_log_fields(request),
            reason="unexpected_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        response = RedirectResponse(
            _telegram_login_target(request, "telegram_login_failed"),
            status_code=status.HTTP_302_FOUND,
        )
        _clear_telegram_oauth_cookies(response, request)
        return response

    client_ip = request.client.host if request.client else None
    username = claims.get("preferred_username") or claims.get("name") or "telegram"
    session_id = create_session(
        ip_address=client_ip,
        username=username,
        auth_method="telegram",
        telegram_id=str(claims.get("sub", "")) or None,
    )

    response = RedirectResponse(redirect_target, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, request, session_id)
    _clear_telegram_oauth_cookies(response, request)
    log_event(
        logger,
        "info",
        "auth.telegram.oidc_callback_succeeded",
        **_request_log_fields(request),
        **_telegram_identity_fields(claims),
    )
    return response
