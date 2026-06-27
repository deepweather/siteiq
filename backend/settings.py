"""Operational settings (env-driven).

These are runtime knobs: CORS origins, log level, etc. Domain constants
(hourly rates, sim tick durations) stay in `config.py` since they're part
of the simulation's behavior, not its deployment.

Override any field via env var, e.g.:
    SITEIQ_LOG_LEVEL=DEBUG uv run uvicorn main:app
"""
from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SITEIQ_", env_file=".env", extra="ignore")

    # Environment marker. Controls which knobs default to dev-friendly
    # values (cookie Secure, /dev/outbox mount, etc.). "dev" | "prod" | "test".
    env: str = "dev"

    # API. `NoDecode` disables JSON parsing of the env var — the validator
    # below splits the comma-separated string instead.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # Frontend origin (for WebSocket origin-check + email links).
    frontend_origin: str = "http://localhost:5173"

    # Database. SQLite by default for zero-setup dev/test. Override to
    # postgresql+asyncpg://... for production.
    database_url: str = "sqlite+aiosqlite:///./siteiq.db"

    # Auth.
    # 32+ random bytes (base64 ok). Used for signing the CSRF double-submit
    # token. Sessions themselves are opaque — they're stored server-side and
    # validated by hash, so a leaked session_secret cannot forge sessions.
    session_secret: str = "dev-only-not-secret-please-override-in-prod"
    session_cookie_name: str = "siteiq_session"
    session_lifetime_days: int = 14
    session_idle_days: int = 7
    cookie_domain: str | None = None
    # If True, sets the Secure cookie flag and uses the __Host- prefix.
    # Defaults follow `env`: True in prod, False in dev.
    cookie_secure: bool | None = None

    # Email.
    email_provider: str = "console"  # "console" | "resend"
    resend_api_key: str = ""
    email_from: str = "SiteIQ <noreply@siteiq.local>"

    # Rate limiting.
    rate_limit_redis_url: str = ""  # empty = in-memory limiter (dev only)

    # Outbox cleanup. Sent emails older than this are deleted by a
    # periodic background task. Set to 0 to disable cleanup entirely.
    email_outbox_retention_days: int = 90
    email_outbox_cleanup_interval_seconds: int = 3600  # 1 hour

    # Auth garbage collection. Revoked/expired auth_sessions and
    # consumed/expired verification_tokens are dropped after the
    # respective retention windows. 0 = disabled.
    auth_session_retention_days: int = 30
    auth_token_retention_days: int = 7
    auth_cleanup_interval_seconds: int = 3600

    # Portfolio estimator. Computes per-template waste at startup by
    # warming a transient SimulationEngine for each project. Tests turn
    # this off so the lifespan stays fast.
    compute_portfolio_at_startup: bool = True

    # Simulation
    default_project_id: str = "westhafen"

    # System of record — capture + query seams. Deterministic, dependency-
    # free defaults ship; the "llm" providers are wireable later without
    # touching call sites (mirrors the email_provider seam).
    capture_provider: str = "rule"          # "rule" | "llm"
    query_provider: str = "deterministic"   # "deterministic" | "llm"
    record_llm_api_key: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"

    # Vision
    yolo_model_path: str = "yolov8n.pt"
    videos_dir: str = "vision/videos"

    @property
    def is_prod(self) -> bool:
        return self.env.lower() == "prod"

    @property
    def is_dev(self) -> bool:
        return self.env.lower() == "dev"

    @property
    def effective_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_prod

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        """Allow comma-separated env var input: SITEIQ_CORS_ORIGINS='a,b,c'"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        v = v.upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, v: str) -> str:
        v = v.lower()
        if v not in {"text", "json"}:
            raise ValueError("log_format must be 'text' or 'json'")
        return v

    @field_validator("env")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        v = v.lower()
        if v not in {"dev", "prod", "test"}:
            raise ValueError("env must be one of dev|prod|test")
        return v

    @field_validator("email_provider")
    @classmethod
    def _validate_email_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in {"console", "resend"}:
            raise ValueError("email_provider must be one of console|resend")
        return v

    @field_validator("capture_provider")
    @classmethod
    def _validate_capture_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in {"rule", "llm"}:
            raise ValueError("capture_provider must be one of rule|llm")
        return v

    @field_validator("query_provider")
    @classmethod
    def _validate_query_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in {"deterministic", "llm"}:
            raise ValueError("query_provider must be one of deterministic|llm")
        return v


def get_settings() -> Settings:
    """Singleton-style accessor. Importable from anywhere without circular
    deps because Settings has no side-effects on construction."""
    return Settings()
