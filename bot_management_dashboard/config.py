from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_DEFAULT_JWT_SECRET = "change-me-jwt-secret"
_DEFAULT_ENCRYPTION_KEY = "xIjf7vhbGJy9vVxjQU5E4h3wIPMQRrLhVAW8KD4x5gM="


@dataclass(frozen=True)
class DashboardSettings:
    app_env: str
    database_url: str
    jwt_secret: str
    encryption_key: str
    jwt_exp_minutes: int
    nonce_ttl_seconds: int
    auth_rate_limit: int
    auth_rate_window_seconds: int
    allowed_domain: str
    cors_origins: list[str]
    static_dir: Path

    def validate(self) -> None:
        if self.app_env == "production":
            if self.jwt_secret == _DEFAULT_JWT_SECRET:
                raise ValueError("DASHBOARD_JWT_SECRET must be set in production.")
            if self.encryption_key == _DEFAULT_ENCRYPTION_KEY:
                raise ValueError("DASHBOARD_ENCRYPTION_KEY must be set in production.")


def _parse_cors_origins(raw: str) -> list[str]:
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> DashboardSettings:
    settings = DashboardSettings(
        app_env=os.getenv("DASHBOARD_APP_ENV", "development").lower(),
        database_url=os.getenv("DASHBOARD_DATABASE_URL", "sqlite:///./bot_dashboard.db"),
        jwt_secret=os.getenv("DASHBOARD_JWT_SECRET", _DEFAULT_JWT_SECRET),
        encryption_key=os.getenv("DASHBOARD_ENCRYPTION_KEY", _DEFAULT_ENCRYPTION_KEY),
        jwt_exp_minutes=int(os.getenv("DASHBOARD_JWT_EXP_MINUTES", "60")),
        nonce_ttl_seconds=int(os.getenv("DASHBOARD_NONCE_TTL_SECONDS", "300")),
        auth_rate_limit=int(os.getenv("DASHBOARD_AUTH_RATE_LIMIT", "30")),
        auth_rate_window_seconds=int(os.getenv("DASHBOARD_AUTH_RATE_WINDOW_SECONDS", "60")),
        allowed_domain=os.getenv("DASHBOARD_ALLOWED_DOMAIN", "bot-dashboard.local"),
        cors_origins=_parse_cors_origins(os.getenv("DASHBOARD_CORS_ORIGINS", "")),
        static_dir=Path(__file__).parent / "static",
    )
    settings.validate()
    return settings


def clear_settings_cache() -> None:
    get_settings.cache_clear()

