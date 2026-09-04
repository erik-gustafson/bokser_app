from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.storage.raw.utils import write_file_to_data_lake


class BinaryDataLakeWriterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.write_result = SimpleNamespace(
            file_path=Path("/data_lake/raw/sutton/report/file.xls"),
            file_name="file.xls",
            record_count=0,
            file_size_bytes=3,
            sha256="checksum",
            written_at_utc=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        self.raw_writer = MagicMock()
        self.raw_writer.write_file_bytes.return_value = self.write_result
        self.session = MagicMock()
        self.session.commit = AsyncMock()
        self.session.flush = AsyncMock()

    async def test_flushes_without_closing_caller_owned_transaction(self) -> None:
        await write_file_to_data_lake(
            session=self.session,
            raw_writer=self.raw_writer,
            source_name="sutton",
            entity_name="sales_report",
            file_bytes=b"xls",
            file_type=".xls",
            original_file_name="SLS003T_1.XLS",
            commit=False,
        )

        self.session.flush.assert_awaited_once_with()
        self.session.commit.assert_not_awaited()
        self.session.add.assert_called_once()

    async def test_commits_when_helper_owns_transaction(self) -> None:
        await write_file_to_data_lake(
            session=self.session,
            raw_writer=self.raw_writer,
            source_name="gmail",
            entity_name="attachments",
            file_bytes=b"pdf",
            file_type=".pdf",
        )

        self.session.commit.assert_awaited_once_with()
        self.session.flush.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
