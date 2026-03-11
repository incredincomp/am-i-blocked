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
        "scm_auth_url": "https://auth.apps.paloaltonetworks.com/oauth2/access_token",
        "scm_api_base_url": "https://api.sase.paloaltonetworks.com",
        "logscale_url": None,
        "logscale_repo": None,
        "logscale_token": None,
        "sdwan_api_url": None,
        "sdwan_api_key": None,
        "sdwan_verify_ssl": False,
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


@pytest.mark.anyio
async def test_readiness_uses_scm_adapter_when_configured():
    settings = _settings(
        scm_client_id="cid",
        scm_client_secret="sec",
        scm_tsg_id="tsg",
        scm_auth_url="https://auth.example.com/oauth2/access_token",
        scm_api_base_url="https://api.example.com",
    )
    with patch(
        "am_i_blocked_adapters.scm.SCMAdapter.check_readiness",
        new_callable=AsyncMock,
        return_value={
            "available": False,
            "status": "auth_failed",
            "reason": "SCM auth failed (401)",
            "latency_ms": 12,
        },
    ) as readiness:
        report = await source_readiness_check.run(settings)

    readiness.assert_awaited_once()
    scm = report.to_dict()["scm"]
    assert scm["status"] == "auth_failed"
    assert scm["available"] is False
    assert "scm" not in report.available_sources


@pytest.mark.anyio
async def test_readiness_scm_not_configured_comes_from_adapter():
    settings = _settings()
    report = await source_readiness_check.run(settings)
    scm = report.to_dict()["scm"]
    assert scm["available"] is False
    assert scm["status"] == "not_configured"


@pytest.mark.anyio
async def test_readiness_uses_sdwan_adapter_when_configured():
    settings = _settings(
        sdwan_api_url="https://sdwan.example.com/api",
        sdwan_api_key="tok",
        sdwan_verify_ssl=True,
    )
    with patch(
        "am_i_blocked_adapters.sdwan.SDWANAdapter.check_readiness",
        new_callable=AsyncMock,
        return_value={
            "available": False,
            "status": "timeout",
            "reason": "SD-WAN readiness probe timed out",
            "latency_ms": None,
        },
    ) as readiness:
        report = await source_readiness_check.run(settings)

    readiness.assert_awaited_once()
    sdwan = report.to_dict()["sdwan"]
    assert sdwan["status"] == "timeout"
    assert sdwan["available"] is False
    assert "sdwan" not in report.available_sources


@pytest.mark.anyio
async def test_readiness_sdwan_not_configured_comes_from_adapter():
    settings = _settings()
    report = await source_readiness_check.run(settings)
    sdwan = report.to_dict()["sdwan"]
    assert sdwan["available"] is False
    assert sdwan["status"] == "not_configured"
