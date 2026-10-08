from typing import Literal

from pydantic import Field, SecretStr
from .base import AppBaseSettings


class AmazonSettings(AppBaseSettings):
    amazon_environment: Literal["sandbox", "production"] = "sandbox"
    amazon_enabled: bool = False
    amazon_owner: Literal["bokser", "channelengine"] = "bokser"
    amazon_writes_enabled: bool = False
    amazon_seller_id: str = ""
    amazon_marketplace_id: Literal["ATVPDKIKX0DER"] = "ATVPDKIKX0DER"
    amazon_lwa_client_id: str = ""
    amazon_lwa_client_secret: SecretStr = SecretStr("")
    amazon_lwa_refresh_token: SecretStr = SecretStr("")
    amazon_inventory_interval_minutes: int = Field(default=15, ge=1)
    # Must be chosen at launch; publication refuses to calculate without it.
    amazon_stock_max_age_minutes: int | None = Field(default=None, ge=1)
    amazon_inventory_buffer: int = Field(default=0, ge=0)
    amazon_inventory_cap: int | None = Field(default=None, ge=0)
    amazon_search_min_interval_seconds: float = Field(default=180, gt=0)
    amazon_shipment_min_interval_seconds: float = Field(default=0.5, gt=0)
    amazon_inventory_min_interval_seconds: float = Field(default=0.2, gt=0)
    amazon_http_timeout_seconds: float = Field(default=30, gt=0)

    def require_active(self, *, write: bool = False) -> None:
        if not self.amazon_enabled or self.amazon_owner != "bokser":
            raise ValueError("Amazon connector is disabled or owned by another integration")
        if write and not self.amazon_writes_enabled:
            raise ValueError("Amazon writes are disabled")
        if not all((self.amazon_seller_id, self.amazon_lwa_client_id,
                    self.amazon_lwa_client_secret.get_secret_value(),
                    self.amazon_lwa_refresh_token.get_secret_value())):
            raise ValueError("Amazon credentials and seller ID are required")
