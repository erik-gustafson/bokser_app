import base64
import logging
import hmac
import asyncio
import httpx
from typing import Optional, Tuple
from hashlib import sha256
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.core.config import settings

logger = logging.getLogger(__name__)

# IM Merchant Creds
IM_BH_MERCHANT_USER = settings.IM_BH_MERCHANT_USER
IM_BH_MERCHANT_KEY = settings.IM_BH_MERCHANT_KEY


def verify_basic_auth(authorization: str | None) -> bool:

    logger.info("Basic Auth Started")

    if not authorization or not authorization.startswith("Basic "):
        logger.error("No Authorization Header")
        return False
    try:
        token = authorization.split(" ", 1)[1].strip()
        userpass = base64.b64decode(token).decode()
        user, pwd = userpass.split(":", 1)
        logger.info("Basic Authorization Pass")
        return user == IM_BH_MERCHANT_USER and pwd == IM_BH_MERCHANT_KEY
    except Exception:
        logger.error("Basic Authorization Exception")
        return False


def verify_im_signature(
    raw: bytes, received_signature: str | None
) -> Tuple[bool, str | None]:
    """
    Verifies an incoming IM webhook signature using either the KSP or BH secret.
    Returns True if the signature matches one of them.
    """
    if not received_signature:
        logger.error("No Signature Received")
        return False, None

    candidate_secrets: tuple[tuple[str, str | None], ...] = (
        ("bh_merchant", settings.IM_BH_MERCHANT_KEY),
        ("bh_cart", settings.IM_BH_CART_KEY),
        ("ksp_merchant", settings.IM_KSP_MERCHANT_KEY),
        ("ksp_b2b_cart", settings.IM_CART_BH_B2B_KEY),
        ("ksp_walmart_cart", settings.IM_CART_WALMART_B2B_KEY),
        ("ksp_bbb_cart", settings.IM_CART_BBB_KEY),
        ("ksp_wayfair_cart", settings.IM_CART_WAYFAIR_KEY),
        ("ksp_kohls_cart", settings.IM_CART_KOHLS_KEY),
        ("ksp_macys_cart", settings.IM_CART_MACYS_KEY),
        ("ksp_shopify_cart", settings.IM_CART_SHOPIFY_KEY),
        ("ksp_target_cart", settings.IM_CART_TARGET_KEY),
    )

    configured_secrets: tuple[tuple[str, str], ...] = tuple(
        (source_name, secret)
        for source_name, secret in candidate_secrets
        if isinstance(secret, str) and secret.strip()
    )
    if not configured_secrets:
        logger.error("No signing secrets configured")
        return False, None

    received_signature_value = received_signature.strip().lower()

    def _compute_signature(secret: str) -> str:
        return hmac.new(secret.encode(), raw, sha256).hexdigest().lower()

    def _matches_signature(secret: str) -> bool:
        return hmac.compare_digest(_compute_signature(secret), received_signature_value)

    for source_name, secret in configured_secrets:
        if _matches_signature(secret):
            logger.info("Signature verified using %s secret", source_name)
            return True, source_name

    logger.warning("Signature verification failed for all configured secrets")
    return False, None


class WMSKeyVerifier:
    """
    Verifies RSA-PKCS1v1.5 + SHA256 signatures on raw bodies.
    - Caches public key in-memory
    - Refreshes on demand and on verify-fail (handles key rotation)
    - Async/await friendly
    """

    def __init__(self):
        self._key_url = settings.WMS_PUBLIC_KEY_URL
        self._timeout = settings.WMS_PUBLIC_KEY_TIMEOUT
        self._cached_key: Optional[rsa.RSAPublicKey] = None
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def warm(self) -> None:
        """Fetch and cache the key at startup."""
        await self._refresh_public_key()

    async def _fetch_public_key(self) -> rsa.RSAPublicKey:
        if not self._key_url:
            raise ValueError("Missing _key_url in settings")
        response = await self._client.get(self._key_url)
        response.raise_for_status()
        response_payload = response.json()
        pem = response_payload["publicKey"]  # PEM/SPKI per spec
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("Retrieved key is not RSA")
        return key

    async def _refresh_public_key(self) -> None:
        new_key = await self._fetch_public_key()
        self._cached_key = new_key

    async def _get_public_key(self) -> rsa.RSAPublicKey:
        if self._cached_key is None:
            async with self._lock:
                if self._cached_key is None:
                    await self._refresh_public_key()
        # mypy: assert non-None
        assert self._cached_key is not None
        return self._cached_key

    @staticmethod
    def _b64strict(signature_value: str) -> bytes:
        # Signature is base64 per spec; use strict decoder
        return base64.b64decode(signature_value, validate=True)

    async def verify(self, *, raw: bytes, signature_b64: Optional[str]) -> bool:
        """Verify once, refresh-on-fail, and retry once."""
        if not signature_b64:
            return False

        try:
            signature_bytes = self._b64strict(signature_b64)
        except Exception:
            return False

        # first attempt with cached key
        try:
            key = await self._get_public_key()
            key.verify(signature_bytes, raw, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            # refresh & retry once
            try:
                async with self._lock:
                    await self._refresh_public_key()
                    key = await self._get_public_key()
                key.verify(signature_bytes, raw, padding.PKCS1v15(), hashes.SHA256())
                return True
            except Exception:
                return False
