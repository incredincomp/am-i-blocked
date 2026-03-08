"""Shared infrastructure readiness checks for API and worker."""

from __future__ import annotations

from typing import Any

from redis import asyncio as redis_async
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def check_database_readiness(database_url: str) -> dict[str, Any]:
    """Return database readiness state using a lightweight `SELECT 1`."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"available": True, "reason": None}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    finally:
        await engine.dispose()


async def check_redis_readiness(redis_url: str) -> dict[str, Any]:
    """Return Redis readiness state using a `PING` check."""
    client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        await client.ping()
        return {"available": True, "reason": None}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    finally:
        await client.aclose()
