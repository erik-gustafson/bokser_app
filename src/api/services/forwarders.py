from __future__ import annotations
import base64
import httpx
import logging
from typing import Any
from src.core.config import settings

logger = logging.getLogger(__name__)


class UpdateExtensivOrder:

    def __init__(self):
        self.im_base_url = settings.IM_API_BASE
        self.im_update_path = "/v1/merchant/orders/update"
        self.im_wms_user = settings.IM_BH_MERCHANT_USER
        self.im_wms_key = settings.IM_BH_MERCHANT_KEY

    def _basic_auth_header(self, user: str, key: str) -> str:
        token = base64.b64encode(f"{user}:{key}".encode()).decode()
        return f"Basic {token}"

    def _status(
        self,
        cust_ref: Any | None = None,
        status: str | None = None,
        ship_data: list[dict[str, Any]] | None = None,
    ):

        if not self.im_wms_user or not self.im_wms_key:
            raise ValueError("Missing IM_WMS_USER/IM_WMS_KEY in settings")

        if not (ship_data or (cust_ref and status)):
            raise ValueError("Missing required data")

        payload = (
            ship_data if ship_data else {"cust_ref": cust_ref, "order_status": status}
        )

        headers = {
            "Authorization": self._basic_auth_header(self.im_wms_user, self.im_wms_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = httpx.post(
            f"{settings.IM_API_BASE}{self.im_update_path}",
            headers=headers,
            json=payload,
        )

        return response.json()
