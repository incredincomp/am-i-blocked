"""Redis queue helpers for diagnostic job dispatch."""

from __future__ import annotations

import json
from typing import Any

from redis import asyncio as redis_async

DIAGNOSTIC_QUEUE_KEY = "am_i_blocked:jobs"


async def enqueue_job(redis_url: str, payload: dict[str, Any]) -> None:
    """Push a diagnostic job payload to the Redis queue."""
    client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        await client.rpush(DIAGNOSTIC_QUEUE_KEY, json.dumps(payload))
    finally:
        await client.aclose()


async def dequeue_job(redis_url: str, timeout_s: int = 5) -> dict[str, Any] | None:
    """Pop a diagnostic job payload from Redis, returning None on timeout."""
    client = redis_async.from_url(redis_url, decode_responses=True)
    try:
        item = await client.blpop([DIAGNOSTIC_QUEUE_KEY], timeout=timeout_s)
        if item is None:
            return None
        _queue_key, raw_payload = item
        return json.loads(raw_payload)
    finally:
        await client.aclose()
