"""Shared helpers for reverse-proxy-aware request origin handling."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request

from .settings import settings


def request_is_https(request: Request) -> bool:
    """Detect HTTPS correctly when running behind a reverse proxy."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip() == "https"
    return request.url.scheme == "https"


def build_request_origin(request: Request) -> str:
    """Build the public request origin respecting reverse-proxy headers."""
    scheme = "https" if request_is_https(request) else "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def normalize_origin(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    parsed = urlsplit(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None

    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def allowed_request_origins(request: Request) -> set[str]:
    allowed = set()

    request_origin = normalize_origin(build_request_origin(request))
    if request_origin:
        allowed.add(request_origin)

    public_origin = normalize_origin(settings.public_base_url)
    if public_origin:
        allowed.add(public_origin)

    return allowed


def origin_matches_request(request: Request, origin: str | None) -> bool:
    normalized_origin = normalize_origin(origin)
    if normalized_origin is None:
        return False
    return normalized_origin in allowed_request_origins(request)
