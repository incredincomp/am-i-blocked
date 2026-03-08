"""Worker entry point - minimal stub for Docker CMD."""

from __future__ import annotations

import asyncio
from typing import Any

from am_i_blocked_core.config import get_settings
from am_i_blocked_core.health_checks import (
    check_database_readiness,
    check_redis_readiness,
)
from am_i_blocked_core.logging_helpers import configure_logging, get_logger
from am_i_blocked_core.queue import dequeue_job

from .pipeline import run_diagnostic

logger = get_logger(__name__)


async def _process_job(job: dict[str, Any]) -> None:
    request_id = job["request_id"]
    await run_diagnostic(
        request_id=request_id,
        destination=job["destination"],
        port=job.get("port"),
        time_window=job.get("time_window", "last_15m"),
        requester=job.get("requester", "anonymous"),
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("am-i-blocked worker started", concurrency=settings.worker_concurrency)
    db_check = await check_database_readiness(settings.database_url)
    redis_check = await check_redis_readiness(settings.redis_url)
    logger.info("worker infrastructure readiness", database=db_check, redis=redis_check)

    logger.info("worker queue loop started")
    while True:
        job = await dequeue_job(settings.redis_url, timeout_s=5)
        if not job:
            await asyncio.sleep(0)
            continue
        try:
            await _process_job(job)
        except Exception as exc:
            logger.exception(
                "worker failed to process job",
                request_id=job.get("request_id"),
                error=str(exc),
            )


if __name__ == "__main__":
    asyncio.run(main())
