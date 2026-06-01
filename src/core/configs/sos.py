from __future__ import annotations

from pydantic import Field
from dataclasses import dataclass
from dataclasses import dataclass
from typing import ClassVar
from .base import AppBaseSettings


@dataclass(frozen=True, slots=True)
class SOSEndpoint:
    name: str
    path: str
    entity_name: str
    enabled: bool = True


class SosSettings(AppBaseSettings):
    sos_api_url: str = "https://api.sosinventory.com/api/v2"
    sos_static_token: str = Field(default="dev-token", repr=False)
    sos_token_url: str = "https://api.sosinventory.com/oauth2/token"
    sos_client_id: str = ""
    sos_client_secret: str = ""
    sos_oauth_redirect_uri: str = ""
    sos_authorization_code: str = ""
    sos_token_refresh_skew_seconds: int = 60
    sos_token_timeout_seconds: float = 30.0
    sos_rate_limiter: float = 0.501
    sos_poll_interval_minutes: int = 5

    SOS_ENDPOINTS: ClassVar[tuple[SOSEndpoint, ...]] = (
        SOSEndpoint(
            name="sales_orders", path="/salesorder/", entity_name="sales_order"
        ),
        SOSEndpoint(name="invoices", path="/invoice/", entity_name="invoice"),
        SOSEndpoint(name="shipments", path="/shipment/", entity_name="shipment"),
        SOSEndpoint(name="payments", path="/payment/", entity_name="payment"),
        SOSEndpoint(
            name="purchase_orders",
            path="/purchaseorder/",
            entity_name="purchase_order",
        ),
        SOSEndpoint(
            name="item_receipts",
            path="/itemreceipt/",
            entity_name="item_receipt",
        ),
        SOSEndpoint(name="items", path="/item/", entity_name="item"),
    )

    @classmethod
    def sos_enabled_endpoints(cls) -> tuple[SOSEndpoint, ...]:
        return tuple(endpoint for endpoint in cls.SOS_ENDPOINTS if endpoint.enabled)

    @classmethod
    def sos_paths(cls) -> list[str]:
        return [endpoint.path for endpoint in cls.sos_enabled_endpoints()]

    @classmethod
    def sos_endpoint_names(cls) -> list[str]:
        return [endpoint.name for endpoint in cls.sos_enabled_endpoints()]

    @property
    def sos_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


__all__ = ["SosSettings"]
