# app/main.py
from __future__ import annotations

import logging
from src.core.utils.logger import setup_logging

from fastapi import FastAPI
from contextlib import asynccontextmanager

from src.api.routers import health, rithum, webhooks
from src.core.config import settings
from src.api.services.validators import WMSKeyVerifier
from src.integrations._base_client.token_cache import token_store

setup_logging(settings.log_level)
logger = logging.getLogger("api")

logger.info("Starting API app...")


# ---- LIFESPAN HANDLER ---- #
@asynccontextmanager
async def lifespan(app: FastAPI):

    verifier = WMSKeyVerifier()
    await verifier.warm()  # fetch and cache key at boot
    app.state.wms_verifier = verifier
    logger.info("WMS RSA verifier initialized and key cached")

    await token_store.warmup_on_startup()

    # Let FastAPI run
    yield

    # Shutdown tasks
    await app.state.wms_verifier.aclose()
    logger.info("WMS RSA verifier closed")


# ---- FASTAPI APP ---- #
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.ROOT_API_PATH}/openapi.json",
    docs_url=f"{settings.ROOT_API_PATH}/docs",
    redoc_url=f"{settings.ROOT_API_PATH}/redoc",
    lifespan=lifespan,
)


# ---- ROUTERS ---- #
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(webhooks.router, prefix="/order-bridge", tags=["im", "wms"])
app.include_router(rithum.router, tags=["rithum"])
