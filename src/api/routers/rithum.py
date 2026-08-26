from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.database.database import get_async_db
from src.database.models.order_data_models import (
    RithumPOHeader,
    RithumPODetail,
)
from src.api.services.auth import require_api_key

router = APIRouter(prefix="/rithum", dependencies=[Depends(require_api_key)])


@router.post("/order-headers/", status_code=status.HTTP_200_OK)
async def post_rithum_order_headers(
    rithum_po_headers: list[RithumPOHeader.RithumPOHeaderSchema],
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, int]:
    if not rithum_po_headers:
        return {"status": 200, "rows": 0}

    rows = [item.model_dump() for item in rithum_po_headers]

    stmt = insert(RithumPOHeader).values(rows)
    excluded = stmt.excluded
    update_cols = {
        col.name: getattr(excluded, col.name)
        for col in RithumPOHeader.__table__.columns
        if col.name != "hub_order_id"
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[RithumPOHeader.hub_order_id],
        set_=update_cols,
    )

    try:
        await db.execute(stmt)
        await db.commit()
        return {"status": 200, "rows": len(rows)}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/order-details/", status_code=status.HTTP_200_OK)
async def post_rithum_order_details(
    rithum_po_details: list[RithumPODetail.RithumPODetailSchema],
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, int]:
    if not rithum_po_details:
        return {"status": 200, "rows": 0}

    rows = [item.model_dump() for item in rithum_po_details]

    stmt = insert(RithumPODetail).values(rows)
    excluded = stmt.excluded
    update_cols = {
        col.name: getattr(excluded, col.name)
        for col in RithumPODetail.__table__.columns
        if col.name != "hub_line_id"
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[RithumPODetail.hub_line_id],
        set_=update_cols,
    )

    try:
        await db.execute(stmt)
        await db.commit()
        return {"status": 200, "rows": len(rows)}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
