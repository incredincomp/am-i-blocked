"""Shared pytest fixtures."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from am_i_blocked_core.enums import (
    EvidenceKind,
    EvidenceSource,
)
from am_i_blocked_core.models import EvidenceRecord

# ---------------------------------------------------------------------------
# Evidence fixtures
# ---------------------------------------------------------------------------


def _make_evidence(
    source: EvidenceSource,
    kind: EvidenceKind,
    normalized: dict[str, Any],
    request_id: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid.uuid4(),
        request_id=uuid.UUID(request_id or str(uuid.uuid4())),
        source=source,
        kind=kind,
        normalized=normalized,
        raw_ref=None,
        redacted={},
    )


@pytest.fixture
def cloud_deny_evidence() -> list[EvidenceRecord]:
    """Cloud policy deny from SCM."""
    return [
        _make_evidence(
            source=EvidenceSource.SCM,
            kind=EvidenceKind.TRAFFIC_LOG,
            normalized={
                "action": "deny",
                "rule_name": "block-all-saas",
                "destination": "example.com",
                "port": 443,
            },
        )
    ]


@pytest.fixture
def onprem_deny_evidence() -> list[EvidenceRecord]:
    """On-prem PAN-OS deny."""
    return [
        _make_evidence(
            source=EvidenceSource.PANOS,
            kind=EvidenceKind.TRAFFIC_LOG,
            normalized={
                "action": "deny",
                "rule_name": "block-external",
                "destination": "10.0.0.1",
                "port": 22,
            },
        )
    ]


@pytest.fixture
def sdwan_degraded_evidence() -> list[EvidenceRecord]:
    """SD-WAN degradation without any deny."""
    return [
        _make_evidence(
            source=EvidenceSource.SDWAN,
            kind=EvidenceKind.PATH_SIGNAL,
            normalized={
                "degraded": True,
                "site_id": "site-001",
                "health_score": 0.3,
            },
        )
    ]


@pytest.fixture
def incomplete_evidence() -> list[EvidenceRecord]:
    """Stub/incomplete evidence from all adapters."""
    return [
        _make_evidence(
            source=EvidenceSource.PANOS,
            kind=EvidenceKind.TRAFFIC_LOG,
            normalized={"stub": True, "message": "not wired"},
        ),
        _make_evidence(
            source=EvidenceSource.SCM,
            kind=EvidenceKind.TRAFFIC_LOG,
            normalized={"stub": True, "message": "not wired"},
        ),
    ]
