from __future__ import annotations

import asyncio
import logging
import signal
import httpx

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.utils.logger import setup_logging
from src.integrations._base_client.token_cache import token_store
from src.integrations.sos_client import SOSClient
from src.integrations.acenda_client import AcendaClient
from src.storage.raw.writer import RawPayloadWriter
from src.worker.jobs.get_data.get_sos_data import GetSosData
from src.worker.jobs.get_data.get_acenda_data import GetAcendaData
from src.worker.jobs.get_data.base_get import sync_endpoints_job
from src.worker.jobs.get_data.gmail.get_gmail_data import gmail_tasks
from src.worker.jobs.process_data.sutton.process_sutton_reporting import (
    sutton_report_tasks,
)
from src.worker.jobs.process_data.acenda.process_acenda_data import acenda_load_to_db
from src.worker.jobs.process_data.sos.process_sos_data import sos_load_to_db
from src.storage.states.state_store import warmup_state_files


@dataclass(frozen=True)
class WorkerRuntime:
    sos_data_factory: Callable[[], GetSosData]
    acenda_data_factory: Callable[[], GetAcendaData]
    raw_writer: RawPayloadWriter


def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


def build_runtime(http_client: httpx.AsyncClient) -> WorkerRuntime:
    sos_client = SOSClient(client=http_client)
    acenda_client = AcendaClient(client=http_client)
    raw_writer = RawPayloadWriter(settings.lake_root)

    return WorkerRuntime(
        sos_data_factory=lambda: GetSosData(sos_client=sos_client),
        acenda_data_factory=lambda: GetAcendaData(acenda_client=acenda_client),
        raw_writer=raw_writer,
    )


def register_jobs(scheduler: AsyncIOScheduler, runtime: WorkerRuntime) -> None:

    scheduler.add_job(
        sos_load_to_db,
        "interval",
        minutes=settings.sos_lake_load_interval_minutes,
        id="load_sos_lake_files_to_db",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        sync_endpoints_job,
        trigger="interval",
        minutes=settings.sos_poll_interval_minutes,
        kwargs={
            "target_source_factory": runtime.sos_data_factory,
            "raw_writer": runtime.raw_writer,
            "max_concurrency": 15,
        },
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        sync_endpoints_job,
        trigger="interval",
        minutes=settings.acenda_poll_interval_minutes,
        kwargs={
            "target_source_factory": runtime.acenda_data_factory,
            "raw_writer": runtime.raw_writer,
            "max_concurrency": 50,
        },
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        acenda_load_to_db,
        "interval",
        minutes=settings.acenda_lake_load_interval_minutes,
        id="load_acenda_lake_files_to_db",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        gmail_tasks.sutton_report_download,
        "interval",
        minutes=1,
        id="download_sutton_reports",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        sutton_report_tasks.process_sutton_reports,
        "interval",
        minutes=1,
        id="load_sutton_lake_files_to_db",
        max_instances=1,
        coalesce=True,
    )


def build_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone="UTC")


async def run_worker() -> None:

    setup_logging(settings.log_level)
    logger = logging.getLogger("worker")

    await token_store.warmup_on_startup()

    await warmup_state_files()

    stop_event = asyncio.Event()
    async with build_http_client() as http_client:
        runtime = build_runtime(http_client)
        scheduler = build_scheduler()
        register_jobs(scheduler, runtime)
        scheduler.start()

        logger.info("Worker started sucessfully")
        logger.info("=" * 60)
        logger.info("SCHEDULED JOBS:")
        logger.info("=" * 60)
        for job in scheduler.get_jobs():
            logger.info(f"  • {job.name}")
            logger.info(f"    ID: {job.id}")
            logger.info(f"    Next run: {job.next_run_time}")
            logger.info(f"    Trigger: {job.trigger}")
            logger.info("-" * 60)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        try:
            await stop_event.wait()
        finally:
            scheduler.shutdown(wait=False)
            logger.info("Worker shutdown complete")
