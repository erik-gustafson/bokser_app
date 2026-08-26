from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.services.auth import require_api_key
from src.api.schemas.marketplaces import PayoutProcessRequestById
from src.worker.jobs.process_data.marketplaces.marketplace_services import (
    MarketplaceProcesser,
)

router = APIRouter(prefix="/marketplace", dependencies=[Depends(require_api_key)])


@router.post("/process-payout-id/", status_code=status.HTTP_200_OK)
async def process_payout_by_id(
    request_params: PayoutProcessRequestById,
) -> dict[str, int]:

    if not request_params:
        return {"status": 200, "rows": 0}

    marketplace = request_params.marketplace
    payout_id = request_params.payout_id

    mkt_processor = MarketplaceProcesser()

    try:
        await mkt_processor.process_payout(marketplace=marketplace, payout_id=payout_id)
        return {"status": 200}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
