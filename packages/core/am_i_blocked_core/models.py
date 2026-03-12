"""Pydantic v2 models for API request/response schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .enums import (
    DestinationType,
    EnforcementPlane,
    EvidenceKind,
    EvidenceSource,
    OwnerTeam,
    PathContext,
    RequestStatus,
    TimeWindow,
    Verdict,
)

# ---------------------------------------------------------------------------
# Request / submission
# ---------------------------------------------------------------------------


class DiagnosticRequest(BaseModel):
    """Inbound request payload for POST /api/v1/am-i-blocked."""

    destination: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="URL, FQDN, or IP to diagnose",
    )
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Optional single destination port",
    )
    time_window: TimeWindow = Field(
        default=TimeWindow.LAST_15M,
        description="Bounded time window for log correlation",
    )

    @field_validator("destination")
    @classmethod
    def destination_not_range(cls, v: str) -> str:
        # Guardrail: reject CIDR ranges and obvious scanning patterns
        if "/" in v and not v.startswith("http"):
            raise ValueError("CIDR ranges are not permitted; provide a single destination.")
        return v.strip()


class DiagnosticRequestSubmitted(BaseModel):
    """Response body after successfully enqueuing a request."""

    request_id: uuid.UUID
    status: RequestStatus
    status_url: str


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class ContextRecord(BaseModel):
    path_context: PathContext
    enforcement_plane: EnforcementPlane
    site: str | None = None
    path_confidence: float = Field(ge=0.0, le=1.0)
    signals: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class EvidenceRecord(BaseModel):
    evidence_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    request_id: uuid.UUID
    source: EvidenceSource
    kind: EvidenceKind
    normalized: dict[str, Any] = Field(default_factory=dict)
    raw_ref: str | None = None
    # raw_ref points to a privileged store; redacted copy lives here
    redacted: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------


class ObservedFact(BaseModel):
    """A single piece of observed evidence contributing to the verdict."""

    source: EvidenceSource
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)


class RoutingRecommendation(BaseModel):
    owner_team: OwnerTeam
    reason: str
    next_steps: list[str] = Field(default_factory=list)


class SourceReadinessSummary(BaseModel):
    """Compact operator-facing summary of source readiness state."""

    total_sources: int = 0
    available_sources: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    unknown_sources: list[str] = Field(default_factory=list)


class SourceReadinessDetail(BaseModel):
    """Per-source readiness status/detail for operator diagnostics."""

    source: str
    status: str
    reason: str | None = None
    latency_ms: int | None = None


class ObservedFactSummary(BaseModel):
    """Compact operator-facing summary of observed fact authority mix."""

    total_facts: int = 0
    authoritative_facts: int = 0
    enrichment_only_facts: int = 0
    authoritative_sources: list[str] = Field(default_factory=list)
    enrichment_only_sources: list[str] = Field(default_factory=list)


class DiagnosticResult(BaseModel):
    request_id: uuid.UUID
    verdict: Verdict
    destination_type: DestinationType | None = None
    destination_value: str | None = None
    destination_port: int | None = None
    enforcement_plane: EnforcementPlane
    path_context: PathContext
    path_confidence: float = Field(ge=0.0, le=1.0)
    result_confidence: float = Field(ge=0.0, le=1.0)
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
    operator_handoff_summary: str | None = None
    summary: str
    unknown_reason_signals: list[str] = Field(default_factory=list)
    source_readiness_summary: SourceReadinessSummary = Field(default_factory=SourceReadinessSummary)
    source_readiness_details: list[SourceReadinessDetail] = Field(default_factory=list)
    observed_fact_summary: ObservedFactSummary = Field(default_factory=ObservedFactSummary)
    observed_facts: list[ObservedFact] = Field(default_factory=list)
    routing_recommendation: RoutingRecommendation
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditRecord(BaseModel):
    audit_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    request_id: uuid.UUID
    actor: str
    action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request status detail
# ---------------------------------------------------------------------------


class RequestDetail(BaseModel):
    request_id: uuid.UUID
    status: RequestStatus
    destination_type: DestinationType
    destination_value: str
    port: int | None
    time_window_start: datetime
    time_window_end: datetime
    requester: str
    created_at: datetime
    failure_reason: str | None = None
    failure_stage: str | None = None
    failure_category: str | None = None
    result: DiagnosticResult | None = None
