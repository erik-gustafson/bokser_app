from fastapi import APIRouter
from sqlalchemy import text
from src.database.database import sync_engine

router = APIRouter()


@router.get("/")
async def health():
    return {"ok": True, "service": "im-bridge"}


@router.get("/status")
def health_status() -> dict[str, str]:
    return {"status": "ok"}


# @router.get("/db")
# async def health_db():
#     try:
#         with sync_engine.connect() as conn:
#             conn.execute(text("SELECT 1"))
#         return {"ok": True}
#     except Exception as e:
#         return {"ok": False, "error": str(e)}
