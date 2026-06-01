import asyncio

from src.core.config import settings
from src.integrations._base_client.token_cache import token_store
from src.storage.raw.writer import RawPayloadWriter
from src.worker.jobs.get_data.get_acenda_data import (
    GetAcendaData,
    sync_acenda_endpoints_job,
)
from src.worker.jobs.get_data.get_sos_data import GetSosData, sync_sos_endpoints_job


async def sos_main() -> None:
    await token_store.warmup_on_startup()

    sos_data = GetSosData()
    raw_writer = RawPayloadWriter(lake_root=settings.lake_root)

    await sync_sos_endpoints_job(
        sos_data=sos_data,
        raw_writer=raw_writer,
        max_concurrency=6,
    )


async def acenda_main() -> None:
    await token_store.warmup_on_startup()

    acenda_data = GetAcendaData()
    raw_writer = RawPayloadWriter(lake_root=settings.lake_root)

    await sync_acenda_endpoints_job(
        acenda_data=acenda_data,
        raw_writer=raw_writer,
        max_concurrency=20,
    )


if __name__ == "__main__":
    asyncio.run(acenda_main())
