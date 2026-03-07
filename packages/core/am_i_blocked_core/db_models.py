"""SQLAlchemy 2.x ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RequestRow(Base):
    __tablename__ = "requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    requester: Mapped[str] = mapped_column(String(256), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_value: Mapped[str] = mapped_column(String(512), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")

    context: Mapped[ContextRow | None] = relationship(
        "ContextRow", back_populates="request", uselist=False
    )
    evidence: Mapped[list[EvidenceRow]] = relationship("EvidenceRow", back_populates="request")
    result: Mapped[ResultRow | None] = relationship(
        "ResultRow", back_populates="request", uselist=False
    )
    audit: Mapped[list[AuditRow]] = relationship("AuditRow", back_populates="request")


class ContextRow(Base):
    __tablename__ = "context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests.request_id"), nullable=False, unique=True
    )
    path_context: Mapped[str] = mapped_column(String(64), nullable=False)
    enforcement_plane: Mapped[str] = mapped_column(String(64), nullable=False)
    site: Mapped[str | None] = mapped_column(String(256), nullable=True)
    path_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signals_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    request: Mapped[RequestRow] = relationship("RequestRow", back_populates="context")


class EvidenceRow(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests.request_id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    request: Mapped[RequestRow] = relationship("RequestRow", back_populates="evidence")


class ResultRow(Base):
    __tablename__ = "result"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests.request_id"), primary_key=True
    )
    verdict: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_team: Mapped[str] = mapped_column(String(64), nullable=False)
    result_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_completeness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_steps_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    request: Mapped[RequestRow] = relationship("RequestRow", back_populates="result")


class AuditRow(Base):
    __tablename__ = "audit"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests.request_id"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    request: Mapped[RequestRow] = relationship("RequestRow", back_populates="audit")
