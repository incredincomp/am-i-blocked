"""Unit tests for authoritative correlation PAN-OS evidence handling."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from am_i_blocked_core.enums import (
    EnforcementPlane,
    EvidenceKind,
    EvidenceSource,
    PathContext,
    Verdict,
)
from am_i_blocked_core.models import EvidenceRecord
from am_i_blocked_worker.steps import authoritative_correlation, classify


def _ev(
    source: EvidenceSource,
    normalized: dict[str, object],
    *,
    request_id: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid.uuid4(),
        request_id=uuid.UUID(request_id or str(uuid.uuid4())),
        source=source,
        kind=EvidenceKind.TRAFFIC_LOG,
        normalized=normalized,
    )


class _FakeAdapter:
    def __init__(self, records: list[EvidenceRecord] | None = None, exc: Exception | None = None) -> None:
        self._records = records or []
        self._exc = exc

    async def query_evidence(self, **_: object) -> list[EvidenceRecord]:
        if self._exc is not None:
            raise self._exc
        return self._records


@pytest.mark.anyio
async def test_authoritative_correlation_keeps_panos_deny_records() -> None:
    req_id = str(uuid.uuid4())
    records = [
        _ev(
            EvidenceSource.PANOS,
            {"action": "deny", "action_raw": "deny", "authoritative": True, "rule_name": "block-a"},
            request_id=req_id,
        ),
        _ev(
            EvidenceSource.PANOS,
            {"action": "deny", "action_raw": "reset-client", "authoritative": True, "rule_name": "block-b"},
            request_id=req_id,
        ),
    ]

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=records),
    ):
        result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["panos"],
            settings=MagicMock(),
        )

    assert len(result) == 2
    assert all(r.source == EvidenceSource.PANOS for r in result)
    assert all(r.normalized.get("action") == "deny" for r in result)
    assert all(r.normalized.get("authoritative") is True for r in result)


@pytest.mark.anyio
async def test_authoritative_correlation_excludes_non_deny_and_malformed_panos() -> None:
    req_id = str(uuid.uuid4())
    records = [
        _ev(EvidenceSource.PANOS, {"action": "allow", "authoritative": True}, request_id=req_id),
        _ev(EvidenceSource.PANOS, {"action": "deny", "authoritative": False}, request_id=req_id),
        _ev(EvidenceSource.PANOS, {"authoritative": True}, request_id=req_id),
    ]

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=records),
    ):
        result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["panos"],
            settings=MagicMock(),
        )

    assert result == []


@pytest.mark.anyio
async def test_authoritative_correlation_timeout_and_no_match_return_empty() -> None:
    req_id = str(uuid.uuid4())

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(exc=TimeoutError("poll timeout")),
    ):
        timeout_result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["panos"],
            settings=MagicMock(),
        )
    assert timeout_result == []

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=[]),
    ):
        no_match_result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["panos"],
            settings=MagicMock(),
        )
    assert no_match_result == []


@pytest.mark.anyio
async def test_absent_panos_authoritative_evidence_classifies_unknown() -> None:
    req_id = str(uuid.uuid4())
    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=[]),
    ):
        evidence = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["panos"],
            settings=MagicMock(),
        )

    classification = classify.run(
        evidence=evidence,
        probe_results={},
        path_context=PathContext.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        path_confidence=0.4,
        available_sources=["panos"],
    )
    assert classification.verdict == Verdict.UNKNOWN


@pytest.mark.anyio
async def test_authoritative_correlation_keeps_only_authoritative_scm_deny_and_decrypt() -> None:
    req_id = str(uuid.uuid4())
    records = [
        _ev(
            EvidenceSource.SCM,
            {"action": "deny", "authoritative": True, "rule_name": "cloud-block"},
            request_id=req_id,
        ),
        _ev(
            EvidenceSource.SCM,
            {"decrypt_error": "cert_mismatch", "authoritative": True},
            request_id=req_id,
        ),
    ]
    records[1].kind = EvidenceKind.DECRYPT_LOG

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=records),
    ):
        result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["scm"],
            settings=MagicMock(),
        )

    assert len(result) == 2
    assert all(record.source == EvidenceSource.SCM for record in result)
    assert any(record.normalized.get("action") == "deny" for record in result)
    assert any(record.kind == EvidenceKind.DECRYPT_LOG for record in result)


@pytest.mark.anyio
async def test_authoritative_correlation_excludes_non_authoritative_scm_records() -> None:
    req_id = str(uuid.uuid4())
    decrypt_record = _ev(
        EvidenceSource.SCM,
        {"decrypt_error": "cert_mismatch", "authoritative": False},
        request_id=req_id,
    )
    decrypt_record.kind = EvidenceKind.DECRYPT_LOG
    records = [
        _ev(
            EvidenceSource.SCM,
            {"action": "deny", "authoritative": False, "rule_name": "cloud-block"},
            request_id=req_id,
        ),
        _ev(
            EvidenceSource.SCM,
            {"action": "allow", "authoritative": True, "rule_name": "cloud-allow"},
            request_id=req_id,
        ),
        decrypt_record,
    ]

    with patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakeAdapter(records=records),
    ):
        result = await authoritative_correlation.run(
            request_id=req_id,
            destination="api.example.com",
            port=443,
            time_window_start="2026-01-01T00:00:00+00:00",
            time_window_end="2026-01-01T00:15:00+00:00",
            available_sources=["scm"],
            settings=MagicMock(),
        )

    assert result == []
