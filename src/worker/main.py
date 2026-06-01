from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import dataclass

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.integrations._base_client.token_cache import token_store
from src.integrations.sos_client import SOSClient
from src.storage.raw.writer import RawPayloadWriter
from src.worker.jobs.get_data.get_sos_data import GetSosData, sync_sos_endpoints_job


@dataclass(frozen=True)
class WorkerRuntime:
    sos_data: GetSosData
    raw_writer: RawPayloadWriter


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


def build_runtime(http_client: httpx.AsyncClient) -> WorkerRuntime:
    sos_client = SOSClient(
        client=http_client,
    )
    sos_data = GetSosData(sos_client=sos_client)
    raw_writer = RawPayloadWriter(settings.lake_root)
    return WorkerRuntime(
        sos_data=sos_data,
        raw_writer=raw_writer,
    )


def register_jobs(scheduler: AsyncIOScheduler, runtime: WorkerRuntime) -> None:
    scheduler.add_job(
        sync_sos_endpoints_job,
        trigger="interval",
        minutes=settings.sos_poll_interval_minutes,
        kwargs={
            "sos_data": runtime.sos_data,
            "raw_writer": runtime.raw_writer,
            "max_concurrency": 3,
        },
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )


def build_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone="UTC")


async def run_worker() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    await token_store.warmup_on_startup()

    stop_event = asyncio.Event()
    async with build_http_client() as http_client:
        runtime = build_runtime(http_client)
        scheduler = build_scheduler()
        register_jobs(scheduler, runtime)
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
