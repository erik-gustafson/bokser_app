from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    String,
    DateTime,
    JSON,
    Boolean,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base

BH_API_SCHEMA = "bh_api"


class BokserAPIWebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = {"schema": BH_API_SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
