"""Unit tests for worker queue dispatch helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from am_i_blocked_worker import main as worker_main


@pytest.mark.anyio
async def test_process_job_dispatches_pipeline():
    job = {
        "request_id": "req-1",
        "destination": "api.example.com",
        "port": 443,
        "time_window": "last_15m",
        "requester": "alice",
    }
    with patch.object(worker_main, "run_diagnostic", new_callable=AsyncMock) as run_diag:
        await worker_main._process_job(job)

    run_diag.assert_awaited_once()


@pytest.mark.anyio
async def test_main_dequeues_and_processes_job():
    job = {
        "request_id": "req-2",
        "destination": "api.example.com",
        "port": 443,
        "time_window": "last_15m",
        "requester": "alice",
    }

    with patch.object(
        worker_main,
        "get_settings",
        return_value=type(
            "Settings",
            (),
            {
                "log_level": "INFO",
                "log_format": "console",
                "worker_concurrency": 1,
                "database_url": "postgresql+psycopg://x/y",
                "redis_url": "redis://localhost:6379/0",
            },
        )(),
    ), patch.object(worker_main, "configure_logging"), patch.object(
        worker_main,
        "check_database_readiness",
        new_callable=AsyncMock,
        return_value={"available": True, "reason": None},
    ), patch.object(
        worker_main,
        "check_redis_readiness",
        new_callable=AsyncMock,
        return_value={"available": True, "reason": None},
    ), patch.object(
        worker_main,
        "dequeue_job",
        new_callable=AsyncMock,
        side_effect=[job, RuntimeError("stop-loop")],
    ), patch.object(
        worker_main,
        "_process_job",
        new_callable=AsyncMock,
    ) as process_job:
        with pytest.raises(RuntimeError, match="stop-loop"):
            await worker_main.main()

    process_job.assert_awaited_once_with(job)
