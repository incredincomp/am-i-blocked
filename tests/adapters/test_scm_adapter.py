"""Tests for bounded SCM readiness probing."""

from __future__ import annotations

import httpx
import pytest
import respx
from am_i_blocked_adapters.scm import SCMAdapter


class TestSCMAdapterReadiness:
    @pytest.mark.anyio
    async def test_readiness_not_configured(self):
        adapter = SCMAdapter(client_id=None, client_secret=None, tsg_id=None)
        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_success_ready(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is True
        assert result["status"] == "ready"
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_auth_failed(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="bad",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "auth_failed"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unauthorized(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unauthorized"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_timeout(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "timeout"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unreachable(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            side_effect=httpx.ConnectError("dns failure")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unreachable"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unexpected_response(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"token_type": "Bearer"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unexpected_response"
