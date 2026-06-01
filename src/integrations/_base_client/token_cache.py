from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.database.database import async_session
from src.database.models import AuthToken

logger = logging.getLogger(__name__)

PROVIDER_SOS = "sos_inventory"
PROVIDER_PRODUCTIV = "productiv"
PROVIDER_ACENDA = "acenda"
ALL_PROVIDERS: tuple[str, ...] = (
    PROVIDER_SOS,
    PROVIDER_PRODUCTIV,
    PROVIDER_ACENDA,
)


class TokenName(str, Enum):
    SOS = PROVIDER_SOS
    PRODUCTIV = PROVIDER_PRODUCTIV
    ACENDA = PROVIDER_ACENDA


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
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _is_expired(expires_at: datetime, *, skew_seconds: int) -> bool:
    refresh_before = _normalize_datetime(expires_at) - timedelta(seconds=skew_seconds)
    return datetime.now(timezone.utc) >= refresh_before


def _expires_at_from_payload(
    payload: dict[str, Any], *, default_seconds: int
) -> datetime:
    try:
        expires_in = int(payload.get("expires_in") or default_seconds)
    except (TypeError, ValueError):
        expires_in = default_seconds

    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)


def _as_refreshed_token(
    payload: dict[str, Any],
    *,
    provider: str,
    default_ttl_seconds: int,
) -> RefreshedToken | None:
    access_token = _clean(payload.get("access_token"))

    if access_token is None:
        logger.warning(
            "Token response missing access_token for provider=%s",
            provider,
        )
        return None

    return RefreshedToken(
        access_token=access_token,
        refresh_token=_clean(payload.get("refresh_token")),
        expires_at=_expires_at_from_payload(
            payload,
            default_seconds=default_ttl_seconds,
        ),
        token_type=_clean(payload.get("token_type")),
        scope=_clean(payload.get("scope")),
    )


async def _post_for_token(
    *,
    provider: str,
    token_url: str,
    headers: dict[str, str],
    data: dict[str, Any] | None,
    json_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            response = await client.post(
                token_url,
                headers=headers,
                data=data,
                json=json_data,
            )
    except httpx.HTTPError:
        logger.exception("Token request failed for provider=%s", provider)
        return None

    if response.status_code >= 400:
        logger.warning(
            "Token request failed for provider=%s status=%s",
            provider,
            response.status_code,
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.warning(
            "Token response returned invalid JSON for provider=%s",
            provider,
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Token response payload had unexpected shape for provider=%s",
            provider,
        )
        return None

    return payload


async def _refresh_sos_token(current: TokenRecord | None) -> RefreshedToken | None:
    refresh_token = _clean(current.refresh_token if current else None)

    if refresh_token:
        payload = await _post_for_token(
            provider=PROVIDER_SOS,
            token_url=settings.sos_token_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "api.sosinventory.com",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            json_data=None,
        )
        if payload is not None:
            refreshed = _as_refreshed_token(
                payload,
                provider=PROVIDER_SOS,
                default_ttl_seconds=3600,
            )
            if refreshed is not None:
                return refreshed

    auth_code = _clean(settings.sos_authorization_code)
    client_id = _clean(settings.sos_client_id)
    client_secret = _clean(settings.sos_client_secret)
    redirect_uri = _clean(settings.sos_oauth_redirect_uri)

    if not auth_code or not client_id or not client_secret or not redirect_uri:
        logger.warning(
            "SOS token refresh fallback unavailable; missing one of authorization_code/client_id/client_secret/redirect_uri"
        )
        return None

    payload = await _post_for_token(
        provider=PROVIDER_SOS,
        token_url=settings.sos_token_url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "api.sosinventory.com",
        },
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "redirect_uri": redirect_uri,
        },
        json_data=None,
    )

    if payload is None:
        return None

    return _as_refreshed_token(
        payload,
        provider=PROVIDER_SOS,
        default_ttl_seconds=3600,
    )


async def _refresh_productiv_token(_: TokenRecord | None) -> RefreshedToken | None:
    auth_key = _clean(settings.productiv_auth_key)
    user_login = _clean(settings.productiv_auth_user)

    if not auth_key or not user_login:
        logger.warning("Productiv refresh unavailable; missing auth key or user login")
        return None

    payload = await _post_for_token(
        provider=PROVIDER_PRODUCTIV,
        token_url=settings.productiv_token_url,
        headers={
            "Authorization": auth_key,
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "Accept-Encoding": "gzip,deflate,sdch",
            "Accept-Language": "en-US,en;q=0.8",
        },
        data=None,
        json_data={
            "grant_type": "client_credentials",
            "user_login": user_login,
        },
    )

    if payload is None:
        return None

    return _as_refreshed_token(
        payload,
        provider=PROVIDER_PRODUCTIV,
        default_ttl_seconds=3600,
    )


