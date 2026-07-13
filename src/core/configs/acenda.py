from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, ClassVar, Tuple
from pathlib import Path
from .base import AppBaseSettings

from src.storage.states.state_store import acenda_state


@dataclass(frozen=True, slots=True)
class AcendaEndpoint:
    name: str
    path: str
    data_type: str
    params: dict[str, Any] = field(default_factory=dict)
    state_data: Tuple[str, ...] | None = None
    enabled: bool = True


# fmt: off
class AcendaSettings(AppBaseSettings):
    acenda_api_url: str = "https://api.acenda.io/v1"
    acenda_token_url: str = "https://login.acenda.io/auth/realms/acenda/protocol/openid-connect/token"
    acenda_client_id: str = ""
    acenda_client_secret: str = ""
    acenda_rate_limiter: float = 0.501
    acenda_poll_interval_minutes: int = 5
    acenda_lake_load_interval_minutes: int = 5

    ACENDA_ENDPOINTS: ClassVar[tuple[AcendaEndpoint, ...]] = (
        AcendaEndpoint(name="new_orders", path="/order", params={"query":{"created_at":{"$gt":None}}}, state_data=("new_orders", "last_created_at"), data_type="new"),
        AcendaEndpoint(name="updated_orders", path="/order", params={"query":{"updated_at":{"$gt":None}}}, state_data=("updated_orders", "last_updated_at"), data_type="update"),
        AcendaEndpoint(name="new_ship_advices", path="/ship_advice", params={"query":{"created_at":{"$gt":None}}}, state_data=("new_ship_advices", "last_created_at"), data_type="new"),
        AcendaEndpoint(name="updated_ship_advices", path="/ship_advice", params={"query":{"updated_at":{"$gt":None}}}, state_data=("updated_ship_advices", "last_updated_at"), data_type="update"),
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
        file_path: Path,
        endpoint: AcendaEndpoint,
    ) -> dict:

        watermark = (cls.get_acenda_watermark(file_path=file_path, endpoint=endpoint))

        if endpoint.name in ["new_orders", "new_ship_advices"]:
                        
            return {
                "query": json.dumps({
                    "created_at": {
                        "$gt": watermark
                    }
                })
            }

        if endpoint.name in ["updated_orders", "updated_ship_advices"]:
                        
            return {
                "query": json.dumps({
                    "updated_at": {
                        "$gt": watermark
                    }
                })
            }

        return {}

    @classmethod
    def get_acenda_watermark(cls, file_path: Path, endpoint: AcendaEndpoint) -> str | None:

        one_day_back = cls.acenda_timestamp_format(datetime.now(timezone.utc) - timedelta(days=1))

        try:
            if not endpoint.state_data:
                raise Exception
            
            state_dict_dt = acenda_state._state[endpoint.state_data[0]][endpoint.state_data[1]]

            if state_dict_dt:
                return state_dict_dt

            with open(file_path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
            watermark = data[endpoint.state_data[0]][endpoint.state_data[1]]
            return watermark
        
        except:
            return one_day_back


    @classmethod
    def acenda_timestamp_format(cls, dt: date | datetime | None) -> str:

        if not dt:
            return (datetime.now(timezone.utc)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if isinstance(dt, datetime):
            return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if isinstance(dt, date):
            dt_comb = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)
            return dt_comb.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @property
    def acenda_base_headers(self) -> dict[str, str]:
        return {
            "X-Astur-Organization": "bokserhome",
        }



__all__ = ["AcendaSettings"]
