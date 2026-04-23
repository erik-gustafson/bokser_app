from __future__ import annotations

from src.bokser_app.core.config import settings

PROVIDER_SOS = "sos_inventory"


async def get_valid_token_async(provider: str) -> str:
    """
    Replace this with your real async token refresh/cache logic later.
    """
    if provider != PROVIDER_SOS:
        raise ValueError(f"Unsupported provider: {provider}")

    token = settings.sos_static_token
    if not token:
        raise RuntimeError("SOS token is missing")

    return token
