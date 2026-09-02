from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.database.models.ksp_models import (
    KSPShipmentDetailItems,
    KSPShipmentDetails,
    KSPShipmentHeaders,
)
from src.worker.jobs.process_data.warehouses.process_shipment_data import (
    load_shipment_records,
)


class _AsyncTransaction:
    def __init__(self, session: Session) -> None:
        self._transaction = session.begin_nested()

    async def __aenter__(self) -> "_AsyncTransaction":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self._transaction.commit()
        else:
            self._transaction.rollback()


class _AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def begin_nested(self) -> _AsyncTransaction:
        return _AsyncTransaction(self._session)

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._session.get(*args, **kwargs)

    def add(self, instance: Any) -> None:
        self._session.add(instance)


def _shipment_payload(
    *,
    status: str,
    carrier: str,
    quantity: int,
    delivered_at: str,
    include_new_children: bool = False,
    include_stale_detail: bool = False,
) -> dict[str, Any]:
    shipments: list[dict[str, Any]] = [
        {
            "carrier": carrier,
            "method": "GROUND",
            "tracking_no": "TRACK-1",
            "tracking_no_secondary": None,
            "total_cost": 5.0,
            "package_weight_lbs": 2.0,
            "dim_weight_lbs": 3.0,
            "zone": "2",
            "delivery_surcharge_type": None,
            "date": "2026-09-01T15:00:00Z",
            "custom_1": None,
            "custom_2": None,
            "custom_3": None,
            "items": [
                {
                    "item": "SKU-1",
                    "quantity": quantity,
                    "carton_code": "BOX",
                }
            ],
        }
    ]

    if include_new_children:
        shipments[0]["items"].append(
            {
                "item": "SKU-2",
                "quantity": 1,
                "carton_code": "BOX",
            }
        )

    if include_stale_detail:
        shipments.append(
            {
                "carrier": "UPS",
                "method": "GROUND",
                "tracking_no": "TRACK-STALE",
                "total_cost": 1.0,
                "package_weight_lbs": 1.0,
                "dim_weight_lbs": 1.0,
                "date": "2026-09-01T12:00:00Z",
                "items": [{"item": "SKU-STALE", "quantity": 1}],
            }
        )
        shipments.append(
            {
                "carrier": "USPS",
                "method": "PRIORITY",
                "tracking_no": "TRACK-2",
                "total_cost": 7.0,
                "package_weight_lbs": 1.0,
                "dim_weight_lbs": 1.0,
                "date": "2026-09-01T16:00:00+00:00",
                "items": [{"item": "SKU-3", "quantity": 1}],
            }
        )

    return {
        "cust_ref": "17848",
        "cust_po_no": "5118683245",
        "delivered_to_wms_date": delivered_at,
        "order_status": status,
        "shipments": shipments,
    }


class KSPShipmentUpsertTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql(
            "ATTACH DATABASE ':memory:' AS warehouse_data"
        )
        tables = [
            KSPShipmentHeaders.__table__,
            KSPShipmentDetails.__table__,
            KSPShipmentDetailItems.__table__,
        ]
        KSPShipmentHeaders.metadata.create_all(self.connection, tables=tables)
        self.session = Session(self.connection, expire_on_commit=False)
        self.async_session = _AsyncSessionAdapter(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.connection.close()
        self.engine.dispose()

    async def test_duplicate_header_key_updates_graph_without_duplicate_insert(self) -> None:
        first = _shipment_payload(
            status="processing",
            carrier="UPS",
            quantity=1,
            delivered_at="2026-09-01T13:00:00+00:00",
            include_stale_detail=True,
        )
        second = _shipment_payload(
            status="shipped",
            carrier="FedEx",
            quantity=2,
            delivered_at="2026-09-01T14:20:53+00:00",
            include_new_children=True,
        )

        result = await load_shipment_records(
            session=self.async_session,  # type: ignore[arg-type]
            records=[first, second],
            warehouse="ksp",
        )

        self.assertEqual(result, {"loaded": 2, "failed": []})
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(KSPShipmentHeaders)),
            1,
        )

        header = self.session.get(KSPShipmentHeaders, ("17848", "5118683245"))
        self.assertIsNotNone(header)
        assert header is not None
        self.assertEqual(header.order_status, "shipped")
        self.assertEqual(
            header.delivered_to_wms_date,
            datetime(2026, 9, 1, 14, 20, 53, tzinfo=timezone.utc),
        )
        self.assertEqual(len(header.ship_details), 3)

        details = {detail.tracking_no: detail for detail in header.ship_details}
        self.assertEqual(details["TRACK-1"].carrier, "FedEx")
        items = {item.item: item for item in details["TRACK-1"].items}
        self.assertEqual(items["SKU-1"].quantity, 2)
        self.assertIn("SKU-2", items)
        self.assertIn("TRACK-2", details)
        self.assertIn("TRACK-STALE", details)


if __name__ == "__main__":
    unittest.main()
