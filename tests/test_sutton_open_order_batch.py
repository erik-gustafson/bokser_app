import unittest

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from src.database.models.sutton_models import SuttonOpenOrderReport
from src.worker.jobs.process_data.sutton.process_sutton_reporting import SuttonReportProcessor


class SuttonOpenOrderBatchTests(unittest.TestCase):
    def test_missing_batch_is_inserted_and_matched_on_reimport(self):
        engine = create_engine("sqlite://")
        with engine.connect() as connection:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS sutton")
            # PostgreSQL partial indexes are verified separately; exercise the loader here.
            connection.execute(CreateTable(SuttonOpenOrderReport.__table__))
            connection.commit()
            with Session(connection) as session:
                processor = SuttonReportProcessor()
                base = dict(company="C", customer_acct="A", purchase_order="P", sku="S")
                for batch in (None, "", "B1", "B2"):
                    result = processor._commit_to_db(
                        pd.DataFrame([{**base, "warehouse_batch": batch, "quantity": 1}]),
                        SuttonOpenOrderReport, session,
                    )
                    self.assertEqual(result["errors"], 0)
                self.assertEqual(session.query(SuttonOpenOrderReport).count(), 3)
                result = processor._commit_to_db(
                    pd.DataFrame([{**base, "quantity": 2}]), SuttonOpenOrderReport, session,
                )
                self.assertEqual(result["records_updated"], 1)
                self.assertEqual(session.query(SuttonOpenOrderReport).filter_by(warehouse_batch=None).one().quantity, 2)
                invalid = processor._commit_to_db(
                    pd.DataFrame([{**base, "sku": None}]), SuttonOpenOrderReport, session,
                )
                self.assertEqual(invalid["errors"], 1)
        engine.dispose()
