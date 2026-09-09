"""Shared shipment ingestion rules; completed or uncertain posts are never replayed."""

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.postgresql.dml import Insert

from src.database.models.sos_models import SosShipmentSync


def shipment_sync_upsert(source: str, source_id: str, payload_hash: str) -> Insert:
    stmt = insert(SosShipmentSync).values(
        source=source, source_id=source_id, payload_hash=payload_hash, status="pending"
    )
    held = SosShipmentSync.status.in_(("sent", "processing", "reconcile"))
    return stmt.on_conflict_do_update(
        constraint="ux_sos_shipment_sync_source_key",
        set_={
            "payload_hash": payload_hash,
            "status": case((held, "reconcile"), else_=SosShipmentSync.status),
            "last_error": case(
                (
                    held,
                    "Source payload changed after shipment processing; reconcile against SOS",
                ),
                else_=SosShipmentSync.last_error,
            ),
        },
        where=SosShipmentSync.payload_hash.is_distinct_from(payload_hash),
    )
