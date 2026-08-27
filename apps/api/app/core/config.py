"""Backend application configuration, sourced from environment variables."""

from __future__ import annotations

import os


class Settings:
    APP_NAME: str = "LLM Benchmarking Framework API"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = os.environ.get("BENCHLAB_CORS_ORIGINS", "*").split(",")
    LOG_LEVEL: str = os.environ.get("BENCHLAB_LOG_LEVEL", "INFO")


settings = Settings()
