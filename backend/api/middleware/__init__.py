"""Security middleware - IP whitelist, rate limiting, request tracing."""

import secrets
import time
from collections import defaultdict

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.logging_utils import get_logger, log_event, sanitize_fields
from backend.api.settings import settings


logger = get_logger("agent_nexus.http")


class RateLimiter:
    """Простой rate limiter на основе IP."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = defaultdict(list)  # ip -> [timestamps]
    
    def is_allowed(self, ip: str) -> bool:
        """Проверяет, разрешён ли запрос."""
        now = time.time()
        
        # Удаляем старые запросы
        self.requests[ip] = [
            ts for ts in self.requests[ip]
            if now - ts < self.window
        ]
        
        # Проверяем лимит
        if len(self.requests[ip]) >= self.max_requests:
            return False
        
        # Добавляем текущий запрос
        self.requests[ip].append(now)
        return True
    
    def remaining(self, ip: str) -> int:
        """Оставшиеся запросы."""
        return max(0, self.max_requests - len(self.requests[ip]))


# Глобальный rate limiter
rate_limiter = RateLimiter(
    settings.rate_limit_requests,
    settings.rate_limit_window_seconds,
)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware для безопасности:
    - IP whitelist
    - Rate limiting
    - Логирование запросов
    """
    
    async def dispatch(self, request: Request, call_next):
        request_id = self._get_request_id(request)
        client_ip = self._get_client_ip(request)
        request.state.request_id = request_id
        request.state.client_ip = client_ip

        log_event(
            logger,
            "info",
            "http.request.started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=self._get_query_params(request),
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
        )

        # 1. IP Whitelist проверка
        if settings.ip_whitelist and client_ip not in settings.ip_whitelist:
            log_event(
                logger,
                "warning",
                "http.request.blocked",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client_ip=client_ip,
                reason="ip_not_allowlisted",
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Доступ запрещён"},
                headers={"X-Request-ID": request_id},
            )
        
        # 2. Rate limiting (кроме health check)
        if not request.url.path.startswith("/health"):
            if not rate_limiter.is_allowed(client_ip):
                log_event(
                    logger,
                    "warning",
                    "http.request.rate_limited",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    client_ip=client_ip,
                    limit=settings.rate_limit_requests,
                    window_seconds=settings.rate_limit_window_seconds,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Слишком много запросов"},
                    headers={"X-Request-ID": request_id},
                )
        
        # 3. Логирование
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_event(
                logger,
                "error",
                "http.request.failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client_ip=client_ip,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_event(
            logger,
            "info",
            "http.request.completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        
        # Добавляем заголовки rate limit
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
        response.headers["X-RateLimit-Remaining"] = str(rate_limiter.remaining(client_ip))
        response.headers["X-Request-ID"] = request_id
        
        return response

    def _get_request_id(self, request: Request) -> str:
        request_id = request.headers.get("X-Request-ID", "").strip()
        if request_id:
            return request_id[:128]
        return secrets.token_hex(8)

    def _get_query_params(self, request: Request) -> dict[str, str]:
        return sanitize_fields(dict(request.query_params))
    
    def _get_client_ip(self, request: Request) -> str:
        """Получает реальный IP клиента."""
        # Проверяем заголовки прокси
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback на direct connection
        if request.client:
            return request.client.host
        
        return "unknown"
