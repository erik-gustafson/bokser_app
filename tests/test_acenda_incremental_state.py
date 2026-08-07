from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.core.configs.acenda import AcendaEndpoint, AcendaSettings
from src.worker.jobs.get_data.get_acenda_data import GetAcendaData


UPDATED_ORDERS = AcendaEndpoint(
    name="updated_orders",
    path="/order",
    params={},
    state_data=("updated_orders", "last_updated_at"),
    data_type="update",
)


class AcendaIncrementalStateTests(unittest.IsolatedAsyncioTestCase):
    def test_null_file_watermark_uses_one_day_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "acenda_query_state.json"
            state_file.write_text(
                json.dumps({"updated_orders": {"last_updated_at": None}}),
                encoding="utf-8",
            )

            with patch(
                "src.core.configs.acenda.acenda_state._state",
                {"updated_orders": {"last_updated_at": None}},
            ):
                params = AcendaSettings.get_acenda_endpoint_params(
                    state_file,
                    UPDATED_ORDERS,
                )

        query = json.loads(params["query"])
        self.assertIsInstance(query["updated_at"]["$gt"], str)
        self.assertTrue(query["updated_at"]["$gt"])

    async def test_empty_result_does_not_replace_existing_watermark(self) -> None:
        getter = GetAcendaData(acenda_client=AsyncMock())

        with patch(
            "src.worker.jobs.get_data.get_acenda_data.acenda_state.update",
            new_callable=AsyncMock,
        ) as update:
            await getter.update_state_file("updated_orders", [])

        update.assert_not_awaited()

    async def test_nonempty_result_updates_watermark(self) -> None:
        getter = GetAcendaData(acenda_client=AsyncMock())

        with patch(
            "src.worker.jobs.get_data.get_acenda_data.acenda_state.update",
            new_callable=AsyncMock,
        ) as update:
            await getter.update_state_file(
                "updated_orders",
                [{"updated_at": "2026-08-07T03:03:31.000Z"}],
            )

        update.assert_awaited_once_with(
            {
                "updated_orders": {
                    "last_updated_at": "2026-08-07T03:03:31.000Z"
                }
            }
        )


if __name__ == "__main__":
    unittest.main()
