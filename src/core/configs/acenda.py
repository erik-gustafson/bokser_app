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
    payload_type: str
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

    # Sos Customer Name: Sos Customer ID
    acenda_send_to_wms: dict[str, Any] = {
        "Walmart (c)" : 206
    }

    ACENDA_ENDPOINTS: ClassVar[tuple[AcendaEndpoint, ...]] = (
        AcendaEndpoint(name="acenda_orders", path="/order", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_orders", "last_updated_at"), payload_type="order"),
        AcendaEndpoint(name="acenda_ship_advices", path="/ship_advice", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_ship_advices", "last_updated_at"), payload_type="ship_advice"),
        AcendaEndpoint(name="acenda_fulfillments", path="/fulfillment", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_fulfillments", "last_updated_at"), payload_type="fulfillment"),
        AcendaEndpoint(name="acenda_returns", path="/return_extended", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_returns", "last_updated_at"), payload_type="return"),
        AcendaEndpoint(name="acenda_channel_item_status", path="/channel_item_status", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_channel_item_status", "last_updated_at"), payload_type="channel_item_status"),
        AcendaEndpoint(name="acenda_catalog", path="/catalog", params={"query":{"updated_at":{"$gt":None}}}, state_data=("acenda_catalog", "last_updated_at"), payload_type="catalog"),
    )

    ENDPOINT_BY_NAME: ClassVar[dict[str, AcendaEndpoint]] = {
        endpoint.name: endpoint
        for endpoint in ACENDA_ENDPOINTS
    }


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
    def acenda_endpoints_as_dict(cls, name: str) -> AcendaEndpoint:
        try:
            return cls.ENDPOINT_BY_NAME[name]
        except KeyError:
            raise ValueError(f"Invalid Acenda endpoint {name}") from None

    @classmethod
    def acenda_payload_type(cls, name: str):
        try:
            endpoint_dict = cls.acenda_endpoints_as_dict(name)
            return endpoint_dict.payload_type
        except:
            raise ValueError(f"Payload Type not set for {name}")

    @classmethod
    def get_acenda_endpoint_params(
        cls,
        file_path: Path,
        endpoint: AcendaEndpoint,
    ) -> dict[str,str]:

        watermark = (cls.get_acenda_watermark(file_path=file_path, endpoint=endpoint))
                        
        return {
            "query": json.dumps({
                "updated_at": {
                    "$gt": watermark
                }
            })
        }


    @classmethod
    def get_acenda_watermark(cls, file_path: Path, endpoint: AcendaEndpoint) -> str:

        one_day_back = cls.acenda_timestamp_format(datetime.now(timezone.utc) - timedelta(days=1))

        try:
            if not endpoint.state_data:
                raise Exception
            
            state_dict_dt = acenda_state._state[endpoint.state_data[0]][endpoint.state_data[1]]

            if isinstance(state_dict_dt, str) and state_dict_dt.strip():
                return state_dict_dt

            with open(file_path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
            watermark = data[endpoint.state_data[0]][endpoint.state_data[1]]
            if isinstance(watermark, str) and watermark.strip():
                return watermark

            return one_day_back
        
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
