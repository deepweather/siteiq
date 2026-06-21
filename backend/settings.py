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

    # API. `NoDecode` disables JSON parsing of the env var — the validator
    # below splits the comma-separated string instead.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # Simulation
    default_project_id: str = "westhafen"

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"

    # Vision
    yolo_model_path: str = "yolov8n.pt"
    videos_dir: str = "vision/videos"

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


def get_settings() -> Settings:
    """Singleton-style accessor. Importable from anywhere without circular
    deps because Settings has no side-effects on construction."""
    return Settings()
