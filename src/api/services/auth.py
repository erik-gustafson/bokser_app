from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.core.config import settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> None:
    if not settings.BH_API_KEY:
        raise HTTPException(status_code=503, detail="BH_API_KEY not configured")
    if not x_api_key or x_api_key != settings.BH_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
