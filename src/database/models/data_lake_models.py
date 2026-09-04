from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Integer, text, BigInteger, func, JSON
from src.database.database import Base
from datetime import datetime

# Statuses
# LANDED      file written and ready to load
# PROCESSING  loader claimed it
# LOADED      successfully loaded to DB
# FAILED      failed and needs review or retry
# SKIPPED     intentionally ignored


class DataLakeFile(Base):
    __tablename__ = "data_lake_files"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_name: Mapped[str] = mapped_column(String(64), index=True)
    entity_name: Mapped[str] = mapped_column(String(64), index=True)

    file_path: Mapped[str] = mapped_column(Text, unique=True)
    file_name: Mapped[str] = mapped_column(String(255))

    record_count: Mapped[int] = mapped_column(default=0)
    file_size_bytes: Mapped[int | None]
    sha256: Mapped[str | None] = mapped_column(String(64))

    landed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(32),
        default="LANDED",
        index=True,
    )

    last_error: Mapped[str | None] = mapped_column(Text)

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    loaded_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    source_min_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    source_max_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class DataLakeCursors(Base):
    __tablename__ = "data_lake_cursors"

    source_name: Mapped[str] = mapped_column(String(64), index=True, primary_key=True)
    entity_name: Mapped[str] = mapped_column(String(64), index=True, primary_key=True)
    last_successful_run: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
