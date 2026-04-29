from __future__ import annotations

import unittest

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.integrations.sos_inventory.client import SOSInventoryClient
from src.worker.jobs.get_data.sos_data import sync_sos_orders_job
from src.worker.main import (
    WorkerRuntime,
    build_http_client,
    build_token_http_client,
    register_jobs,
)


class WorkerMainRuntimeTests(unittest.TestCase):
    def test_register_jobs_wires_runtime_dependencies(self) -> None:
        sos_client = object()
        raw_writer = object()
        runtime = WorkerRuntime(
            sos_client=sos_client,  # type: ignore[arg-type]
            raw_writer=raw_writer,  # type: ignore[arg-type]
        )
        scheduler = AsyncIOScheduler(timezone="UTC")

        register_jobs(scheduler, runtime)
        jobs = scheduler.get_jobs()

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertIs(job.func, sync_sos_orders_job)
        self.assertEqual(job.trigger.__class__.__name__, "IntervalTrigger")
        self.assertEqual(job.kwargs["sos_client"], sos_client)
        self.assertEqual(job.kwargs["raw_writer"], raw_writer)
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)
        self.assertEqual(job.misfire_grace_time, 60)


class WorkerClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_off_client_context_closes_underlying_httpx_client(self) -> None:
        async with SOSInventoryClient.one_off(api_url="https://api.example.com") as client:
            underlying_client = client._client  # noqa: SLF001
            self.assertFalse(underlying_client.is_closed)
        self.assertTrue(underlying_client.is_closed)

    async def test_worker_api_and_token_clients_are_distinct(self) -> None:
        api_client = build_http_client()
        token_client = build_token_http_client()
        try:
            self.assertIsNot(api_client, token_client)
            self.assertIsNotNone(api_client._auth)  # noqa: SLF001
            self.assertIsNone(token_client._auth)  # noqa: SLF001
        finally:
            await api_client.aclose()
            await token_client.aclose()
