"""Unit tests for source readiness checks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from am_i_blocked_worker.steps import source_readiness_check


def _settings(**overrides):
    defaults = {
        "panos_fw_hosts": [],
        "panos_api_key": None,
        "panos_verify_ssl": False,
        "scm_client_id": None,
        "scm_client_secret": None,
        "scm_tsg_id": None,
        "logscale_url": None,
        "logscale_repo": None,
        "logscale_token": None,
        "sdwan_api_url": None,
        "sdwan_api_key": None,
        "torq_client_id": None,
        "torq_client_secret": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.anyio
async def test_readiness_marks_logscale_unavailable_when_not_configured():
    report = await source_readiness_check.run(_settings())
    logscale = report.to_dict()["logscale"]
    assert logscale["available"] is False
    assert logscale["reason"] == "not configured"
    assert "logscale" not in report.available_sources


@pytest.mark.anyio
async def test_readiness_uses_logscale_adapter_when_configured():
    settings = _settings(
        logscale_url="https://logscale.example.com",
        logscale_repo="repo-a",
        logscale_token="token-a",
    )
    with patch(
        "am_i_blocked_adapters.logscale.LogScaleAdapter.check_readiness",
        new_callable=AsyncMock,
        return_value={"available": True, "reason": "HTTP 200", "latency_ms": 12},
    ) as readiness:
        report = await source_readiness_check.run(settings)

    readiness.assert_awaited_once()
    assert report.to_dict()["logscale"]["available"] is True
    assert "logscale" in report.available_sources
