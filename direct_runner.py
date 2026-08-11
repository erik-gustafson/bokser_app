import asyncio
from pathlib import Path
from src.core.config import settings

from src.integrations._base_client.token_cache import token_store

from src.worker.jobs.get_data.base_get import sync_endpoints_job

from src.storage.raw.writer import RawPayloadWriter
from src.storage.states.state_store import warmup_state_files

from src.worker.jobs.get_data.get_acenda_data import GetAcendaData
from src.worker.jobs.get_data.get_sos_data import GetSosData

from src.worker.jobs.push_data.push_to_sos import AcendaOrderPush

LAKE_ROOT = settings.lake_root


async def warmup_tokens() -> None:

    await token_store.warmup_on_startup()


async def sos_main() -> None:

    await sync_endpoints_job(
        target_source_factory=GetSosData,
        raw_writer=RawPayloadWriter(LAKE_ROOT),
        max_concurrency=10,
    )


async def acenda_main() -> None:

    await sync_endpoints_job(
        target_source_factory=GetAcendaData,
        raw_writer=RawPayloadWriter(LAKE_ROOT),
        max_concurrency=10,
    )


if __name__ == "__main__":

    acenda_order_push = AcendaOrderPush()

    asyncio.run(acenda_order_push.send_to_sos())

    # data = get_json_data(
    #     path=Path(r"C:\Users\erik\Code\data_lake\dev\raw\acenda"),
    #     data_type="new_orders",
    # )

    # asyncio.run(warmup_tokens())
    # asyncio.run(warmup_state_files())
    # asyncio.run(acenda_main())
    # asyncio.run(sos_main())
