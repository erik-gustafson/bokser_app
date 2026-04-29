from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="BOKSER App API")


@app.get("/health/status")
def health_status() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