async def _refresh_acenda_token(_: TokenRecord | None) -> RefreshedToken | None:
    client_id = _clean(settings.acenda_client_id)
    client_secret = _clean(settings.acenda_client_secret)

    if not client_id or not client_secret:
        logger.warning("Acenda refresh unavailable; missing client id or client secret")
        return None

    payload = await _post_for_token(
        provider=PROVIDER_ACENDA,
        token_url=settings.acenda_token_url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        json_data=None,
    )

    if payload is None:
        return None

    return _as_refreshed_token(
        payload,
        provider=PROVIDER_ACENDA,
        default_ttl_seconds=300,
    )


async def refresh_provider_token(
    *,
    provider: str,
    current: TokenRecord | None,
) -> RefreshedToken | None:
    if provider == PROVIDER_SOS:
        return await _refresh_sos_token(current)

    if provider == PROVIDER_PRODUCTIV:
        return await _refresh_productiv_token(current)

    if provider == PROVIDER_ACENDA:
        return await _refresh_acenda_token(current)

    logger.error("Unsupported token provider=%s", provider)
    return None


async def _select_token_row(session: AsyncSession, provider: str) -> AuthToken | None:
    result = await session.execute(
        select(AuthToken).where(AuthToken.provider == provider)
    )
    return result.scalar_one_or_none()


def _row_to_record(token_row: AuthToken) -> TokenRecord:
    return TokenRecord(
        provider=token_row.provider,
        access_token=token_row.access_token,
        refresh_token=token_row.refresh_token,
        expires_at=_normalize_datetime(token_row.expires_at),
    )


async def get_auth_token_from_db(
    provider: str,
    *,
    session: AsyncSession | None = None,
) -> TokenRecord | None:
    if session is not None:
        token_row = await _select_token_row(session, provider)
        return _row_to_record(token_row) if token_row is not None else None

    async with async_session() as owned_session:
        token_row = await _select_token_row(owned_session, provider)
        return _row_to_record(token_row) if token_row is not None else None


async def _upsert_auth_token_in_session(
    session: AsyncSession,
    *,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime,
) -> None:
    token_row = await _select_token_row(session, provider)
    normalized_expires_at = _normalize_datetime(expires_at)

    if token_row is None:
        token_row = AuthToken(
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=normalized_expires_at,
        )
        session.add(token_row)
        await session.flush()
        return

    token_row.access_token = access_token

    if refresh_token is not None:
        token_row.refresh_token = refresh_token

    token_row.expires_at = normalized_expires_at
    await session.flush()


