"""Unit tests for shared infrastructure health checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from am_i_blocked_core import health_checks


class _ConnCtx:
    def __init__(self, execute: AsyncMock) -> None:
        self._execute = execute

    async def __aenter__(self) -> _ConnCtx:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, *args, **kwargs):
        await self._execute(*args, **kwargs)


@pytest.mark.anyio
async def test_database_readiness_available(monkeypatch):
    engine = MagicMock()
    execute = AsyncMock()
    engine.connect.return_value = _ConnCtx(execute)
    engine.dispose = AsyncMock()
    monkeypatch.setattr(health_checks, "create_async_engine", lambda *args, **kwargs: engine)

    result = await health_checks.check_database_readiness("postgresql+psycopg://x/y")

    assert result == {"available": True, "reason": None}
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_database_readiness_failure(monkeypatch):
    engine = MagicMock()
    execute = AsyncMock(side_effect=RuntimeError("db unavailable"))
    engine.connect.return_value = _ConnCtx(execute)
    engine.dispose = AsyncMock()
    monkeypatch.setattr(health_checks, "create_async_engine", lambda *args, **kwargs: engine)

    result = await health_checks.check_database_readiness("postgresql+psycopg://x/y")

    assert result["available"] is False
    assert "db unavailable" in (result["reason"] or "")
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_redis_readiness_available(monkeypatch):
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    monkeypatch.setattr(health_checks.redis_async, "from_url", lambda *args, **kwargs: client)

    result = await health_checks.check_redis_readiness("redis://localhost:6379/0")

    assert result == {"available": True, "reason": None}
    client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_redis_readiness_failure(monkeypatch):
    client = MagicMock()
    client.ping = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    client.aclose = AsyncMock()
    monkeypatch.setattr(health_checks.redis_async, "from_url", lambda *args, **kwargs: client)

    result = await health_checks.check_redis_readiness("redis://localhost:6379/0")

    assert result["available"] is False
    assert "redis unavailable" in (result["reason"] or "")
    client.aclose.assert_awaited_once()
