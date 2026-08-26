from __future__ import annotations

import unittest

import direct_runner
from src.api import old_main as api_main
from src.worker import main as worker_main


class _WarmupSpy:
    def __init__(self) -> None:
        self.calls = 0

    async def warmup_on_startup(self) -> None:
        self.calls += 1


class _FakeHttpClientContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_: object) -> None:
        return None


class _FakeStopEvent:
    async def wait(self) -> None:
        return None

    def set(self) -> None:
        return None


class _FakeLoop:
    def add_signal_handler(self, *_: object) -> None:
        return None


class _FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.shutdown_called = False

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool) -> None:
        _ = wait
        self.shutdown_called = True


class StartupWarmupTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_run_warms_tokens_once(self) -> None:
        warmup = _WarmupSpy()
        scheduler = _FakeScheduler()

        original_token_store = worker_main.token_store
        original_configure_logging = worker_main.configure_logging
        original_event = worker_main.asyncio.Event
        original_loop_getter = worker_main.asyncio.get_running_loop
        original_build_http_client = worker_main.build_http_client
        original_build_runtime = worker_main.build_runtime
        original_build_scheduler = worker_main.build_scheduler
        original_register_jobs = worker_main.register_jobs

        worker_main.token_store = warmup  # type: ignore[assignment]
        worker_main.configure_logging = lambda: None  # type: ignore[assignment]
        worker_main.asyncio.Event = lambda: _FakeStopEvent()  # type: ignore[assignment]
        worker_main.asyncio.get_running_loop = lambda: _FakeLoop()  # type: ignore[assignment]
        worker_main.build_http_client = lambda: _FakeHttpClientContext()  # type: ignore[assignment]
        worker_main.build_runtime = lambda http_client: object()  # type: ignore[assignment]
        worker_main.build_scheduler = lambda: scheduler  # type: ignore[assignment]
        worker_main.register_jobs = lambda scheduler, runtime: None  # type: ignore[assignment]

        try:
            await worker_main.run_worker()
        finally:
            worker_main.token_store = original_token_store  # type: ignore[assignment]
            worker_main.configure_logging = original_configure_logging  # type: ignore[assignment]
            worker_main.asyncio.Event = original_event  # type: ignore[assignment]
            worker_main.asyncio.get_running_loop = original_loop_getter  # type: ignore[assignment]
            worker_main.build_http_client = original_build_http_client  # type: ignore[assignment]
            worker_main.build_runtime = original_build_runtime  # type: ignore[assignment]
            worker_main.build_scheduler = original_build_scheduler  # type: ignore[assignment]
            worker_main.register_jobs = original_register_jobs  # type: ignore[assignment]

        self.assertEqual(warmup.calls, 1)
        self.assertTrue(scheduler.started)
        self.assertTrue(scheduler.shutdown_called)

    async def test_api_lifespan_warms_tokens_once(self) -> None:
        warmup = _WarmupSpy()
        original_token_store = api_main.token_store
        api_main.token_store = warmup  # type: ignore[assignment]

        try:
            async with api_main.lifespan(api_main.app):
                pass
        finally:
            api_main.token_store = original_token_store  # type: ignore[assignment]

        self.assertEqual(warmup.calls, 1)

    async def test_direct_runner_sos_warms_tokens_once(self) -> None:
        warmup = _WarmupSpy()
        calls = {"sync": 0}

        original_token_store = direct_runner.token_store
        original_get_sos = direct_runner.GetSosData
        original_writer = direct_runner.RawPayloadWriter
        original_sync_job = direct_runner.sync_sos_endpoints_job

        async def _sync_job(**kwargs) -> None:
            _ = kwargs
            calls["sync"] += 1

        direct_runner.token_store = warmup  # type: ignore[assignment]
        direct_runner.GetSosData = lambda: object()  # type: ignore[assignment]
        direct_runner.RawPayloadWriter = lambda lake_root: object()  # type: ignore[assignment]
        direct_runner.sync_sos_endpoints_job = _sync_job  # type: ignore[assignment]

        try:
            await direct_runner.sos_main()
        finally:
            direct_runner.token_store = original_token_store  # type: ignore[assignment]
            direct_runner.GetSosData = original_get_sos  # type: ignore[assignment]
            direct_runner.RawPayloadWriter = original_writer  # type: ignore[assignment]
            direct_runner.sync_sos_endpoints_job = original_sync_job  # type: ignore[assignment]

        self.assertEqual(warmup.calls, 1)
        self.assertEqual(calls["sync"], 1)

    async def test_direct_runner_acenda_warms_tokens_once(self) -> None:
        warmup = _WarmupSpy()
        calls = {"sync": 0}

        original_token_store = direct_runner.token_store
        original_get_acenda = direct_runner.GetAcendaData
        original_writer = direct_runner.RawPayloadWriter
        original_sync_job = direct_runner.sync_acenda_endpoints_job

        async def _sync_job(**kwargs) -> None:
            _ = kwargs
            calls["sync"] += 1

        direct_runner.token_store = warmup  # type: ignore[assignment]
        direct_runner.GetAcendaData = lambda: object()  # type: ignore[assignment]
        direct_runner.RawPayloadWriter = lambda lake_root: object()  # type: ignore[assignment]
        direct_runner.sync_acenda_endpoints_job = _sync_job  # type: ignore[assignment]

        try:
            await direct_runner.acenda_main()
        finally:
            direct_runner.token_store = original_token_store  # type: ignore[assignment]
            direct_runner.GetAcendaData = original_get_acenda  # type: ignore[assignment]
            direct_runner.RawPayloadWriter = original_writer  # type: ignore[assignment]
            direct_runner.sync_acenda_endpoints_job = original_sync_job  # type: ignore[assignment]

        self.assertEqual(warmup.calls, 1)
        self.assertEqual(calls["sync"], 1)


if __name__ == "__main__":
    unittest.main()
