from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import SettingsConfigDict
from .configs import *


class Settings(
    DatabaseSettings,
    HttpxSettings,
    SosSettings,
    ProductivSettings,
    AcendaSettings,
    BokserAPISettings,
):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "dev"
    log_level: str = "INFO"

    lake_root: Path = Path("/data_lake")
    logs_root: Path = Path("/app/logs")
    downloads_root: Path = Path("/app/downloads")
    reporting_archive_root: Path = Path("/app/reporting_archive")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


__all__ = ["Settings", "get_settings", "settings"]
