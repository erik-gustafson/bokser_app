import asyncio
from typing import Optional, Any
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    and_,
    func,
    or_,
    select,
    update,
    tuple_,
    and_,
    case,
    func,
    select,
    inspect,
    delete,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement, SQLColumnExpression
from sqlalchemy.orm import selectinload

from sqlalchemy.ext.asyncio import AsyncSession
from dataclasses import dataclass
from src.database.database import async_session
from src.integrations.sos_client import SOSClient

from src.database.models.marketplace_models import (
    WayfairPayment,
    WayfairDeduction,
    TargetPayout,
    TargetTransfer,
    BbbPayout,
)

from src.database.models.sos_models import (
    SosSalesOrderHeader,
    SosItem,
)


async def invoice_mkt_order(client, order_numbers):

    sos_client = SOSClient()

    invoices = []

    for number in order_numbers:

        so_response = await sos_client.get(f"/salesorder/?query={number}&archived=both")
        so_raw = so_response.json()
        so_record = so_raw.get("data", [])[0]
        ship_response = await sos_client.get(f"/shipment/?query={number}&archived=both")
        shipment_raw = ship_response.json()
        ship_record = shipment_raw.get("data", [])[0]

        lines = []
        total = 0.0
        mkt_fee = 0.0
        for line in so_record["lines"]:
            _line = {
                "item": line["item"],
                "class": line["class"],
                "linkedTransaction": {
                    "id": line["id"],
                    "transactionType": "SO",
                    "refNumber": so_record["number"],
                    "lineNumber": line["lineNumber"],
                },
                "quantity": line["shipped"],
                "unitprice": line["unitprice"],
                "amount": line["amount"],
                "uom": line["uom"],
            }
            total += line["amount"]
            mkt_fee -= round((line["amount"] * 0.15), 2)
            lines.append(_line)

        mkt_fee_line = {
            "item": {"id": 1448, "name": "Target Marketplace Referral Fee"},
            "class": {"id": 2, "name": "DTC"},
            "quantity": 1,
            "unitprice": mkt_fee,
            "amount": mkt_fee,
        }

        total += mkt_fee

        lines.append(mkt_fee_line)

        inv = {
            "number": "auto",
            "date": ship_record["date"],
            "customer": so_record["customer"],
            "billing": so_record["billing"],
            "shipping": so_record["shipping"],
            "terms": so_record["terms"],
            "customerPO": so_record["customerPO"],
            "trackingNumber": ship_record["trackingNumber"],
            "shipDate": ship_record["date"],
            "shippingMethod": ship_record["shippingMethod"],
            "total": total,
            "lines": lines,
        }

        invoices.append(inv)

    response = await sos_client.post("/invoice", json_data=invoices)

    return response.json()


async def return_mkt_order(session: AsyncSession, data):

    sos_client = SOSClient()
    returns = []
    for order_id, ret_lines in data.items():

        # ship_response = await sos_client.sos_get_request(
        #     f"/shipment/?query={order_id}&archived=both"
        # )
        # shipment_raw = ship_response.json()
        # ship_record = shipment_raw.get("data", [])[0]

        lines = []
        total = 0.0
        mkt_fee = 0.0
        for line in ret_lines:
            _line = {}
            upc = (
                await session.execute(
                    select(SosItem.id, SosItem.name).where(
                        SosItem.sku == line.seller_sku
                    )
                )
            ).first()

            if not upc:
                raise ValueError(f"No UPC Returned for {order_id} - {line}")

            if line.transfer_type == "RETURN":
                line_total = abs(float(line.payment_amount))
                qty = int(line.quantity)
                unit_price = line_total / qty
                _line = {
                    "item": {"id": upc[0], "name": upc[1]},
                    "class": {"id": 2, "name": "DTC"},
                    "quantity": qty,
                    "unitprice": unit_price,
                    "amount": line_total,
                    "uom": {"id": 1, "name": "EA"},
                }
                total += line_total

            else:

                _line = {
                    "item": {
                        "id": 1343,
                        "name": "Target Marketplace Return Service Fee",
                    },
                    "class": {"id": 2, "name": "DTC"},
                    "quantity": 1,
                    "unitprice": float(line.payment_amount),
                    "amount": float(line.payment_amount),
                }

                total += float(line.payment_amount)

            lines.append(_line)

        ret = {
            "number": "auto",
            "date": datetime.now().isoformat(timespec="seconds"),
            "customer": {
                "id": 15,
                "name": "Target.com DTC",
                "fullname": "Target.com DTC",
            },
            "location": {"id": 4, "name": "KSP"},
            "customFields": [
                {"id": 17, "name": "Invoice Number", "value": "", "dataType": "Text"},
                {"id": 16, "name": "PO Number", "value": order_id, "dataType": "Text"},
            ],
            "total": total,
            "createCreditMemo": True,
            "lines": lines,
        }

        returns.append(ret)

    post_response = await sos_client.post("/return", json_data=returns)


