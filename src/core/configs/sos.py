from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from pathlib import Path
from pydantic import Field
from dataclasses import dataclass, field
from typing import ClassVar, Any
from .base import AppBaseSettings

from src.storage.states.state_store import sos_state

TIMEZONE_DICT = {"cst": ZoneInfo("America/Chicago"), "utc": ZoneInfo("UTC")}


@dataclass(frozen=True, slots=True)
class SOSEndpoint:
    name: str
    path: str
    payload_type: str
    params: dict[str, Any] = field(default_factory=dict)
    state_data: tuple[str, ...] | None = None
    enabled: bool = True


# fmt: off
class SosSettings(AppBaseSettings):
    sos_api_url: str = "https://api.sosinventory.com/api/v2"
    sos_token_url: str = "https://api.sosinventory.com/oauth2/token"
    sos_client_id: str = ""
    sos_client_secret: str = ""
    sos_oauth_redirect_uri: str = ""
    sos_authorization_code: str = ""
    sos_token_refresh_skew_seconds: int = 60
    sos_token_timeout_seconds: float = 30.0
    sos_rate_limiter: float = .501
    sos_poll_interval_minutes: int = 5
    sos_lake_load_interval_minutes: int = 5

    sos_clt_location_dict: dict[str, Any] = {"id": 1, "name": "Productiv CLT"}
    sos_ksp_location_dict: dict[str, Any] = {"id": 4, "name": "KSP"}

    sos_ready_to_send_order_stage_dict: dict[str, Any] = {"id": 10, "name": "Ready to Send"}
    sos_marketplace_order_stage_dict: dict[str, Any] = {"id": 21, "name": "Marketplace Order"}

    sos_default_terms_dict: dict[str, Any] = {"id": 4, "name": "Net 30"}

    sos_b2b_class_dict: dict[str, Any] = {"id": 1, "name": "B2B"}
    sos_dtc_class_dict: dict[str, Any] = {"id": 2, "name": "DTC"}

    sos_default_exchange_rate: float = 1.0

    sos_uom_ea_dict: dict[str, Any] = {"id": 1, "name": "EA"}
    sos_uom_ca_dict: dict[str, Any] = {"id": 3, "name": "CA"}

    sos_dtc_channel_dict: dict[str, Any] = {"id": 1,"name": "DTC"}
    sos_b2b_channel_dict: dict[str, Any] = {"id": 2,"name": "B2B"}

    sos_item_taxable_dict: dict[str, Any] = {"taxable": True}
    sos_item_non_taxable_dict: dict[str, Any] = {"taxable": False}

    sos_default_so_prefix: str = "SO"
    sos_default_api_prefix: str = "API"
    sos_default_mkt_prefix: str = "MKT"

    SOS_ENDPOINTS: ClassVar[tuple[SOSEndpoint, ...]] = (
        SOSEndpoint(
            name="updated_sales_orders",
            path="/salesorder/",
            state_data=("sales_orders", "updated"),
            payload_type="sales_order"
        ),
        SOSEndpoint(
            name="sales_receipts",
            path="/salesreceipt/",
            state_data=("sales_receipts", "updated"),
            payload_type="sales_receipt"
        ),
        SOSEndpoint(
            name="estimates",
            path="/estimate/",
            state_data=("estimates", "updated"),
            payload_type="estimate"
        ),
        SOSEndpoint(
            name="updated_invoices",
            path="/invoice/",
            state_data=("invoices", "updated"),
            payload_type="invoice"
        ),
        SOSEndpoint(
            name="updated_shipments",
            path="/shipment/",
            state_data=("shipments", "updated"),
            payload_type="shipment"
        ),
        SOSEndpoint(
            name="updated_item_receipts",
            path="/itemreceipt/",
            state_data=("item_receipts", "updated"),
            payload_type="item_receipt"
        ),
        SOSEndpoint(
            name="updated_items",
            path="/item/",
            state_data=("items", "updated"),
            payload_type="item",
        ),
        SOSEndpoint(
            name="payments",
            path="/payment/",
            state_data=("payments", "all"),
            payload_type="payment"
        ),
        SOSEndpoint(
            name="purchase_orders",
            path="/purchaseorder/",
            state_data=("purchase_orders", "updated"),
            payload_type="purchase_order"
        ),
        SOSEndpoint(
            name="adjustments",
            path="/adjustment/",
            state_data=("adjustments", "updated"),
            payload_type="adjustment"
        ),
        SOSEndpoint(
            name="returns",
            path="/return/",
            state_data=("returns", "updated"),
            payload_type="return"
        ),
        SOSEndpoint(
            name="rmas",
            path="/rma/",
            state_data=("rmas", "updated"),
            payload_type="rma"
        ),
    )

    SOS_RECORD_TYPES: ClassVar[dict[str, Any]] = {
        "updated": "last_run_at",
        "created": "last_run_at",
    }

    SOS_ENDPOINT_BY_NAME: ClassVar[dict[str, SOSEndpoint]] = {
        endpoint.name: endpoint
        for endpoint in SOS_ENDPOINTS
    }

    @classmethod
    def get_endpoint(cls, name: str) -> SOSEndpoint:
        try:
            return cls.SOS_ENDPOINT_BY_NAME[name]
        except KeyError:
            valid_names = ", ".join(cls.SOS_ENDPOINT_BY_NAME)
            raise ValueError(
                f"Unknown SOS endpoint {name!r}. "
                f"Valid endpoints: {valid_names}"
            ) from None


