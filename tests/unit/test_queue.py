"""Unit tests for Redis queue helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from am_i_blocked_core import queue


@pytest.mark.anyio
async def test_enqueue_job_pushes_json_payload(monkeypatch):
    client = MagicMock()
    client.rpush = AsyncMock()
    client.aclose = AsyncMock()
    monkeypatch.setattr(queue.redis_async, "from_url", lambda *args, **kwargs: client)

    payload = {"request_id": "abc", "destination": "api.example.com"}
    await queue.enqueue_job("redis://localhost:6379/0", payload)

    client.rpush.assert_awaited_once_with(queue.DIAGNOSTIC_QUEUE_KEY, json.dumps(payload))
    client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_dequeue_job_returns_none_when_timeout(monkeypatch):
    client = MagicMock()
    client.blpop = AsyncMock(return_value=None)
    client.aclose = AsyncMock()
    monkeypatch.setattr(queue.redis_async, "from_url", lambda *args, **kwargs: client)

    result = await queue.dequeue_job("redis://localhost:6379/0", timeout_s=1)

    assert result is None
    client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_dequeue_job_decodes_payload(monkeypatch):
    client = MagicMock()
    raw = json.dumps({"request_id": "xyz", "destination": "example.com"})
    client.blpop = AsyncMock(return_value=(queue.DIAGNOSTIC_QUEUE_KEY, raw))
    client.aclose = AsyncMock()
    monkeypatch.setattr(queue.redis_async, "from_url", lambda *args, **kwargs: client)

    result = await queue.dequeue_job("redis://localhost:6379/0", timeout_s=1)

    assert result == {"request_id": "xyz", "destination": "example.com"}
    client.aclose.assert_awaited_once()
