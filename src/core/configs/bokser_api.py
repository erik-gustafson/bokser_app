from __future__ import annotations

from typing import Optional

from .base import AppBaseSettings


class BokserAPISettings(AppBaseSettings):

    ADMIN_TOKEN: Optional[str] = None
    BH_API_KEY: Optional[str] = None

    ROOT_API_PATH: str = "/bokser-api"
    PROJECT_NAME: str = "Bokser API"

    # --- Extensiv IM ---
    IM_API_BASE: str = "https://api.cartrover.com"
    IM_API_KEY: Optional[str] = None

    IM_BH_MERCHANT_USER: Optional[str] = None
    IM_BH_MERCHANT_KEY: Optional[str] = None

    IM_KSP_MERCHANT_USER: Optional[str] = None
    IM_KSP_MERCHANT_KEY: Optional[str] = None

    IM_BH_CART_USER: Optional[str] = None
    IM_BH_CART_KEY: Optional[str] = None

    IM_CART_BH_B2B_USER: Optional[str] = None
    IM_CART_BH_B2B_KEY: Optional[str] = None
    IM_CART_WALMART_B2B_USER: Optional[str] = None
    IM_CART_WALMART_B2B_KEY: Optional[str] = None
    IM_CART_BBB_USER: Optional[str] = None
    IM_CART_BBB_KEY: Optional[str] = None
    IM_CART_WAYFAIR_USER: Optional[str] = None
    IM_CART_WAYFAIR_KEY: Optional[str] = None
    IM_CART_KOHLS_USER: Optional[str] = None
    IM_CART_KOHLS_KEY: Optional[str] = None
    IM_CART_MACYS_USER: Optional[str] = None
    IM_CART_MACYS_KEY: Optional[str] = None
    IM_CART_SHOPIFY_USER: Optional[str] = None
    IM_CART_SHOPIFY_KEY: Optional[str] = None
    IM_CART_TARGET_USER: Optional[str] = None
    IM_CART_TARGET_KEY: Optional[str] = None

    # --- Webhooks (inbound basic auth; currently unused) ---
    WEBHOOK_USER: Optional[str] = None
    WEBHOOK_PASS: Optional[str] = None

    # --- 3PL WMS / Productiv ---
    PRODUCTIV_BASE_URL: Optional[str] = None
    PRODUCTIV_AUTH_USER: str = "cw+bhapi@getproductiv.com"
    PRODUCTIV_AUTH_KEY: Optional[str] = None
    WMS_RSA_PUBLIC_PEM: Optional[str] = None
    WMS_PUBLIC_KEY_URL: Optional[str] = None
    WMS_PUBLIC_KEY_TIMEOUT: float = 5.0

    # --- Carrier APIs ---
    UPS_CLIENT_ID: Optional[str] = None
    UPS_CLIENT_SECRET: Optional[str] = None
    UPS_OAUTH_URL: str = "https://onlinetools.ups.com/security/v1/oauth/token"
    UPS_TRACK_URL: str = "https://onlinetools.ups.com/api/track/v1/details"
    UPS_TRACK_ALERT_SUBSCRIBE_URL: str = (
        "https://onlinetools.ups.com/api/trackalert/v1/subscriptions/track"
    )
    UPS_TRACK_ALERT_DESTINATION_URL: Optional[str] = None
    UPS_TRACK_ALERT_WEBHOOK_TOKEN: Optional[str] = None
    UPS_TRACK_ALERT_LOCALE: str = "en_US"
    UPS_TRACK_ALERT_COUNTRY_CODE: str = "US"

    FEDEX_CLIENT_ID: Optional[str] = None
    FEDEX_CLIENT_SECRET: Optional[str] = None
    FEDEX_OAUTH_URL: str = "https://apis.fedex.com/oauth/token"
    FEDEX_TRACK_URL: str = "https://apis.fedex.com/track/v1/trackingnumbers"
    USPS_CLIENT_ID: Optional[str] = None
    USPS_CLIENT_SECRET: Optional[str] = None
    USPS_OAUTH_URL: str = "https://apis.usps.com/oauth2/v3/token"
    USPS_TRACK_URL: str = "https://apis.usps.com/tracking/v3/tracking"


__all__ = ["BokserAPISettings"]
