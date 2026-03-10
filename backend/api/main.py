"""Agent Nexus FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .logging_utils import get_logger, log_event
from .middleware import SecurityMiddleware
from .scanner import session_scanner
from .settings import settings

logger = get_logger("agent_nexus.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    log_event(
        logger,
        "info",
        "app.starting",
        db_path=settings.db_path,
        auth_required=settings.auth_required,
        password_enabled=bool(settings.password),
        telegram_mode=settings.telegram_auth_mode or None,
        public_base_url=settings.public_base_url,
        backend_port=settings.backend_port,
    )

    # Ensure database directory exists
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    session_count = session_scanner.ensure_loaded()
    log_event(logger, "info", "app.sessions_warmed", session_count=session_count)

    yield

    log_event(logger, "info", "app.stopping")


# Create FastAPI app
app = FastAPI(
    title="Agent Nexus",
    description="Real-time AI coding agent monitoring dashboard",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will be restricted by IP whitelist
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middleware (IP whitelist, rate limiting)
app.add_middleware(SecurityMiddleware)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        f"max-age={settings.hsts_max_age_seconds}; includeSubDomains"
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # Content Security Policy (with CDN for Swagger UI)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://oauth.telegram.org https://telegram.org; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com https://oauth.telegram.org https://telegram.org; "
        "connect-src 'self' ws: wss: https://oauth.telegram.org https://telegram.org; "
        "frame-src 'self' https://oauth.telegram.org https://telegram.org;"
    )

    return response


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "agent-nexus",
        "version": "0.1.0",
    }


# API info endpoint
@app.get("/api", tags=["System"])
async def api_info():
    """API information."""
    return {
        "name": "Agent Nexus API",
        "version": "0.1.0",
        "endpoints": {
            "sessions": "/api/sessions",
            "latest_session": "/api/latest-session",
            "metrics": "/api/metrics",
            "websocket": "/ws",
            "docs": "/api/docs",
        }
    }


# Robots.txt - block all crawlers
@app.get("/robots.txt", tags=["System"])
async def robots_txt():
    """Block search engine crawlers."""
    return JSONResponse(
        content={"text": "User-agent: *\nDisallow: /"},
        media_type="text/plain"
    )


# Import and include routers
from .routes import sessions_router, websocket_router, auth_router
app.include_router(sessions_router)
app.include_router(websocket_router)
app.include_router(auth_router)
