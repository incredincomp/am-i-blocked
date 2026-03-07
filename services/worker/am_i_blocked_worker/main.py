"""Worker entry point - minimal stub for Docker CMD."""

from __future__ import annotations

import asyncio

from am_i_blocked_core.config import get_settings
from am_i_blocked_core.logging_helpers import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    logger.info("am-i-blocked worker started", concurrency=settings.worker_concurrency)

    # TODO: Connect to Redis and start processing jobs from the task queue.
    # Example loop structure:
    # async with redis_client as client:
    #     while True:
    #         job = await client.blpop("am_i_blocked:jobs", timeout=5)
    #         if job:
    #             asyncio.create_task(handle_job(job))

    logger.info("Worker loop placeholder - wire Redis queue to start processing")
    # Keep the container alive for demonstration
    while True:
        await asyncio.sleep(30)
        logger.info("worker heartbeat")


if __name__ == "__main__":
    asyncio.run(main())
