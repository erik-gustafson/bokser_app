from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from src.core.config import settings
from src.database.database import async_session
from src.database.models.auth_models import AuthToken


logger = logging.getLogger(__name__)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def get_sos_auth_token_from_code():

    token_url = "https://api.sosinventory.com/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "api.sosinventory.com",
    }
    token_response = httpx.post(
        token_url,
        headers=headers,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.sos_client_id,
            "client_secret": settings.sos_client_secret,
            "code": settings.sos_authorization_code,
            "redirect_uri": "https://live.sosinventory.com/",
        },
    )

    if token_response.status_code != 200:
        raise Exception

    tokens = token_response.json()

    expires_in = int(tokens.get("expires_in", 7775999))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    await upsert_auth_token(
        provider="sos_inventory",
        access_token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        expires_at=expires_at,
    )
    set_sos_auth_token(tokens.get("access_token"))


async def upsert_auth_token(
    *,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime,
) -> None:
    async with async_session() as session:
        try:
            result = await session.execute(
                select(AuthToken).where(AuthToken.provider == provider)
            )
            token_row = result.scalar_one_or_none()
            normalized_expires_at = _normalize_datetime(expires_at)

            if token_row is None:
                token_row = AuthToken(
                    provider=provider,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=normalized_expires_at,
                )
                session.add(token_row)
            else:
                token_row.access_token = access_token
                token_row.refresh_token = refresh_token
                token_row.expires_at = normalized_expires_at

            await session.commit()
        except Exception:
            await session.rollback()
            raise


#####

_sos_auth_token: str | None = None


def set_sos_auth_token(token: str | None) -> None:
    global _sos_auth_token
    _sos_auth_token = token


def get_sos_auth_token() -> str | None:
    return _sos_auth_token


def clear_sos_auth_token() -> None:
    global _sos_auth_token
    _sos_auth_token = None


async def load_auth_token_from_db(provider: str) -> AuthToken | None:
    async with async_session() as session:
        result = await session.execute(
            select(AuthToken).where(AuthToken.provider == provider)
        )
        return result.scalar_one_or_none()
