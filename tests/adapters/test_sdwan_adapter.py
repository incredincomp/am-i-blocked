"""Tests for bounded SD-WAN readiness probing."""

from __future__ import annotations

import httpx
import pytest
import respx
from am_i_blocked_adapters.sdwan import SDWANAdapter


class TestSDWANAdapterReadiness:
    @pytest.mark.anyio
    async def test_readiness_not_configured(self):
        adapter = SDWANAdapter(api_url=None, api_key=None)
        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_success_ready(self):
        adapter = SDWANAdapter(
            api_url="https://sdwan.example.com/api",
            api_key="tok",
            verify_ssl=False,
        )
        respx.get("https://sdwan.example.com/api").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is True
        assert result["status"] == "ready"
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_auth_failed(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="bad")
        respx.get("https://sdwan.example.com/api").mock(
            return_value=httpx.Response(401, json={"error": "invalid token"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "auth_failed"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unauthorized(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="tok")
        respx.get("https://sdwan.example.com/api").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unauthorized"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_timeout(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="tok")
        respx.get("https://sdwan.example.com/api").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "timeout"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unreachable(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="tok")
        respx.get("https://sdwan.example.com/api").mock(
            side_effect=httpx.ConnectError("dns failure")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unreachable"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unexpected_response(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="tok")
        respx.get("https://sdwan.example.com/api").mock(
            return_value=httpx.Response(200, text="not-json")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unexpected_response"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_internal_error(self):
        adapter = SDWANAdapter(api_url="https://sdwan.example.com/api", api_key="tok")
        respx.get("https://sdwan.example.com/api").mock(side_effect=RuntimeError("boom"))

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "internal_error"
