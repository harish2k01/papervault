from __future__ import annotations

import asyncio
import os
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from papervault_api.core.config import get_settings

DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_INTERVAL_SECONDS = 2.0


async def wait_for_database(
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    try:
        while time.monotonic() < deadline:
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                return
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(interval_seconds)
    finally:
        await engine.dispose()

    raise RuntimeError("Database did not become ready before timeout") from last_error


def main() -> None:
    timeout_seconds = float(
        os.getenv("PAPERVAULT_DATABASE_READY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
    )
    interval_seconds = float(
        os.getenv("PAPERVAULT_DATABASE_READY_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS),
    )
    asyncio.run(
        wait_for_database(
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        ),
    )


if __name__ == "__main__":
    main()
