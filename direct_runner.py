import asyncio
from src.core.config import settings

from src.storage.raw.writer import RawPayloadWriter
from src.worker.jobs.get_data.sos_data import GetSosData, sync_sos_endpoints_job


async def main() -> None:
    sos_data = GetSosData()
    raw_writer = RawPayloadWriter(lake_root=settings.lake_root)

    await sync_sos_endpoints_job(
        sos_data=sos_data,
        raw_writer=raw_writer,
        max_concurrency=3,
    )


if __name__ == "__main__":
    asyncio.run(main())
