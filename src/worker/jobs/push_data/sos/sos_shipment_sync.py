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

from sqlalchemy import select, func, cast, Text, BigInteger, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.database import async_session


from src.database.models.sos_models import SosShipmentSync

logger = logging.getLogger(__name__)


class SosShipmentSyncTasks:

    def __init__(self):
        pass

    async def process_shipment_sync(self):

        shipments_to_sync = await self.get_shipments_to_sync()

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
