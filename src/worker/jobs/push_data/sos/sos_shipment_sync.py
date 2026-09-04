"""
KSP, pull cust ref try to load from sos unsig id, match po# in no match then get by query of customer PO
Productiv, use ref % and strip after "."
Sutton Good lord, proabyl match based on a moon cycle or something.  Customer PO is best proxy.  Review old code for key.


Use 3PL Shipment ship_header ID + warehouse table source name (i.e. Sutton, productiv, ksp) as unique constraint, line details can live with soruce, sync table only captures header level becuase we will always post everything


"""

"""
Sutton Sales Report PK = invoice + "sutton
Productiv = id + "productiv"
KSP = id + "ksp"
"""
import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, exists, literal, select, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.database import async_session
from src.database.models import *

from src.integrations.sos_client import SOSClient

logger = logging.getLogger(__name__)


class SosShipmentSyncTasks:

    def __init__(self):
        self.sos_client = SOSClient()

    async def process_shipment_sync(self):

        shipments_to_sync = await self.get_shipments_to_sync()

        self.sos_client.get()

    async def get_shipments_to_sync(
        self,
    ) -> list[SosShipmentSync]:

        sync_delay = datetime.now(timezone.utc) - timedelta(minutes=15)

        async with async_session() as session:
            stmt = select(SosShipmentSync).where(
                or_(
                    SosShipmentSync.status == "pending",
                    SosShipmentSync.sos_shipment_id.is_(None),
                ),
                SosShipmentSync.created_at <= sync_delay,
            )

            result = await session.scalars(stmt)

            return list(result.all())

    async def direct_load_to_sync_table(self) -> None:

        async with async_session() as session:
            sources = [
                ("sutton", SuttonSalesReport),
                ("ksp", KSPShipmentHeaders),
                ("productiv", ProductivShipmentHeaders),
            ]

            for source_name, model in sources:

                if source_name == "sutton":
                    source_id = model.invoice
                elif source_name == "ksp":
                    source_id = model.cust_ref
                else:
                    source_id = model.order_id

                source_id_as_string = cast(source_id, String(128))

                source_rows = select(
                    literal(source_name),
                    source_id_as_string,
                ).where(
                    ~exists(
                        select(1).where(
                            SosShipmentSync.source == source_name,
                            SosShipmentSync.source_id == source_id_as_string,
                        )
                    )
                )

                stmt = (
                    insert(SosShipmentSync)
                    .from_select(
                        ["source", "source_id"],
                        source_rows,
                    )
                    .on_conflict_do_nothing(
                        constraint="ux_sos_shipment_sync_source_key"
                    )
                )

                await session.execute(stmt)

            await session.commit()
