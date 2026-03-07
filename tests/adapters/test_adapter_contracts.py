"""Adapter contract tests with mocked HTTP."""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx
from am_i_blocked_adapters.logscale import LogScaleAdapter
from am_i_blocked_adapters.panos import PANOSAdapter

REQUEST_ID = str(uuid.uuid4())
TIME_START = "2026-01-01T00:00:00+00:00"
TIME_END = "2026-01-01T00:15:00+00:00"


class TestPANOSAdapter:
    def setup_method(self):
        self.adapter = PANOSAdapter(
            fw_hosts=["10.0.0.1"],
            api_key="test-key",
            verify_ssl=False,
        )

    @pytest.mark.anyio
    async def test_readiness_no_hosts(self):
        adapter = PANOSAdapter(fw_hosts=[], api_key="key")
        result = await adapter.check_readiness()
        assert result["available"] is False

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_reachable_host(self):
        respx.get("https://10.0.0.1/api/").mock(
            return_value=httpx.Response(200, text="<response><result><version>10.1.0</version></result></response>")
        )
        result = await self.adapter.check_readiness()
        assert result["available"] is True

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unreachable_host(self):
        respx.get("https://10.0.0.1/api/").mock(side_effect=httpx.ConnectError("refused"))
        result = await self.adapter.check_readiness()
        assert result["available"] is False

    @pytest.mark.anyio
    async def test_query_evidence_returns_stub(self):
        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )
        assert len(records) == 1
        assert records[0].normalized["stub"] is True
        assert records[0].source.value == "panos"


class TestLogScaleAdapter:
    def setup_method(self):
        self.adapter = LogScaleAdapter(
            base_url="https://logscale.example.com",
            repo="my-repo",
            token="test-token",
        )

    @pytest.mark.anyio
    async def test_readiness_no_credentials(self):
        adapter = LogScaleAdapter(base_url="", repo="", token="")
        result = await adapter.check_readiness()
        assert result["available"] is False

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_reachable(self):
        respx.get("https://logscale.example.com/api/v1/repositories/my-repo").mock(
            return_value=httpx.Response(200, json={"name": "my-repo"})
        )
        result = await self.adapter.check_readiness()
        assert result["available"] is True

    @pytest.mark.anyio
    async def test_query_evidence_returns_stub(self):
        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=None,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )
        assert len(records) == 1
        assert records[0].normalized["stub"] is True
        assert records[0].source.value == "logscale"
