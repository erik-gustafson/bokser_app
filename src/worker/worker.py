from __future__ import annotations

import asyncio

from src.worker.main import run_worker


if __name__ == "__main__":
    asyncio.run(run_worker())
