from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import httpx
from sqlalchemy import select

# Adjust these imports to match your repo.
from src.core.config import settings
from src.database.database import async_session
from src.database.models import AuthToken

logger = logging.getLogger(__name__)

PROVIDER_SOS = "sos_inventory"
PROVIDER_PRODUCTIV = "productiv"


class TokenName(str, Enum):
    SOS = PROVIDER_SOS
    PRODUCTIV = PROVIDER_PRODUCTIV


@dataclass(frozen=True, slots=True)
class TokenRecord:
    provider: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RefreshedToken:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    token_type: str | None = None
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRefreshConfig:
    token_url: str
    headers: dict | None
    data: dict | None
    json: dict | None


def _provider_key(provider: TokenName | str) -> str:
    if isinstance(provider, TokenName):
        return provider.value
    return provider


def _clean(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()
    return value or None


def _normalize_datetime(value: datetime) -> datetime:
    """
    Normalize datetimes to timezone-aware UTC.

    If your DB column is timezone=False and expects naive UTC datetimes,
    change the final return to:

        return normalized.replace(tzinfo=None)
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _is_expired(expires_at: datetime, *, skew_seconds: int = 60) -> bool:
    normalized_expires_at = _normalize_datetime(expires_at)
    refresh_before = normalized_expires_at - timedelta(seconds=skew_seconds)

    return datetime.now(timezone.utc) >= refresh_before


def _expires_at_from_payload(payload: dict[str, Any]) -> datetime:
    try:
        expires_in = int(payload.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600

    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)


def _refresh_config_for_provider(provider: str) -> ProviderRefreshConfig:

    if provider == PROVIDER_SOS:
        refresh_token = token_store.get_refresh_token(PROVIDER_SOS)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "api.sosinventory.com",
        }

        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        return ProviderRefreshConfig(
            token_url=settings.sos_token_url,
            headers=headers,
            data=data,
            json=None,
        )

    if provider == PROVIDER_PRODUCTIV:
        """No Refresh Token for Productiv, Authentication is refreshed via User Authentication"""
        headers = {
            "Authorization": settings.productiv_auth_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        json = {
            "grant_type": "client_credentials",
            "user_login": settings.productiv_auth_user,
        }

        return ProviderRefreshConfig(
            token_url=settings.productiv_token_url,
            headers=headers,
            data=None,
            json=json,
        )

    """

"""

    raise ValueError(f"Unsupported token provider: {provider}")


async def get_auth_token_from_db(provider: str) -> TokenRecord | None:
    async with async_session() as session:
        result = await session.execute(
            select(AuthToken).where(AuthToken.provider == provider)
        )
        token_row = result.scalar_one_or_none()

        if token_row is None:
            return None

        return TokenRecord(
            provider=token_row.provider,
            access_token=token_row.access_token,
            refresh_token=token_row.refresh_token,
            expires_at=_normalize_datetime(token_row.expires_at),
        )


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

                # Preserve the existing refresh token when the provider
                # does not return a rotated refresh token.
                if refresh_token is not None:
                    token_row.refresh_token = refresh_token

                token_row.expires_at = normalized_expires_at

            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def delete_auth_token_from_db(provider: str) -> None:
    async with async_session() as session:
        try:
            result = await session.execute(
                select(AuthToken).where(AuthToken.provider == provider)
            )
            token_row = result.scalar_one_or_none()

            if token_row is not None:
                await session.delete(token_row)

            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def refresh_provider_token(
    *,
    provider: str,
) -> RefreshedToken | None:
    """
    Calls the provider OAuth refresh endpoint.

    This function does not update memory or DB state.
    TokenStore.force_refresh(...) handles persistence.
    """

    try:
        config = _refresh_config_for_provider(provider)
    except Exception:
        logger.exception("No refresh config available for provider=%s", provider)
        return None

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                config.token_url,
                data=config.data,
                json=config.json,
                headers=config.headers,
            )
    except httpx.HTTPError:
        logger.exception("Token refresh request failed for provider=%s", provider)
        return None

    if response.status_code >= 400:
        logger.warning(
            "Token refresh failed for provider=%s status=%s",
            provider,
            response.status_code,
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.warning("Token refresh returned invalid JSON for provider=%s", provider)
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Token refresh returned unexpected payload for provider=%s", provider
        )
        return None

    access_token = _clean(payload.get("access_token"))

    if access_token is None:
        logger.warning(
            "Token refresh response missing access_token for provider=%s", provider
        )
        return None

    return RefreshedToken(
        access_token=access_token,
        refresh_token=_clean(payload.get("refresh_token")),
        expires_at=_expires_at_from_payload(payload),
        token_type=_clean(payload.get("token_type")),
        scope=_clean(payload.get("scope")),
    )


class TokenStore:
    """
    Process-local memory cache + DB persistence.

    Memory gives fast access while the container is running.
    DB gives persistence across container restarts.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, TokenRecord] = {}
        self._lock = asyncio.Lock()
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    async def get(
        self,
        provider: TokenName | str,
        *,
        load_from_db: bool = True,
    ) -> TokenRecord | None:
        provider_key = _provider_key(provider)

        async with self._lock:
            cached = self._tokens.get(provider_key)

        if cached is not None:
            return cached

        if not load_from_db:
            return None

        db_record = await get_auth_token_from_db(provider_key)

        if db_record is None:
            return None

        async with self._lock:
            self._tokens[provider_key] = db_record

        return db_record

    async def set(
        self,
        provider: TokenName | str,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime,
        persist: bool = True,
    ) -> TokenRecord:
        provider_key = _provider_key(provider)

        record = TokenRecord(
            provider=provider_key,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=_normalize_datetime(expires_at),
        )

        async with self._lock:
            self._tokens[provider_key] = record

        if persist:
            await upsert_auth_token(
                provider=provider_key,
                access_token=record.access_token,
                refresh_token=record.refresh_token,
                expires_at=record.expires_at,
            )

        return record

    async def get_access_token(self, provider: TokenName | str) -> str | None:
        record = await self.get(provider)
        return record.access_token if record else None

    async def get_refresh_token(self, provider: TokenName | str) -> str | None:
        record = await self.get(provider)
        return record.refresh_token if record else None

    async def get_valid_access_token(
        self,
        provider: TokenName | str,
        *,
        skew_seconds: int = 60,
    ) -> str:
        provider_key = _provider_key(provider)
        record = await self.get(provider_key)

        if record is None:
            raise RuntimeError(f"No auth token found for provider={provider_key}")

        if not _is_expired(record.expires_at, skew_seconds=skew_seconds):
            return record.access_token

        refreshed = await self.force_refresh(provider_key)

        if refreshed is None:
            raise RuntimeError(
                f"Unable to refresh access token for provider={provider_key}"
            )

        return refreshed.access_token

    async def force_refresh(self, provider: TokenName | str) -> TokenRecord | None:
        """
        Force-refresh using the stored refresh token.

        This is what OAuthBearerAuth calls after a 401.
        """

        provider_key = _provider_key(provider)
        refresh_lock = await self._get_refresh_lock(provider_key)

        async with refresh_lock:
            current = await self.get(provider_key)

            if current is None:
                logger.warning("No auth token found for provider=%s", provider_key)
                return None

            if not current.refresh_token:
                logger.warning(
                    "No refresh token available for provider=%s", provider_key
                )
                return None

            refreshed = await refresh_provider_token(
                provider=provider_key,
            )

            if refreshed is None:
                return None

            # Preserve the previous refresh token if the provider does not rotate it.
            return await self.set(
                provider_key,
                access_token=refreshed.access_token,
                refresh_token=refreshed.refresh_token or current.refresh_token,
                expires_at=refreshed.expires_at,
                persist=True,
            )

    async def clear_memory(self, provider: TokenName | str | None = None) -> None:
        async with self._lock:
            if provider is None:
                self._tokens.clear()
                return

            self._tokens.pop(_provider_key(provider), None)

    async def clear(
        self,
        provider: TokenName | str,
        *,
        delete_from_db: bool = False,
    ) -> None:
        provider_key = _provider_key(provider)

        async with self._lock:
            self._tokens.pop(provider_key, None)

        if delete_from_db:
            await delete_auth_token_from_db(provider_key)

    async def _get_refresh_lock(self, provider: str) -> asyncio.Lock:
        async with self._lock:
            refresh_lock = self._refresh_locks.get(provider)

            if refresh_lock is None:
                refresh_lock = asyncio.Lock()
                self._refresh_locks[provider] = refresh_lock

            return refresh_lock


token_store = TokenStore()