# fmt: on
    @classmethod
    def sos_enabled_endpoints(cls) -> tuple[SOSEndpoint, ...]:
        return tuple(endpoint for endpoint in cls.SOS_ENDPOINTS if endpoint.enabled)

    @classmethod
    def sos_paths(cls) -> list[str]:
        return [endpoint.path for endpoint in cls.sos_enabled_endpoints()]

    @classmethod
    def sos_endpoint_names(cls) -> list[str]:
        return [endpoint.name for endpoint in cls.sos_enabled_endpoints()]


    @classmethod
    def sos_endpoints_as_dict(cls, name: str) -> SOSEndpoint:
        try:
            return cls.SOS_ENDPOINT_BY_NAME[name]
        except KeyError:
            raise ValueError(f"Invalid SOS endpoint {name}") from None

    @classmethod
    def sos_payload_type(cls, name: str):
        try:
            endpoint_dict = cls.sos_endpoints_as_dict(name)
            return endpoint_dict.payload_type
        except:
            raise ValueError(f"Payload Type not set for {name}")
        

    @classmethod
    def get_sos_endpoint_params(
        cls,
        file_path: Path,
        endpoint: SOSEndpoint,
    ) -> dict:

        watermark = cls.get_sos_watermark(
            file_path=file_path, endpoint=endpoint
        )

        if endpoint.state_data and endpoint.state_data[1] == "updated":
            return {"updatedsince": watermark}
        
        if endpoint.state_data and endpoint.state_data[1] == "new":
            return {"createdsince": watermark}

        if endpoint.state_data and endpoint.state_data[1] == "all":
            return {"from": watermark}
        
        return {}

    @classmethod
    def get_sos_watermark(
        cls, file_path: Path, endpoint: SOSEndpoint
    ) -> str | None:

        one_day_back = cls.sos_timestamp_format(dt=datetime.now(timezone.utc) - timedelta(days=1), tz="utc")
        try:
            if not endpoint.name:
                raise Exception
            
            state_dict_dt = sos_state._state[endpoint.name]["last_run_at"]

            if state_dict_dt:
                return state_dict_dt

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            watermark = data[endpoint.name]["last_run_at"]
            return watermark

        except:
            return one_day_back


    @classmethod
    def sos_timestamp_format(
        cls,
        dt: date | datetime | None,
        *,
        tz: str | None = None,
        midnight: bool = False,
    ) -> str:

        if not tz:
            tz = "cst"

        zone_info = TIMEZONE_DICT.get(tz)
        
        if dt is None:
            value = datetime.now(zone_info)

        elif isinstance(dt, datetime):
            if dt.tzinfo is None:
                # Treat a naive datetime as Central time.
                value = dt.replace(tzinfo=zone_info)
            else:
                # Convert the actual instant into Central time.
                value = dt.astimezone(zone_info)

        else:
            value = datetime.combine(
                dt,
                time.min,
                tzinfo=zone_info,
            )

        if midnight:
            value = value.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

        return value.replace(tzinfo=None).isoformat(timespec="seconds")

    @property
    def sos_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


__all__ = ["SosSettings"]
