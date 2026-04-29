from __future__ import annotations

from typing import Optional

from .base import AppBaseSettings


class ProductivSettings(AppBaseSettings):

    productiv_api_url: str = "https://secure-wms.com/"
    productiv_token_url: str = "https://secure-wms.com/AuthServer/api/Token"
    productiv_auth_user: str = "cw+bhapi@getproductiv.com"
    productiv_auth_key: Optional[str] = None
    productiv_rate_limiter: float = 0.501
    # WMS_RSA_PUBLIC_PEM: Optional[str] = None
    # WMS_PUBLIC_KEY_URL: Optional[str] = None
    # WMS_PUBLIC_KEY_TIMEOUT: float = 5.0

    @property
    def productiv_base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


__all__ = ["ProductivSettings"]
