"""Unit tests for persistence/report step."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from am_i_blocked_core.enums import (
    EnforcementPlane,
    FailureCategory,
    FailureStage,
    OwnerTeam,
    PathContext,
    Verdict,
)
from am_i_blocked_core.models import RoutingRecommendation
from am_i_blocked_worker.steps import persist_and_report
from am_i_blocked_worker.steps.classify import ClassificationResult
from am_i_blocked_worker.steps.context_resolver import ContextResult


def _classification() -> ClassificationResult:
    return ClassificationResult(
        verdict=Verdict.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        owner_team=OwnerTeam.SECOPS,
        result_confidence=0.2,
        evidence_completeness=0.1,
        summary="Insufficient evidence",
        observed_facts=[],
        routing_recommendation=RoutingRecommendation(
            owner_team=OwnerTeam.SECOPS,
            reason="Telemetry incomplete",
            next_steps=["Check sources"],
        ),
    )


def _context() -> ContextResult:
    return ContextResult(
        path_context=PathContext.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        site=None,
        path_confidence=0.0,
        signals={},
    )


@pytest.mark.anyio
async def test_run_raises_when_db_write_fails():
    req_id = str(uuid.uuid4())

    with patch(
        "am_i_blocked_worker.steps.persist_and_report._persist_result_db",
        new_callable=AsyncMock,
        return_value=False,
    ) as persist_db:
        with pytest.raises(RuntimeError, match="result persistence unavailable"):
            await persist_and_report.run(
                request_id=req_id,
                classification=_classification(),
                context=_context(),
                evidence=[],
                probe_results={},
                readiness={},
            )

    persist_db.assert_awaited_once()


@pytest.mark.anyio
async def test_persist_result_db_returns_false_on_exception(monkeypatch):
    session = MagicMock()
    session.get = AsyncMock(side_effect=RuntimeError("db down"))
    session.commit = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        persist_and_report,
        "_get_session_factory",
        lambda _url: (lambda: _Ctx()),
    )

    settings = MagicMock(database_url="postgresql+psycopg://x/y")
    ok = await persist_and_report._persist_result_db(
        request_id=str(uuid.uuid4()),
        result=persist_and_report.build_result(
            request_id=str(uuid.uuid4()),
            classification=_classification(),
            context=_context(),
        ),
        bundle={"report": "x"},
        settings=settings,
    )
    assert ok is False


@pytest.mark.anyio
async def test_update_request_status_db_stores_structured_failure_metadata(monkeypatch):
    request_id = uuid.uuid4()
    captured_audit = []

    class _Session:
        def __init__(self):
            self.row = MagicMock()
            self.row.status = "running"

        async def get(self, model, key):
            if model.__name__ == "RequestRow" and key == request_id:
                return self.row
            return None

        def add(self, obj):
            captured_audit.append(obj)

        async def commit(self):
            return None

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        persist_and_report,
        "_get_session_factory",
        lambda _url: (lambda: _Ctx()),
    )

    settings = MagicMock(database_url="postgresql+psycopg://x/y")
    ok = await persist_and_report._update_request_status_db(
        request_id,
        "failed",
        reason="boom",
        stage=FailureStage.CLASSIFY,
        category=FailureCategory.PIPELINE_STEP,
        actor="worker",
        settings=settings,
    )

    assert ok is True
    assert len(captured_audit) == 1
    assert captured_audit[0].params_json == {
        "reason": "boom",
        "stage": "classify",
        "category": "pipeline_step",
    }


@pytest.mark.anyio
async def test_update_request_status_db_normalizes_unknown_failure_fields(monkeypatch):
    request_id = uuid.uuid4()
    captured_audit = []

    class _Session:
        def __init__(self):
            self.row = MagicMock()
            self.row.status = "running"

        async def get(self, model, key):
            if model.__name__ == "RequestRow" and key == request_id:
                return self.row
            return None

        def add(self, obj):
            captured_audit.append(obj)

        async def commit(self):
            return None

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        persist_and_report,
        "_get_session_factory",
        lambda _url: (lambda: _Ctx()),
    )

    settings = MagicMock(database_url="postgresql+psycopg://x/y")
    ok = await persist_and_report._update_request_status_db(
        request_id,
        "failed",
        reason="boom",
        stage="bad_stage",
        category="bad_category",
        actor="worker",
        settings=settings,
    )

    assert ok is True
    assert captured_audit[0].params_json["stage"] == "unknown"
    assert captured_audit[0].params_json["category"] == "unknown"
