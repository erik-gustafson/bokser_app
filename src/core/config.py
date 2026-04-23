from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    log_level: str = "INFO"

    lake_root: Path = Path("/data_lake")

    sos_api_url: str = "https://api.example.com"
    sos_static_token: str = Field(default="dev-token", repr=False)
    sos_auth_header_name: str = "Authorization"
    sos_auth_header_prefix: str = "Bearer"

    sos_poll_interval_minutes: int = 5

    http_timeout_seconds: float = 30.0
    http_max_connections: int = 20
    http_max_keepalive_connections: int = 10
    http_keepalive_expiry_seconds: float = 120.0

    @property
    def sos_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
