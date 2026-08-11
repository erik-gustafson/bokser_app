import asyncio
import json
from src.core.configs.sos import SOSEndpoint
from src.worker.jobs.get_data.get_sos_data import GetSosData
from src.integrations.sos_client import SOSClient

sos_client = SOSClient()
get_sos_data = GetSosData()

MKT_SOS_NAMES = [
    # "Target.com DTC",
    # "Wayfair LLC DTC",
    # "Website",
    # "MACY'S (DTC)",
    # "KOHL'S DTC",
    "Bed Bath and Beyond DTC",
    "Walmart (c)",
]


import asyncio
from collections.abc import AsyncIterator
from typing import Any

SOS_ENDPOINT = SOSEndpoint(
    name="get_sos_data",
    path="/salesorder/",
)
CUSTOMER = "Target.com DTC"


async def main() -> None:
    _sos_ids = await get_sos_ids()
    sos_ids = sorted(_sos_ids, reverse=True)
    async for status_code, data, message in delete_sos_ids(sos_ids):
        print(status_code, data, message)


async def get_sos_ids() -> list[int]:

    params = {"query": CUSTOMER}

    result = await get_sos_data._get_raw_sos_data_with_open_client(
        endpoint=SOS_ENDPOINT,
        endpoint_params=params,
        archived="any",
        max_concurrency=10,
        max_results=200,
    )

    return list(
        {
            sos_id
            for sos_data in result
            if str(sos_data.get("number", "")).startswith("MKT")
            and (sos_id := sos_data.get("id")) is not None
        }
    )


async def delete_sos_ids(
    ship_ids: list[int],
) -> AsyncIterator[tuple[int, dict[str, list[int]], str]]:
    semaphore = asyncio.Semaphore(10)
    chunk_size = 1

    async def delete_records(
        batch: list[int],
    ) -> tuple[int, dict[str, list[int]], str]:
        data = {"ids": batch}

        async with semaphore:
            try:
                response = await sos_client.delete(
                    path_or_url=f"https://api.sosinventory.com/api/v2{SOS_ENDPOINT.path}batch",
                    json_data=data,
                )
                if 200 <= response.status_code < 300:
                    return response.status_code, data, "Success"

                return response.status_code, data, "Failed"

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                return 500, data, str(exc)

    tasks = [
        asyncio.create_task(delete_records(ship_ids[i : i + chunk_size]))
        for i in range(0, len(ship_ids), chunk_size)
    ]

    for task in asyncio.as_completed(tasks):
        yield await task


if __name__ == "__main__":
    asyncio.run(main())
