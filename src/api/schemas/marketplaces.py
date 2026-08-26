from pydantic import BaseModel


class PayoutProcessRequestById(BaseModel):

    marketplace: str
    payout_id: str
