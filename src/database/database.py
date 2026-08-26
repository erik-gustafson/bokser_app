# src/database/database.py
from __future__ import annotations

from contextlib import contextmanager
from typing import AsyncIterator, Iterator, Any, Callable, Optional
from dataclasses import dataclass
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings
from src.database.base import Base

TransformFunc = Callable[[Any], Any]


def get_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url

    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace(
            "postgresql+psycopg://",
            "postgresql+asyncpg://",
            1,
        )

    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )

    raise ValueError(
        f"Unsupported database URL: {database_url!r}. "
        "Expected postgresql+psycopg://, postgresql+asyncpg://, or postgresql://."
    )


sync_engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def init_db() -> None:
    if getattr(settings, "auto_create_tables", False):
        with sync_engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS acenda"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS sos"))
            Base.metadata.create_all(bind=connection)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_context_session() -> Iterator[Session]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async_database_url = get_async_database_url(settings.database_url)

async_engine = create_async_engine(
    async_database_url,
    future=True,
    echo=False,
    echo_pool=False,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    class_=AsyncSession,
)


async def get_async_db() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


@dataclass
class FieldMap:
    """
    Map a dotted payload path to a model attribute, with optional transform.
    """

    source: str  # payload path, e.g., "order.id"
    target: str  # model attribute, e.g., "external_id"
    transform: Optional[TransformFunc] = None


__all__ = [
    "Base",
    "sync_engine",
    "SessionLocal",
    "init_db",
    "get_db",
    "get_context_session",
    "async_engine",
    "async_session",
    "get_async_db",
]
