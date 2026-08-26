from typing import Optional, List
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.database.database import get_async_db

# from app.database.models.item_data_models import SkuMaster

router = APIRouter()


async def must_be_admin(authorization: Optional[str] = Header(None)):
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    if token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


# class SkuIn(BaseModel):
#     sku: str = Field(min_length=1, max_length=128)
#     units_per_case: int = Field(ge=1)


# class SkuOut(SkuIn):
#     pass


# @router.get("/skus", response_model=List[SkuOut])
# async def list_skus(
#     limit: int = Query(100, ge=1, le=1000),
#     cursor: Optional[str] = None,
#     db: AsyncSession = Depends(get_async_db),
#     _=Depends(must_be_admin),
# ):
#     stmt = select(SkuMaster).order_by(SkuMaster.sku.asc()).limit(limit)
#     if cursor:
#         stmt = stmt.where(SkuMaster.sku > cursor)

#     result = await db.execute(stmt)
#     rows = result.scalars().all()

#     return [SkuOut(sku=r.sku, units_per_case=r.units_per_case) for r in rows]


# @router.post("/skus", response_model=SkuOut)
# async def upsert_sku(
#     sku: SkuIn,
#     db: AsyncSession = Depends(get_async_db),
#     _=Depends(must_be_admin),
# ):
#     row = await db.get(SkuMaster, sku.sku)

#     if not row:
#         row = SkuMaster(sku=sku.sku, units_per_case=sku.units_per_case)
#         db.add(row)
#     else:
#         row.units_per_case = sku.units_per_case

#     await db.commit()
#     await db.refresh(row)

#     return SkuOut(sku=row.sku, units_per_case=row.units_per_case)


# @router.delete("/skus/{sku}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_sku(
#     sku: str,
#     db: AsyncSession = Depends(get_async_db),
#     _=Depends(must_be_admin),
# ):
#     stmt = delete(SkuMaster).where(SkuMaster.sku == sku)
#     await db.execute(stmt)
#     await db.commit()
#     # 204 → no body
#     return
