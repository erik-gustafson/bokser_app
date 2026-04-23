from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bokser_app.core.config import settings
from src.bokser_app.integrations.sos_inventory.client import SOSInventoryClient
from src.bokser_app.storage.raw.writer import RawPayloadWriter
from src.bokser_app.worker.jobs.get_data.sos_data import sync_sos_orders_job


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


async def run_worker() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    stop_event = asyncio.Event()

    limits = httpx.Limits(
        max_connections=settings.http_max_connections,
        max_keepalive_connections=settings.http_max_keepalive_connections,
        keepalive_expiry=settings.http_keepalive_expiry_seconds,
    )
    timeout = httpx.Timeout(settings.http_timeout_seconds)

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
    ) as http_client:
        sos_client = SOSInventoryClient(
            client=http_client,
            api_url=settings.sos_api_url,
        )
        raw_writer = RawPayloadWriter(settings.lake_root)

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            sync_sos_orders_job,
            trigger="interval",
            minutes=settings.sos_poll_interval_minutes,
            kwargs={
                "sos_client": sos_client,
                "raw_writer": raw_writer,
            },
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        scheduler.start()

        logger.info(
            "SOS worker started; polling every %s minute(s)",
            settings.sos_poll_interval_minutes,
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        try:
            await stop_event.wait()
        finally:
            scheduler.shutdown(wait=False)
            logger.info("Worker shutdown complete")