class MarketplaceProcesser:

    def __init__(self):
        self.sos_client = SOSClient()

    async def process_payout(self, marketplace: str, payout_id: str):

        async with async_session() as session:

            if marketplace == "target":
                tgt_payout_data = await self._get_target_payout_data(session, payout_id)

                order_nums = set([x.order_id for x in tgt_payout_data["SALE"]])

                # await invoice_mkt_order(
                #     client=self.sos_client, order_numbers=order_nums
                # )

            # returns_by_order: dict[str, list[dict[str, Any]]] = {}

            # for mkt_ret in tgt_payout_data["RETURN"]:
            #     if mkt_ret.order_id:
            #         if mkt_ret.order_id not in returns_by_order.keys():
            #             returns_by_order[mkt_ret.order_id] = []
            #         returns_by_order[mkt_ret.order_id].append(mkt_ret)

            # for mkt_ret_fee in tgt_payout_data["RETURN SERVICE FEE"]:
            #     if mkt_ret_fee.order_id:
            #         returns_by_order[mkt_ret_fee.order_id].append(mkt_ret_fee)

            # await return_mkt_order(session, returns_by_order)

            await self.create_mkt_payment(session, payout_id, order_nums)

    async def invoice_mkt_orders(self):

        async with async_session() as session:
            orders = await self._get_db_data(session)

    async def create_mkt_payment(
        self, session: AsyncSession, payout_id: str, order_nums: set
    ):

        stmt = select(TargetPayout.amount).where(TargetPayout.payout_id == payout_id)
        payout_total = (await session.execute(stmt)).first()

        payment_total = 0.0
        invs_to_payout = []
        for order_num in order_nums:

            inv_response = await self.sos_client.get(
                f"/invoice/?query={order_num}&archived=both"
            )
            inv_raw = inv_response.json()
            inv_record = inv_raw.get("data", [])[0]

            _inv = {
                "linkedTransaction": {
                    "id": inv_record["id"],
                    "transactionType": "Invoice",
                    "refNumber": inv_record["number"],
                },
                "amount": inv_record["total"],
            }
            payment_total += inv_record["total"]
            invs_to_payout.append(_inv)

        payout = {
            "number": payout_id,
            "date": datetime.now().isoformat(timespec="seconds"),
            "customer": {
                "id": 15,
                "name": "Target.com DTC",
                "fullname": "Target.com DTC",
            },
            "currency": {"id": 42, "name": "USD"},
            "depositAccount": {"id": 26, "name": "Boxer (9187)"},
            "class": {"id": 2, "name": "DTC"},
            "total": payment_total,
            "lines": invs_to_payout,
        }

        payment_response = await self.sos_client.post("/payment", json_data=payout)

        return payment_response.json()

    async def _get_target_payout_data(self, session: AsyncSession, payout_id: str):

        tgt_payout_line_type: dict[str, list[TargetTransfer]] = {
            "SALE": [],
            "RETURN": [],
            "DISPUTE": [],
            "RETURN SERVICE FEE": [],
        }

        stmt = select(TargetTransfer).where(TargetTransfer.payout_id == payout_id)

        tgt_payout_data = (await session.execute(stmt)).scalars().all()

        for row in tgt_payout_data:
            if row.transfer_type == "SALE":
                tgt_payout_line_type["SALE"].append(row)
            elif row.transfer_type == "RETURN":
                tgt_payout_line_type["RETURN"].append(row)
            elif row.transfer_type == "RETURN SERVICE FEE":
                tgt_payout_line_type["RETURN SERVICE FEE"].append(row)
            elif row.transfer_type == "DISPUTE":
                tgt_payout_line_type["DISPUTE"].append(row)

        return tgt_payout_line_type

    async def _get_db_data(self, session: AsyncSession):

        now = datetime.utcnow()
        cust_pos = [
            "912003437470674-8688107874",
            "902003438829262-8706094967",
            "912003295980373-8688132688",
            "912003438738093-8688122676",
            "902003397507860-8705862482",
            "912003436698818-8687891872",
            "912003437005726-8705812005",
            "902003437688540-8705888295",
            "902003112657500-8697619043",
            "102003437925470-8705883396",
            "902003437989062-8687945958",
            "912003438061673-8705915356",
            "912003437351645-8715638312",
            "912003404716832-8687932094",
            "912002591479605-8705832104",
            "912003203769482-8705957603",
            "912003437418017-8697383707",
            "102003253980139-8697356002",
            "912003436805238-8697327201",
            "102003424775158-8705735656",
            "902003436491024-8705694026",
            "902003436319416-8715406837",
            "902003345637643-8715297694",
            "902003363373866-8697134842",
            "912003435824453-8715327374",
            "902003435964787-8687763387",
            "102003427365958-8705466883",
            "912003354391582-8687471312",
            "912003434228588-8705339318",
            "922003429644348-8715034913",
            "902003389986536-8715057033",
            "912003434439716-8687508055",
            "902003433996964-8705383255",
            "102003434218281-8687451720",
            "912003434191758-8696931718",
            "102003425402531-8705214466",
            "902003433261354-8696698006",
            "912003410372887-8687260801",
            "902003432121326-8714717910",
            "912003430677384-8714761704",
            "912003425421612-8714807273",
            "912003432559130-8705092620",
            "912003431585628-8705124140",
            "912003431478882-8714700338",
            "922003415222939-8714574412",
            "922003415222939-8714574412",
            "912003101513376-8686760520",
            "912003101513376-8686760520",
            "912003101513376-8686760520",
            "912003101513376-8686760520",
            "912003415172502-8696245457",
            "912003415172502-8696245457",
            "912003422455178-8704639926",
            "912003429591278-8714208133",
            "912003415172502-8696245457",
            "912003429298647-8714335148",
            "102003419116252-8714192840",
            "102003418068893-8696180692",
            "912003101513376-8686760520",
            "912003422430344-8686602545",
            "912003429043330-8714144627",
            "102003427858868-8704377976",
            "912003425675087-8686633908",
            "912003428996874-8696095062",
            "912002904404408-8686936904",
            "902003363011893-8704528698",
            "902003297890389-8686666078",
            "912003427313809-8704279466",
            "102003052043070-8695713583",
            "912003426891076-8704225508",
            "912003427242206-8686456669",
            "912003426719523-8686412172",
            "912003425322520-8704020121",
        ]

        stmt = (
            select(SosSalesOrderHeader.id)
            .where(SosSalesOrderHeader.customer_po.in_(cust_pos))
            .distinct(SosSalesOrderHeader.id)
            .order_by(
                SosSalesOrderHeader.id,
                SosSalesOrderHeader.sync_token.desc(),
            )
        )

        return set((await session.execute(stmt)).scalars().all())


if __name__ == "__main__":
    mkt = MarketplaceProcesser()
    asyncio.run(mkt.invoice_mkt_orders())
