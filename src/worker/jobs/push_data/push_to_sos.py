from __future__ import annotations

import asyncio
import logging
from sqlalchemy import select, func, cast, Text
from sqlalchemy.orm import selectinload

from src.database.database import async_session
from src.database.models import (
    AcendaOrderHeaders,
    AcendaOrderItems,
    SosSalesOrderHeader,
    SosSalesOrderLine,
    SosItem,
)

from .sos_payload_mapper import SosSalesOrderPayloadMapper

logger = logging.getLogger(__name__)


async def load_sos_items_by_sku(skus: list[str | None]):
    if not skus:
        return

    async with async_session() as session:

        stmt = select(SosItem.id).where(SosItem.sku.in_(skus))

        return list((await session.scalars(stmt)).all())


class AcendaOrderPush:

    def __init__(self):
        self.sos_mapper = SosSalesOrderPayloadMapper()

    async def send_to_sos(self):

        open_orders = await self.load_open_acenda_db_orders()

        if open_orders:
            tasks = []
            async with asyncio.TaskGroup() as tg:
                for order in open_orders:
                    task = tg.create_task(self.safe_map_order(order))
                    tasks.append(task)

            results = [task.result() for task in tasks]

            for result in results:
                if isinstance(result, Exception):
                    print(f"Task {result} returned error: {result}")
                else:
                    print(f"Task {result} returned data: {result}")

    async def load_open_acenda_db_orders(self) -> list[AcendaOrderHeaders]:

        async with async_session() as session:
            sos_order_exists = (
                select(SosSalesOrderHeader.id)
                .where(
                    cast(SosSalesOrderHeader.customer_po, Text)
                    == cast(AcendaOrderHeaders.id, Text)
                )
                .exists()
            )

            stmt = (
                select(AcendaOrderHeaders)
                .options(selectinload(AcendaOrderHeaders.items))
                .where(
                    AcendaOrderHeaders.created_at >= func.current_date() - 90,
                    ~sos_order_exists,
                )
                .order_by(AcendaOrderHeaders.id.asc())
            )

            return list((await session.scalars(stmt)).all())

    async def safe_map_order(self, order):
        try:
            return await self.map_order(order)
        except Exception as e:
            return e

    async def map_order(self, order: AcendaOrderHeaders):

        # Name: (Acenda Id, Sos ID)
        sales_channel_dict = {
            "Target Plus US Marketplace": (1, 15),
            "Macys": (2, 49),
            "Kohls": (3, 66),
            "bokserhome.myshopify.com": (4, 12),
            "Overstock": (5, 37),
            "Walmart US": (6, 206),
            "Wayfair": (7, 135),
        }

        if order.sales_channel_name:
            channel_id = sales_channel_dict.get(order.sales_channel_name, (None, None))[
                1
            ]

        else:
            raise ValueError(
                f"No Sales Channel Name Provided for Acenda Order {order.id}"
            )

        skus = list({item.sku for item in order.items})

        sos_items = await load_sos_items_by_sku(skus)
        if sos_items and len(sos_items) < len(skus):
            logger.error(f"No SOS Sku Match for {skus}")
        # return await self.sos_mapper.map_acenda_order(order)
