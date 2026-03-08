"""Unit tests for bounded probe failure handling."""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock

import pytest
from am_i_blocked_core.config import Settings
from am_i_blocked_worker.steps import bounded_probes


def _mock_settings() -> Settings:
    return MagicMock(
        spec=Settings,
        enable_bounded_probes=True,
        probe_dns_timeout_s=0.01,
        probe_tcp_timeout_s=0.01,
        probe_tls_timeout_s=0.01,
        probe_http_timeout_s=0.01,
    )


@pytest.mark.anyio
async def test_dns_probe_timeout_returns_failure(monkeypatch):
    async def _raise_timeout(*args, **kwargs):  # noqa: ANN002, ANN003
        raise TimeoutError

    monkeypatch.setattr(bounded_probes.asyncio, "wait_for", _raise_timeout)

    result = await bounded_probes._dns_probe("example.com", 0.01)
    assert result == {"success": False, "error": "timeout"}


@pytest.mark.anyio
async def test_tcp_probe_connection_error_returns_failure(monkeypatch):
    async def _raise_connection_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError("network unreachable")

    monkeypatch.setattr(bounded_probes.asyncio, "open_connection", _raise_connection_error)

    result = await bounded_probes._tcp_probe("example.com", 443, 0.01)
    assert result["success"] is False
    assert "network unreachable" in result["error"]


@pytest.mark.anyio
async def test_tls_probe_cert_error_is_classified(monkeypatch):
    async def _raise_cert_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ssl.SSLCertVerificationError("certificate verify failed")

    monkeypatch.setattr(bounded_probes.asyncio, "open_connection", _raise_cert_error)

    result = await bounded_probes._tls_probe("example.com", 443, 0.01)
    assert result["success"] is False
    assert "cert_verification:" in result["error"]


@pytest.mark.anyio
async def test_run_records_probe_failures_without_raising(monkeypatch):
    async def _dns(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"success": False, "error": "timeout"}

    async def _tcp(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"success": False, "error": "connection refused"}

    async def _tls(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"success": False, "error": "cert_verification: failed"}

    async def _http(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"success": False, "error": "head request failed"}

    monkeypatch.setattr(bounded_probes, "_dns_probe", _dns)
    monkeypatch.setattr(bounded_probes, "_tcp_probe", _tcp)
    monkeypatch.setattr(bounded_probes, "_tls_probe", _tls)
    monkeypatch.setattr(bounded_probes, "_http_probe", _http)

    report = await bounded_probes.run(
        destination="https://example.com/path",
        port=None,
        dest_type="url",
        settings=_mock_settings(),
    )
    payload = report.to_dict()

    assert payload["dns"]["success"] is False
    assert payload["tcp"]["success"] is False
    assert payload["tls"]["success"] is False
    assert payload["http"]["success"] is False
