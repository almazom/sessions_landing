"""Request-level auth and origin rules for interactive endpoints."""

from __future__ import annotations

from fastapi import Request, Response

from .request_origin import origin_matches_request

INTERACTIVE_AUTH_TOKEN = "session-cookie"
INTERACTIVE_ORIGIN_POLICY = "same-origin"
INTERACTIVE_TRANSPORT_SECURITY = "cookie-bound-http"
_ALLOWED_FETCH_SITES = {"same-origin", "same-site", "none"}


def enforce_interactive_request_security(request: Request) -> None:
    origin = request.headers.get("origin")
    sec_fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()

    if origin and not origin_matches_request(request, origin):
        raise PermissionError("interactive route requires a same-origin request")

    if sec_fetch_site == "cross-site":
        raise PermissionError("interactive route requires a same-origin request")

    if origin and sec_fetch_site and sec_fetch_site not in _ALLOWED_FETCH_SITES:
        raise PermissionError("interactive route rejected unsupported browser transport")


def apply_interactive_security_headers(response: Response) -> None:
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Interactive-Auth-Token"] = INTERACTIVE_AUTH_TOKEN
    response.headers["X-Interactive-Origin-Policy"] = INTERACTIVE_ORIGIN_POLICY
    response.headers["X-Interactive-Transport-Security"] = INTERACTIVE_TRANSPORT_SECURITY
    response.headers["Vary"] = _merge_vary_header(response.headers.get("Vary"), "Origin")


def _merge_vary_header(current_value: str | None, next_value: str) -> str:
    values = {
        item.strip()
        for item in (current_value or "").split(",")
        if item.strip()
    }
    values.add(next_value)
    return ", ".join(sorted(values))
