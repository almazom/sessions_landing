"""Central runtime settings loaded from .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).parent.parent.parent / ".env")


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    password: str
    session_secret: str
    session_expire_hours: int
    host: str
    backend_port: int
    dev_backend_port: int
    frontend_port: int
    public_host: str
    public_port: int
    caddy_admin_host: str
    caddy_admin_port: int
    ip_whitelist_raw: str
    ip_whitelist: list[str]
    rate_limit_requests: int
    rate_limit_window_seconds: int
    auth_cookie_max_age_seconds: int
    hsts_max_age_seconds: int
    default_session_limit: int
    max_session_limit: int
    dashboard_sessions_limit: int
    completed_sessions_preview_limit: int
    public_base_url: str
    telegram_auth_enabled: bool
    telegram_client_id: str
    telegram_client_secret: str
    telegram_bot_username: str
    telegram_bot_token: str
    telegram_allowed_user_ids: list[str]
    telegram_allowed_usernames: list[str]
    telegram_allowed_phone_numbers: list[str]
    telegram_request_phone: bool
    telegram_auth_max_age_seconds: int

    @property
    def telegram_oidc_configured(self) -> bool:
        return bool(self.telegram_client_id and self.telegram_client_secret)

    @property
    def telegram_widget_configured(self) -> bool:
        return bool(self.telegram_bot_username and self.telegram_bot_token)

    @property
    def telegram_login_configured(self) -> bool:
        return self.telegram_oidc_configured or self.telegram_widget_configured

    @property
    def telegram_allowlist_configured(self) -> bool:
        return bool(
            self.telegram_allowed_user_ids
            or self.telegram_allowed_usernames
            or self.telegram_allowed_phone_numbers
        )

    @property
    def telegram_auth_mode(self) -> str:
        if self.telegram_widget_configured:
            return "widget"
        if self.telegram_oidc_configured:
            return "oidc"
        return ""

    @property
    def telegram_login_enabled(self) -> bool:
        return (
            self.telegram_auth_enabled
            and self.telegram_login_configured
            and self.telegram_allowlist_configured
        )

    @property
    def auth_required(self) -> bool:
        return bool(self.password) or self.telegram_login_enabled


settings = Settings(
    db_path=Path(_get_str("NEXUS_DB_PATH", "~/.nexus/nexus.db")).expanduser(),
    password=_get_str("NEXUS_PASSWORD", ""),
    session_secret=_get_str("SESSION_SECRET", ""),
    session_expire_hours=_get_int("SESSION_EXPIRE_HOURS", 24),
    host=_get_str("NEXUS_HOST", "0.0.0.0"),
    backend_port=_get_int("NEXUS_BACKEND_PORT", _get_int("NEXUS_PORT", 18890)),
    dev_backend_port=_get_int("NEXUS_DEV_BACKEND_PORT", 8000),
    frontend_port=_get_int("NEXUS_FRONTEND_PORT", 3000),
    public_host=_get_str("NEXUS_PUBLIC_HOST", "107.174.231.22"),
    public_port=_get_int("NEXUS_PUBLIC_PORT", 8888),
    caddy_admin_host=_get_str("NEXUS_CADDY_ADMIN_HOST", "localhost"),
    caddy_admin_port=_get_int("NEXUS_CADDY_ADMIN_PORT", 2018),
    ip_whitelist_raw=_get_str("NEXUS_IP_WHITELIST", ""),
    ip_whitelist=_get_list("NEXUS_IP_WHITELIST"),
    rate_limit_requests=_get_int("RATE_LIMIT_REQUESTS", 100),
    rate_limit_window_seconds=_get_int("RATE_LIMIT_WINDOW", 60),
    auth_cookie_max_age_seconds=_get_int("NEXUS_AUTH_COOKIE_MAX_AGE_SECONDS", 86400),
    hsts_max_age_seconds=_get_int("NEXUS_HSTS_MAX_AGE_SECONDS", 31536000),
    default_session_limit=_get_int("NEXUS_DEFAULT_SESSION_LIMIT", 50),
    max_session_limit=_get_int("NEXUS_MAX_SESSION_LIMIT", 200),
    dashboard_sessions_limit=_get_int("NEXUS_DASHBOARD_SESSIONS_LIMIT", 100),
    completed_sessions_preview_limit=_get_int("NEXUS_COMPLETED_SESSIONS_PREVIEW_LIMIT", 20),
    public_base_url=_get_str("NEXUS_PUBLIC_URL", f"http://{_get_str('NEXUS_PUBLIC_HOST', '107.174.231.22')}:{_get_int('NEXUS_PUBLIC_PORT', 8888)}"),
    telegram_auth_enabled=_get_bool("TELEGRAM_AUTH_ENABLED", True),
    telegram_client_id=_get_str("TELEGRAM_CLIENT_ID", ""),
    telegram_client_secret=_get_str("TELEGRAM_CLIENT_SECRET", ""),
    telegram_bot_username=_get_str("TELEGRAM_BOT_USERNAME", "").lstrip("@"),
    telegram_bot_token=_get_str("TELEGRAM_BOT_TOKEN", ""),
    telegram_allowed_user_ids=_get_list("TELEGRAM_ALLOWED_USER_IDS"),
    telegram_allowed_usernames=[item.lower().lstrip("@") for item in _get_list("TELEGRAM_ALLOWED_USERNAMES")],
    telegram_allowed_phone_numbers=["".join(ch for ch in item if ch.isdigit()) for item in _get_list("TELEGRAM_ALLOWED_PHONE_NUMBERS")],
    telegram_request_phone=_get_bool("TELEGRAM_REQUEST_PHONE", True),
    telegram_auth_max_age_seconds=_get_int("TELEGRAM_AUTH_MAX_AGE_SECONDS", 600),
)
