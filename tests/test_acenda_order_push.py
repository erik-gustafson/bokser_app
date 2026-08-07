from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.worker.jobs.push_data.push_to_sos import AcendaOrderPush


class _TransactionContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> None:
        self.events.append("transaction_entered")

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self.events.append("transaction_committed")


class _SessionContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> _SessionContext:
        self.events.append("session_entered")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.events.append("session_exited")

    def begin(self) -> _TransactionContext:
        return _TransactionContext(self.events)


class AcendaOrderPushTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_rows_commit_before_orders_are_posted(self) -> None:
        events: list[str] = []
        session = _SessionContext(events)
        line = MagicMock(id=57234)
        line.to_payload.return_value = {"id": 57234}
        order = MagicMock(number="50458", lines=[line])

        push = AcendaOrderPush.__new__(AcendaOrderPush)
        push.sos_items = MagicMock()
        push.sos_so_sync = MagicMock()
        push.sos_so_sync._hash_payload.return_value = "payload-hash"
        push.sos_so_sync._build_sync_row.return_value = MagicMock()

        async def upsert_sync_rows(*, session, rows) -> None:
            events.append("sync_rows_upserted")

        async def post_to_sos_and_log(*, mapped_order):
            self.assertIn("transaction_committed", events)
            self.assertIn("session_exited", events)
            events.append("order_posted")
            return True, None

        push.sos_so_sync._upsert_sync_rows = AsyncMock(
            side_effect=upsert_sync_rows
        )
        push.load_open_acenda_db_orders = AsyncMock(return_value=[MagicMock()])
        push._get_order_skus = MagicMock(return_value=())
        push._map_orders = MagicMock(return_value=([order], []))
        push._post_to_sos_and_log = AsyncMock(
            side_effect=post_to_sos_and_log
        )

        with patch(
            "src.worker.jobs.push_data.push_to_sos.async_session",
            return_value=session,
        ), patch("builtins.print"):
            await push.send_to_sos()

        push.sos_so_sync._upsert_sync_rows.assert_awaited_once()
        push._post_to_sos_and_log.assert_awaited_once_with(
            mapped_order=order
        )
        self.assertLess(
            events.index("transaction_committed"),
            events.index("order_posted"),
        )


if __name__ == "__main__":
    unittest.main()
