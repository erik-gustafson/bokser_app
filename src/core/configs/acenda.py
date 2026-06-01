from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, ClassVar
from pathlib import Path
from .base import AppBaseSettings


@dataclass(frozen=True, slots=True)
class AcendaEndpoint:
    name: str
    path: str
    entity_name: str
    params: dict[str, Any] = field(default_factory=dict)
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
        AcendaEndpoint(name="all_orders", path="/order", entity_name="all_orders", params={"query":{"updated_at":{"$gt":None}}}),
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

    @classmethod
    def get_acenda_endpoint_params(
        cls,
        endpoint_name: str,
        watermark: str | None = None,
    ) -> dict:
        

        if endpoint_name == "all_orders":

            one_day_back = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

            updated_after = watermark or one_day_back
            
            return {
                "query": json.dumps({
                    "updated_at": {
                        "$gt": updated_after
                    }
                })
            }

        return {}

    @classmethod
    def get_acenda_endpoint_watermark(cls, file_path: Path, name:str) -> str | None:

        if not name:
            return None

        if name == "all_orders":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            watermark = data.get("all_orders", {}).get("last_updated_date", None)

            return watermark
        
        else:
            return None


    @property
    def acenda_base_headers(self) -> dict[str, str]:
        return {
            "X-Astur-Organization": "bokserhome",
        }



__all__ = ["AcendaSettings"]
