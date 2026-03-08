"""End-to-end fixture tests for the diagnostic pipeline."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from am_i_blocked_core.enums import (
    EvidenceKind,
    EvidenceSource,
    OwnerTeam,
    Verdict,
)
from am_i_blocked_core.models import EvidenceRecord
from am_i_blocked_worker.pipeline import run_diagnostic


def _mock_settings(**kwargs):
    from am_i_blocked_core.config import Settings

    defaults = {
        "enable_bounded_probes": False,
        "panos_fw_hosts": [],
        "panos_api_key": None,
        "scm_client_id": None,
        "scm_client_secret": None,
        "scm_tsg_id": None,
        "logscale_url": None,
        "logscale_token": None,
        "logscale_repo": None,
        "sdwan_api_url": None,
        "sdwan_api_key": None,
        "torq_client_id": None,
        "torq_client_secret": None,
        "log_level": "WARNING",
        "log_format": "console",
        "anonymous_user": "anonymous",
        "app_identity_header": "X-Forwarded-User",
        "worker_concurrency": 2,
        "job_timeout_s": 30,
        "probe_dns_timeout_s": 3.0,
        "probe_tcp_timeout_s": 3.0,
        "probe_tls_timeout_s": 5.0,
        "probe_http_timeout_s": 8.0,
        "panos_verify_ssl": False,
        "sdwan_verify_ssl": False,
        "scm_auth_url": "https://auth.example.com",
        "scm_api_base_url": "https://api.example.com",
        "torq_api_base_url": "https://api.torq.io",
        "database_url": "postgresql+psycopg://app:app@localhost/test",
        "redis_url": "redis://localhost:6379/0",
    }
    defaults.update(kwargs)
    return MagicMock(spec=Settings, **defaults)


def _make_evidence(source, kind, normalized, request_id=None):
    return EvidenceRecord(
        evidence_id=uuid.uuid4(),
        request_id=uuid.UUID(request_id or str(uuid.uuid4())),
        source=source,
        kind=kind,
        normalized=normalized,
    )


@pytest.mark.anyio
async def test_cloud_deny_case():
    """Happy path: cloud deny evidence → verdict=denied, owner=SecOps."""
    req_id = str(uuid.uuid4())
    request_store = {
        req_id: {
            "status": "pending",
            "request_id": uuid.UUID(req_id),
            "destination_value": "api.example.com",
        }
    }
    result_store = {}

    cloud_deny_ev = _make_evidence(
        EvidenceSource.SCM,
        EvidenceKind.TRAFFIC_LOG,
        {"action": "deny", "rule_name": "block-saas"},
        request_id=req_id,
    )

    settings = _mock_settings(scm_client_id="cid", scm_client_secret="sec", scm_tsg_id="tsg")

    with patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        new_callable=AsyncMock,
    ) as mock_readiness, patch(
        "am_i_blocked_worker.steps.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[cloud_deny_ev],
    ):
        mock_readiness.return_value = MagicMock(
            to_dict=lambda: {"scm": {"available": True}},
            available_sources=["scm"],
        )

        result = await run_diagnostic(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window="last_15m",
            requester="alice",
            request_store=request_store,
            result_store=result_store,
            settings=settings,
        )

    assert result.verdict == Verdict.DENIED
    assert result.routing_recommendation.owner_team == OwnerTeam.SECOPS
    assert str(result.request_id) == req_id
    assert result_store[req_id].verdict == Verdict.DENIED
    assert request_store[req_id]["status"] == "complete"


@pytest.mark.anyio
async def test_onprem_deny_case():
    """On-prem deny evidence → verdict=denied, owner=SecOps."""
    req_id = str(uuid.uuid4())
    request_store = {req_id: {"status": "pending", "request_id": uuid.UUID(req_id)}}
    result_store = {}

    onprem_deny_ev = _make_evidence(
        EvidenceSource.PANOS,
        EvidenceKind.TRAFFIC_LOG,
        {"action": "deny", "rule_name": "block-external"},
        request_id=req_id,
    )

    settings = _mock_settings(
        panos_fw_hosts=["10.0.0.1"], panos_api_key="key"
    )

    with patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        new_callable=AsyncMock,
    ) as mock_readiness, patch(
        "am_i_blocked_worker.steps.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[onprem_deny_ev],
    ):
        mock_readiness.return_value = MagicMock(
            to_dict=lambda: {"panos": {"available": True}},
            available_sources=["panos"],
        )

        result = await run_diagnostic(
            request_id=req_id,
            destination="10.1.2.3",
            port=22,
            time_window="last_15m",
            requester="bob",
            request_store=request_store,
            result_store=result_store,
            settings=settings,
        )

    assert result.verdict == Verdict.DENIED
    assert result.routing_recommendation.owner_team == OwnerTeam.SECOPS


@pytest.mark.anyio
async def test_sdwan_degraded_no_deny_case():
    """SD-WAN degradation without deny → verdict=unknown, owner=NetOps."""
    req_id = str(uuid.uuid4())
    request_store = {req_id: {"status": "pending", "request_id": uuid.UUID(req_id)}}
    result_store = {}

    sdwan_ev = _make_evidence(
        EvidenceSource.SDWAN,
        EvidenceKind.PATH_SIGNAL,
        {"degraded": True, "site_id": "site-001", "health_score": 0.2},
        request_id=req_id,
    )

    settings = _mock_settings()

    with patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        new_callable=AsyncMock,
    ) as mock_readiness, patch(
        "am_i_blocked_worker.steps.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[sdwan_ev],
    ):
        mock_readiness.return_value = MagicMock(
            to_dict=lambda: {"sdwan": {"available": True}},
            available_sources=["sdwan"],
        )

        result = await run_diagnostic(
            request_id=req_id,
            destination="api.example.com",
            port=None,
            time_window="last_60m",
            requester="charlie",
            request_store=request_store,
            result_store=result_store,
            settings=settings,
        )

    assert result.verdict == Verdict.UNKNOWN
    assert result.routing_recommendation.owner_team == OwnerTeam.NETOPS


@pytest.mark.anyio
async def test_incomplete_telemetry_unknown_case():
    """Stub evidence only → verdict=unknown, low confidence."""
    req_id = str(uuid.uuid4())
    request_store = {req_id: {"status": "pending", "request_id": uuid.UUID(req_id)}}
    result_store = {}

    stub_ev = _make_evidence(
        EvidenceSource.PANOS,
        EvidenceKind.TRAFFIC_LOG,
        {"stub": True, "message": "not wired"},
        request_id=req_id,
    )

    settings = _mock_settings()

    with patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        new_callable=AsyncMock,
    ) as mock_readiness, patch(
        "am_i_blocked_worker.steps.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[stub_ev],
    ):
        mock_readiness.return_value = MagicMock(
            to_dict=lambda: {"panos": {"available": False}},
            available_sources=[],
        )

        result = await run_diagnostic(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window="last_15m",
            requester="dave",
            request_store=request_store,
            result_store=result_store,
            settings=settings,
        )

    assert result.verdict == Verdict.UNKNOWN
    assert result.result_confidence <= 0.2


@pytest.mark.anyio
async def test_probe_failures_degrade_to_unknown_not_crash():
    """Probe errors/timeouts without authoritative evidence must remain unknown."""
    req_id = str(uuid.uuid4())
    request_store = {req_id: {"status": "pending", "request_id": uuid.UUID(req_id)}}
    result_store = {}

    settings = _mock_settings(enable_bounded_probes=True)
    probe_report = MagicMock(
        to_dict=lambda: {
            "dns": {"success": False, "error": "timeout"},
            "tcp": {"success": False, "error": "connection refused"},
            "http": {"success": False, "error": "request error"},
        }
    )

    with patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        new_callable=AsyncMock,
    ) as mock_readiness, patch(
        "am_i_blocked_worker.steps.bounded_probes.run",
        new_callable=AsyncMock,
        return_value=probe_report,
    ), patch(
        "am_i_blocked_worker.steps.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[],
    ):
        mock_readiness.return_value = MagicMock(
            to_dict=lambda: {
                "panos": {"available": False},
                "scm": {"available": False},
                "logscale": {"available": False},
                "sdwan": {"available": False},
                "torq": {"available": False},
            },
            available_sources=[],
        )

        result = await run_diagnostic(
            request_id=req_id,
            destination="https://api.example.com",
            port=None,
            time_window="last_15m",
            requester="eve",
            request_store=request_store,
            result_store=result_store,
            settings=settings,
        )

    assert result.verdict == Verdict.UNKNOWN
    assert request_store[req_id]["status"] == "complete"
