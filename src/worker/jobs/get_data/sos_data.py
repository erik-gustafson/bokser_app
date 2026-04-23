from __future__ import annotations

import logging
from typing import Any

from src.bokser_app.integrations.sos_inventory.client import SOSInventoryClient
from src.bokser_app.storage.raw.writer import RawPayloadWriter

logger = logging.getLogger(__name__)


async def sync_sos_orders_job(
    *,
    sos_client: SOSInventoryClient,
    raw_writer: RawPayloadWriter,
) -> None:
    orders: list[dict[str, Any]] = await sos_client.fetch_sales_orders()

    result = raw_writer.write_json_payload(
        source_system="sos_inventory",
        entity_name="sales_order",
        payload=orders,
    )

    logger.info(
        "Fetched %s SOS sales orders and wrote raw file to %s",
        result.record_count,
        result.file_path,
    )
