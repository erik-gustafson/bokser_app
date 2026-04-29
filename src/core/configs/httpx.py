from __future__ import annotations

from .base import AppBaseSettings


class HttpxSettings(AppBaseSettings):
    http_timeout_seconds: float = 30.0
    http_max_connections: int = 20
    http_max_keepalive_connections: int = 10
    http_keepalive_expiry_seconds: float = 120.0


__all__ = ["HttpxSettings"]
