from __future__ import annotations

from pydantic import Field
from dataclasses import dataclass
from dataclasses import dataclass
from typing import ClassVar
from .base import AppBaseSettings


@dataclass(frozen=True, slots=True)
class AcendaEndpoint:
    name: str
    path: str
    entity_name: str
    params: dict = {}
    enabled: bool = True


# fmt: off
class AcendaSettings(AppBaseSettings):
    acenda_api_url: str = "https://api.acenda.io/v1"
    acenda_token_url: str = "https://login.acenda.io/auth/realms/acenda/protocol/openid-connect/token"
    acenda_client_id: str = ""
    acenda_client_secret: str = ""
    acenda_rate_limiter: float = 0.501
    acenda_poll_interval_minutes: int = 5

    ACENDA_ENDPOINTS: ClassVar[tuple[AcendaEndpoint, ...]] = (
        AcendaEndpoint(name="all_orders", path="/order", entity_name="all_orders", params={"updated_at":{"$gt":"2026-05-28T21:02:22.246Z"}}),
        # AcendaEndpoint(name="query_orders", path="/search/order/", entity_name="query_orders"),
    )
# fmt: on
    @classmethod
    def acenda_enabled_endpoints(cls) -> tuple[AcendaEndpoint, ...]:
        return tuple(endpoint for endpoint in cls.ACENDA_ENDPOINTS if endpoint.enabled)

    @classmethod
    def acenda_paths(cls) -> list[str]:
        return [endpoint.path for endpoint in cls.acenda_enabled_endpoints()]

    @classmethod
    def acenda_endpoint_names(cls) -> list[str]:
        return [endpoint.name for endpoint in cls.acenda_enabled_endpoints()]

    @property
    def acenda_base_headers(self) -> dict[str, str]:
        return {
            "X-Astur-Organization": "bokserhome",
        }


__all__ = ["AcendaSettings"]
