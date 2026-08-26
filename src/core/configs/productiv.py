from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, ClassVar, Tuple, Optional
from pathlib import Path


from .base import AppBaseSettings


@dataclass(frozen=True, slots=True)
class ProductivEndpoint:
    name: str
    path: str
    data_type: str
    params: dict[str, Any] = field(default_factory=dict)
    state_data: Tuple[str, ...] | None = None
    enabled: bool = True


class ProductivSettings(AppBaseSettings):

    productiv_api_url: str = "https://secure-wms.com"
    productiv_token_url: str = "https://secure-wms.com/AuthServer/api/Token"
    productiv_auth_user: str = "cw+bhapi@getproductiv.com"
    productiv_auth_key: Optional[str] = None
    productiv_rate_limiter: float = 0.501
    # WMS_RSA_PUBLIC_PEM: Optional[str] = None
    # WMS_PUBLIC_KEY_URL: Optional[str] = None
    # WMS_PUBLIC_KEY_TIMEOUT: float = 5.0

    ####

    PRODUCTIV_ENDPOINTS: ClassVar[tuple[ProductivEndpoint, ...]] = (
        ProductivEndpoint(
            name="stock_summaries",
            path="/inventory/stocksummaries",
            params={"query": {"updated_at": {"$gt": None}}},
            state_data=("acenda_orders", "last_updated_at"),
            data_type="update",
        ),
    )

    # fmt: on
    @classmethod
    def productiv_enabled_endpoints(cls) -> tuple[ProductivEndpoint, ...]:
        return tuple(
            endpoint for endpoint in cls.PRODUCTIV_ENDPOINTS if endpoint.enabled
        )

    @classmethod
    def productiv_paths(cls) -> list[str]:
        return [endpoint.path for endpoint in cls.productiv_enabled_endpoints()]

    @classmethod
    def productiv_endpoint_names(cls) -> list[str]:
        return [endpoint.name for endpoint in cls.productiv_enabled_endpoints()]

    @classmethod
    def get_productiv_endpoint_params(
        cls,
        endpoint: ProductivEndpoint,
    ) -> dict:

        # watermark = (cls.get_productiv_cursor(file_path=file_path, endpoint=endpoint))
        ### Use DB table

        # if endpoint.data_type == "new":

        #     return {"query": json.dumps({"created_at": {"$gt": watermark}})}

        # if endpoint.data_type == "update":

        #     return {"query": json.dumps({"updated_at": {"$gt": watermark}})}

        return {}

    # @classmethod
    # ### Pull from Datalake DB Table
    # def get_productiv_cursor(cls, file_path: Path, endpoint: ProductivEndpoint) -> str:

    #     one_day_back = cls.acenda_timestamp_format(
    #         datetime.now(timezone.utc) - timedelta(days=1)
    #     )

    # try:
    #     if not endpoint.state_data:
    #         raise Exception

    #     state_dict_dt = acenda_state._state[endpoint.state_data[0]][endpoint.state_data[1]]

    #     if isinstance(state_dict_dt, str) and state_dict_dt.strip():
    #         return state_dict_dt

    #     with open(file_path, "r", encoding="utf-8") as f:
    #         data: dict = json.load(f)
    #     watermark = data[endpoint.state_data[0]][endpoint.state_data[1]]
    #     if isinstance(watermark, str) and watermark.strip():
    #         return watermark

    #     return one_day_back

    # except:
    #     return one_day_back

    @classmethod
    def acenda_timestamp_format(cls, dt: date | datetime | None) -> str:

        if not dt:
            return (
                (datetime.now(timezone.utc))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
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

    ####
    @property
    def productiv_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


__all__ = ["ProductivSettings"]
