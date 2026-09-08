import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.database.models.sutton_models import SuttonEDILoad
from src.worker.jobs.process_data.sutton.process_sutton_reporting import (
    SuttonReportManager,
    SuttonReportProcessor,
)


class SuttonEdiSheetTests(unittest.TestCase):
    def test_legacy_and_lake_filenames_use_detail_sheet(self):
        with TemporaryDirectory() as directory:
            for prefix in ("EDILDT", "edi"):
                with self.subTest(prefix=prefix):
                    path = Path(directory) / f"{prefix}_report.xlsx"
                    with pd.ExcelWriter(path) as writer:
                        pd.DataFrame([{"PCS": 5, "EXT": 10}]).to_excel(
                            writer, sheet_name="SUM_20260904", index=False,
                        )
                        pd.DataFrame([{
                            "CUST_ACCT#": "A", "CUST_ORDER#": "PO1",
                            "STYLE": "SKU1", "ORDER#": "ORDER1",
                        }]).to_excel(writer, sheet_name="DET_20260904", index=False)
                    manager = SuttonReportManager()
                    manager.add_report(prefix, "1", path)
                    reports = next(iter(manager.report_dicts.values()))
                    frame = SuttonReportProcessor()._pandas_read_excel_files(
                        reports, SuttonEDILoad, "edi",
                    )
                    self.assertEqual(frame.iloc[0]["cust_order"], "PO1")
                    self.assertEqual(frame.iloc[0]["order_num"], "ORDER1")
                    self.assertNotIn("PCS", frame.columns)