async def upsert_auth_token(
    *,
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime,
) -> None:
    async with async_session() as session:
        try:
            await _upsert_auth_token_in_session(
                session,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def delete_auth_token_from_db(provider: str) -> None:
    async with async_session() as session:
        try:
            token_row = await _select_token_row(session, provider)

            if token_row is not None:
                await session.delete(token_row)

            await session.commit()
        except Exception:
            await session.rollback()
            raise


class TokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, TokenRecord] = {}
        self._lock = asyncio.Lock()
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    async def warmup_on_startup(self, strict: bool | None = None) -> None:
        strict_mode = settings.token_warmup_strict if strict is None else strict

        for provider in ALL_PROVIDERS:
            try:
                await self._warm_provider(provider)
            except Exception:
                if strict_mode:
                    raise

                logger.exception("Token warmup failed for provider=%s", provider)

    async def _warm_provider(self, provider: str) -> None:
        record = await self.get(provider, load_from_db=True)

        if record is not None and not _is_expired(
            record.expires_at,
            skew_seconds=settings.token_refresh_skew_seconds,
        ):
            return

        refreshed = await self.force_refresh(
            provider,
            expected_access_token=record.access_token if record else None,
            allow_missing_current=True,
            skew_seconds=settings.token_refresh_skew_seconds,
        )

        if refreshed is None:
            raise RuntimeError(f"Unable to warm token for provider={provider}")

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

        await self._set_cached_record(provider_key, db_record)
        return db_record

    async def _set_cached_record(self, provider_key: str, record: TokenRecord) -> None:
        async with self._lock:
            self._tokens[provider_key] = record

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

        await self._set_cached_record(provider_key, record)

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
        skew_seconds: int | None = None,
    ) -> str:
        provider_key = _provider_key(provider)
        effective_skew = (
            settings.token_refresh_skew_seconds
            if skew_seconds is None
            else skew_seconds
        )
        record = await self.get(provider_key)

        if record is not None and not _is_expired(
            record.expires_at,
            skew_seconds=effective_skew,
        ):
            return record.access_token

        refreshed = await self.force_refresh(
            provider_key,
            expected_access_token=record.access_token if record else None,
            allow_missing_current=True,
            skew_seconds=effective_skew,
        )

        if refreshed is None:
            raise RuntimeError(
                f"Unable to refresh access token for provider={provider_key}"
            )

        return refreshed.access_token

    async def force_refresh(
        self,
        provider: TokenName | str,
        *,
        expected_access_token: str | None = None,
        allow_missing_current: bool = False,
        skew_seconds: int | None = None,
    ) -> TokenRecord | None:
        provider_key = _provider_key(provider)
        effective_skew = (
            settings.token_refresh_skew_seconds
            if skew_seconds is None
            else skew_seconds
        )
        refresh_lock = await self._get_refresh_lock(provider_key)

        async with refresh_lock:
            current = await self.get(provider_key, load_from_db=True)
            current = await self._short_circuit_if_already_refreshed(
                provider_key=provider_key,
                current=current,
                expected_access_token=expected_access_token,
                skew_seconds=effective_skew,
            )
            if current is not None:
                return current

            return await self._refresh_with_cross_container_lock(
                provider_key,
                expected_access_token=expected_access_token,
                allow_missing_current=allow_missing_current,
                skew_seconds=effective_skew,
            )

    async def _short_circuit_if_already_refreshed(
        self,
        *,
        provider_key: str,
        current: TokenRecord | None,
        expected_access_token: str | None,
        skew_seconds: int,
    ) -> TokenRecord | None:
        if current is None:
            return None

        if expected_access_token is None and not _is_expired(
            current.expires_at,
            skew_seconds=skew_seconds,
        ):
            return current

        if (
            expected_access_token is not None
            and current.access_token != expected_access_token
            and not _is_expired(current.expires_at, skew_seconds=skew_seconds)
        ):
            return current

        if expected_access_token is None:
            logger.info(
                "Refreshing token for provider=%s with no expected_access_token",
                provider_key,
            )

        return None

    async def _refresh_with_cross_container_lock(
        self,
        provider_key: str,
        *,
        expected_access_token: str | None,
        allow_missing_current: bool,
        skew_seconds: int,
    ) -> TokenRecord | None:
        async with async_session() as session:
            try:
                async with session.begin():
                    await self._acquire_provider_db_lock(session, provider_key)
                    db_current = await get_auth_token_from_db(
                        provider_key,
                        session=session,
                    )

                    if db_current is not None:
                        refreshed_current = (
                            await self._short_circuit_if_already_refreshed(
                                provider_key=provider_key,
                                current=db_current,
                                expected_access_token=expected_access_token,
                                skew_seconds=skew_seconds,
                            )
                        )
                        if refreshed_current is not None:
                            await self._set_cached_record(
                                provider_key, refreshed_current
                            )
                            return refreshed_current

                    current = db_current
                    if current is None and not allow_missing_current:
                        logger.warning(
                            "No auth token found for provider=%s",
                            provider_key,
                        )
                        return None

                    refreshed = await refresh_provider_token(
                        provider=provider_key,
                        current=current,
                    )
                    if refreshed is None:
                        return None

                    merged_refresh_token = refreshed.refresh_token or (
                        current.refresh_token if current is not None else None
                    )

                    record = TokenRecord(
                        provider=provider_key,
                        access_token=refreshed.access_token,
                        refresh_token=merged_refresh_token,
                        expires_at=_normalize_datetime(refreshed.expires_at),
                    )

                    await _upsert_auth_token_in_session(
                        session,
                        provider=provider_key,
                        access_token=record.access_token,
                        refresh_token=record.refresh_token,
                        expires_at=record.expires_at,
                    )

                await self._set_cached_record(provider_key, record)
                return record
            except Exception:
                logger.exception("Token refresh failed for provider=%s", provider_key)
                return None

    async def _acquire_provider_db_lock(
        self,
        session: AsyncSession,
        provider_key: str,
    ) -> None:
        lock_key = int.from_bytes(
            hashlib.blake2b(provider_key.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
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


__all__ = [
    "ALL_PROVIDERS",
    "PROVIDER_SOS",
    "PROVIDER_PRODUCTIV",
    "PROVIDER_ACENDA",
    "TokenName",
    "TokenRecord",
    "RefreshedToken",
    "TokenStore",
    "token_store",
    "get_auth_token_from_db",
    "upsert_auth_token",
    "delete_auth_token_from_db",
    "refresh_provider_token",
]
