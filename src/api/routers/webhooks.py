# app/routers/im_webhook.py
from __future__ import annotations

import json
import logging
import secrets

from typing import Any, Dict

from fastapi import FastAPI, APIRouter, Request, HTTPException, status, Header, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.database import get_async_db
from src.api.services.validators import verify_im_signature, WMSKeyVerifier
from src.api.services.forwarders import UpdateExtensivOrder
from src.database.models import BokserAPIWebhookEvent
from src.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()
UPS_TRACK_ALERT_EVENT_TYPE = "ups_track_alert"
UPS_TRACK_ALERT_SOURCE = "ups_track_alert"


@router.post("/im-webhooks/im-webhook", status_code=status.HTTP_200_OK)
async def im_webhook_new(
    *,
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    x_webhook_event: str | None = Header(default=None, alias="X-Webhook-Event"),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:

    last_external_id: str | None = None
    signature_valid = False
    source: str | None = None

    raw_body = await request.body()

    if not x_webhook_signature:
        logger.exception("Missing Signature")
        raise HTTPException(status_code=400, detail="Missing Signature")

    try:
        # Uses key to return source of request
        signature_valid, source = verify_im_signature(raw_body, x_webhook_signature)
    except Exception as exc:
        logger.exception("Signature verify error: %s", exc)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event_type_str = str(x_webhook_event or "unknown").strip() or "unknown"

    # Log the webhook event
    db.add(
        BokserAPIWebhookEvent(
            source="ksp",
            event_type=event_type_str,
            signature_valid=bool(signature_valid),
            payload=payload or {},
        )
    )

    await db.commit()

    if not signature_valid:
        raise HTTPException(status_code=401, detail="Invalid signature")

    if not source:
        raise HTTPException(
            status_code=500,
            detail="Unable to determine webhook source",
        )

    return {"ok": True}


#### ---- PRODUCTIV ---- ####


# --- Verifier dependency wiring --- #
def _get_verifier(app: FastAPI) -> WMSKeyVerifier:
    return app.state.wms_verifier


async def verifier_dep(request: Request) -> WMSKeyVerifier:
    return _get_verifier(request.app)


@router.post("/productiv-webhooks/productiv-webhook", status_code=status.HTTP_200_OK)
async def productiv_webhook(
    *,
    request: Request,
    signature: str | None = Header(None, alias="Signature"),
    db: AsyncSession = Depends(get_async_db),
    verifier: WMSKeyVerifier = Depends(verifier_dep),
) -> Dict[str, Any]:

    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")

    except json.JSONDecodeError:
        db.add(
            BokserAPIWebhookEvent(
                source="productiv",
                event_type="unknown",
                signature_valid=False,
                payload={"_parse_error": "invalid json"},
            )
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # ——— Verify signature against RAW body ——— #
    signature_valid = False
    try:
        signature_valid = await verifier.verify(raw=raw_body, signature_b64=signature)
    except Exception as exc:
        logger.exception("Signature verify error (productiv): %s", exc)

    event_type = payload.get("eventType") if isinstance(payload, dict) else "unknown"
    event_type_str = str(event_type or "unknown")

    # --- Always log the webhook event (audit trail) --- #
    db.add(
        BokserAPIWebhookEvent(
            source="productiv",
            event_type=event_type_str,
            signature_valid=bool(signature_valid),
            payload=(
                payload
                if isinstance(payload, (dict, list))
                else {"_raw_type": type(payload).__name__}
            ),
        )
    )
    await db.commit()  # commit audit log regardless

    if not signature_valid:
        # Stop here after logging audit entry
        raise HTTPException(status_code=401, detail="Invalid signature")

    external_id = _extract_external_id_from_productiv(payload)
    if not external_id:
        raise HTTPException(status_code=400, detail="Missing externalId in payload")

    await db.commit()

    return {"ok": True}


#### ---- UPS Webhooks ---- ####


@router.post("/ups-webhooks/track-alert", status_code=status.HTTP_200_OK)
async def ups_track_alert_webhook(
    *,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        db.add(
            BokserAPIWebhookEvent(
                source=UPS_TRACK_ALERT_SOURCE,
                event_type=UPS_TRACK_ALERT_EVENT_TYPE,
                signature_valid=False,
                payload={"_parse_error": "invalid json"},
            )
        )
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid JSON")

    auth_valid = False
    auth_error: HTTPException | None = None
    try:
        auth_valid = _verify_ups_track_alert_bearer(authorization)
    except HTTPException as exc:
        auth_error = exc

    audit_payload = (
        payload
        if isinstance(payload, (dict, list))
        else {"_raw_type": type(payload).__name__}
    )
    db.add(
        BokserAPIWebhookEvent(
            source=UPS_TRACK_ALERT_SOURCE,
            event_type=UPS_TRACK_ALERT_EVENT_TYPE,
            signature_valid=auth_valid,
            payload=audit_payload,
        )
    )

    await db.commit()

    if auth_error:
        raise auth_error

    if not auth_valid:
        raise HTTPException(status_code=401, detail="Invalid authorization")

    return {"ok": True}


# ---------- Helpers ---------- #


def _extract_external_id_from_productiv(payload: Any) -> str | None:
    """
    Try to pull a meaningful external identifier from Productiv webhooks.
    - Primary: body.externalId or top-level externalId
    - Fallbacks: receiverId (for ReceiverConfirm) or data.ReceiverId if provided as JSON string
    """
    if not isinstance(payload, dict):
        return None

    body = payload.get("resource", {}).get("body", {}) or {}

    external_id = body.get("externalId")  # Order Shipments

    if not external_id:
        external_id = body.get("readOnly", {}).get("receiverId")  # Receivers

    if not external_id:
        # Fallback to use embeded JSON string in "data" with ReceiverId or OrderId
        data_field = payload.get("data")
        if isinstance(data_field, str):
            try:
                data_obj = json.loads(data_field)
                external_id = data_obj.get("OrderId") or data_obj.get("ReceiverId")
            except Exception:
                external_id = None

    if external_id is None:
        return None

    external_id_str = str(external_id).strip()
    return external_id_str or None


def _verify_ups_track_alert_bearer(authorization: str | None) -> bool:
    expected_token = str(settings.UPS_TRACK_ALERT_WEBHOOK_TOKEN or "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="UPS track alert webhook token not configured",
        )

    auth_header = str(authorization or "").strip()
    if not auth_header:
        return False

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return False

    candidate_token = token.strip()
    if not candidate_token:
        return False
    return secrets.compare_digest(candidate_token, expected_token)
