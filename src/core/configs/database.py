from __future__ import annotations

from urllib.parse import quote_plus

from .base import AppBaseSettings


class DatabaseSettings(AppBaseSettings):
    postgres_server: str = "10.1.10.10"
    postgres_port: int = 5434
    postgres_user: str = "bokser_admin"
    postgres_password: str = ""
    postgres_db: str = "bokser_app_db"

    auto_create_tables: bool = False

    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)

        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return self.database_url.replace(
            "postgresql+psycopg://",
            "postgresql+asyncpg://",
            1,
        )


__all__ = ["DatabaseSettings"]
