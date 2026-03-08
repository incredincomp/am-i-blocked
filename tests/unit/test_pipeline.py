"""Unit tests for pipeline failure metadata tagging."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from am_i_blocked_core.enums import (
    DestinationType,
    EnforcementPlane,
    FailureCategory,
    FailureStage,
    PathContext,
    RequestStatus,
)
from am_i_blocked_worker import pipeline


@pytest.mark.anyio
async def test_validate_request_failure_records_validate_stage_and_validation_category():
    req_id = str(uuid.uuid4())
    settings = MagicMock()

    with patch(
        "am_i_blocked_worker.pipeline.persist_and_report._update_request_status_db",
        new_callable=AsyncMock,
    ) as update_status, patch(
        "am_i_blocked_worker.pipeline.validate_request.run",
        side_effect=ValueError("invalid destination"),
    ):
        with pytest.raises(ValueError):
            await pipeline.run_diagnostic(
                request_id=req_id,
                destination="bad input",
                port=443,
                time_window="last_15m",
                requester="tester",
                settings=settings,
            )

    assert update_status.await_count == 2
    failed_call = update_status.await_args_list[1]
    assert failed_call.args[1] == RequestStatus.FAILED
    assert failed_call.kwargs["stage"] == FailureStage.VALIDATE_REQUEST
    assert failed_call.kwargs["category"] == FailureCategory.VALIDATION


@pytest.mark.anyio
async def test_authoritative_correlation_failure_records_dependency_category():
    req_id = str(uuid.uuid4())
    settings = MagicMock()
    readiness_report = MagicMock(
        to_dict=lambda: {"panos": {"available": True}},
        available_sources=["panos"],
    )
    context = MagicMock(
        path_context=PathContext.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        path_confidence=0.3,
    )
    probe_report = MagicMock(to_dict=lambda: {"tcp": {"success": True}})

    with patch(
        "am_i_blocked_worker.pipeline.persist_and_report._update_request_status_db",
        new_callable=AsyncMock,
    ) as update_status, patch(
        "am_i_blocked_worker.pipeline.validate_request.run",
        return_value=(DestinationType.FQDN, "api.example.com", 443),
    ), patch(
        "am_i_blocked_worker.pipeline.source_readiness_check.run",
        new_callable=AsyncMock,
        return_value=readiness_report,
    ), patch(
        "am_i_blocked_worker.pipeline.context_resolver.run",
        return_value=context,
    ), patch(
        "am_i_blocked_worker.pipeline.bounded_probes.run",
        new_callable=AsyncMock,
        return_value=probe_report,
    ), patch(
        "am_i_blocked_worker.pipeline.authoritative_correlation.run",
        new_callable=AsyncMock,
        side_effect=RuntimeError("adapter unavailable"),
    ):
        with pytest.raises(RuntimeError):
            await pipeline.run_diagnostic(
                request_id=req_id,
                destination="api.example.com",
                port=443,
                time_window="last_15m",
                requester="tester",
                settings=settings,
            )

    assert update_status.await_count == 2
    failed_call = update_status.await_args_list[1]
    assert failed_call.args[1] == RequestStatus.FAILED
    assert failed_call.kwargs["stage"] == FailureStage.AUTHORITATIVE_CORRELATION
    assert failed_call.kwargs["category"] == FailureCategory.DEPENDENCY


@pytest.mark.anyio
async def test_persist_failure_records_persistence_category():
    req_id = str(uuid.uuid4())
    settings = MagicMock()
    readiness_report = MagicMock(
        to_dict=lambda: {"panos": {"available": True}},
        available_sources=["panos"],
    )
    context = MagicMock(
        path_context=PathContext.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        path_confidence=0.3,
    )
    probe_report = MagicMock(to_dict=lambda: {"tcp": {"success": True}})
    classification = MagicMock()

    with patch(
        "am_i_blocked_worker.pipeline.persist_and_report._update_request_status_db",
        new_callable=AsyncMock,
    ) as update_status, patch(
        "am_i_blocked_worker.pipeline.validate_request.run",
        return_value=(DestinationType.FQDN, "api.example.com", 443),
    ), patch(
        "am_i_blocked_worker.pipeline.source_readiness_check.run",
        new_callable=AsyncMock,
        return_value=readiness_report,
    ), patch(
        "am_i_blocked_worker.pipeline.context_resolver.run",
        return_value=context,
    ), patch(
        "am_i_blocked_worker.pipeline.bounded_probes.run",
        new_callable=AsyncMock,
        return_value=probe_report,
    ), patch(
        "am_i_blocked_worker.pipeline.authoritative_correlation.run",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "am_i_blocked_worker.pipeline.classify.run",
        return_value=classification,
    ), patch(
        "am_i_blocked_worker.pipeline.persist_and_report.run",
        new_callable=AsyncMock,
        side_effect=RuntimeError("result persistence unavailable"),
    ):
        with pytest.raises(RuntimeError):
            await pipeline.run_diagnostic(
                request_id=req_id,
                destination="api.example.com",
                port=443,
                time_window="last_15m",
                requester="tester",
                settings=settings,
            )

    assert update_status.await_count == 2
    failed_call = update_status.await_args_list[1]
    assert failed_call.args[1] == RequestStatus.FAILED
    assert failed_call.kwargs["stage"] == FailureStage.PERSIST_AND_REPORT
    assert failed_call.kwargs["category"] == FailureCategory.PERSISTENCE
