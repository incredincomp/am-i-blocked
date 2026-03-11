"""Tests for bounded LogScale readiness probing."""

from __future__ import annotations

import httpx
import pytest
import respx
from am_i_blocked_adapters.logscale import LogScaleAdapter


class TestLogScaleAdapterReadiness:
    @pytest.mark.anyio
    async def test_readiness_not_configured(self):
        adapter = LogScaleAdapter(base_url="", repo="", token="")
        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_success_ready(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            return_value=httpx.Response(200, json={"name": "repo-a"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is True
        assert result["status"] == "ready"
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_auth_failed(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="bad",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "auth_failed"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unauthorized(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unauthorized"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_timeout(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "timeout"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unreachable(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            side_effect=httpx.ConnectError("dns failure")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unreachable"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unexpected_response(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            return_value=httpx.Response(200, text="not-json")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unexpected_response"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_internal_error(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )
        respx.get("https://logscale.example.com/api/v1/repositories/repo-a").mock(
            side_effect=RuntimeError("boom")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "internal_error"


class TestLogScaleAuthorityBoundary:
    @pytest.mark.anyio
    async def test_query_evidence_remains_enrichment_only(self):
        adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="repo-a",
            token="tok",
        )

        records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00Z",
            time_window_end="2026-01-01T00:15:00Z",
            request_id="11111111-1111-1111-1111-111111111111",
        )

        assert len(records) == 1
        assert records[0].normalized["classification_role"] == "enrichment_only_unverified"
        assert records[0].normalized["authoritative"] is False
