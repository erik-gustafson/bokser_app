import httpx
from src.core.config import settings


async def write_tracking_back(tracking: dict):
    order_ref = tracking["order_ref"]
    payload = {
        "status": "shipped",
        "tracking_number": tracking["tracking_no"],
        "carrier": tracking.get("carrier"),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{settings.IM_API_BASE}/orders/{order_ref}/status",
            json=payload,
            headers={"Authorization": f"Basic {settings.IM_API_KEY}"},
        )
        r.raise_for_status()
