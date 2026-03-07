"""Initial schema - requests, context, evidence, result, audit tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("requester", sa.String(256), nullable=False),
        sa.Column("destination_type", sa.String(64), nullable=False),
        sa.Column("destination_value", sa.String(512), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending"),
    )

    op.create_table(
        "context",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.request_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("path_context", sa.String(64), nullable=False),
        sa.Column("enforcement_plane", sa.String(64), nullable=False),
        sa.Column("site", sa.String(256), nullable=True),
        sa.Column("path_confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "signals_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_table(
        "evidence",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.request_id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column(
            "normalized_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("raw_ref", sa.Text(), nullable=True),
        sa.Column(
            "redacted_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index("ix_evidence_request_id", "evidence", ["request_id"])

    op.create_table(
        "result",
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.request_id"),
            primary_key=True,
        ),
        sa.Column("verdict", sa.String(64), nullable=False),
        sa.Column("owner_team", sa.String(64), nullable=False),
        sa.Column("result_confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence_completeness", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "next_steps_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "report_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_table(
        "audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("requests.request_id"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "params_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index("ix_audit_request_id", "audit", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_request_id", table_name="audit")
    op.drop_table("audit")
    op.drop_table("result")
    op.drop_index("ix_evidence_request_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("context")
    op.drop_table("requests")
