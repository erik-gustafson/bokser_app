from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.integrations._base_client.token_cache import token_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    await token_store.warmup_on_startup()
    yield


app = FastAPI(title="BOKSER App API", lifespan=lifespan)


@app.get("/health/status")
def health_status() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
