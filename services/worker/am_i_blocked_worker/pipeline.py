"""Diagnostic pipeline orchestrator - runs all steps in sequence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from am_i_blocked_core.config import Settings, get_settings
from am_i_blocked_core.enums import FailureCategory, FailureStage, RequestStatus
from am_i_blocked_core.logging_helpers import (
    bind_request_context,
    clear_request_context,
    get_logger,
)
from am_i_blocked_core.models import DiagnosticResult

from .steps import (
    authoritative_correlation,
    bounded_probes,
    classify,
    context_resolver,
    persist_and_report,
    source_readiness_check,
    validate_request,
)

logger = get_logger(__name__)


def _failure_category_for_stage(stage: FailureStage) -> FailureCategory:
    if stage == FailureStage.VALIDATE_REQUEST:
        return FailureCategory.VALIDATION
    if stage in (
        FailureStage.SOURCE_READINESS_CHECK,
        FailureStage.BOUNDED_PROBES,
        FailureStage.AUTHORITATIVE_CORRELATION,
    ):
        return FailureCategory.DEPENDENCY
    if stage == FailureStage.PERSIST_AND_REPORT:
        return FailureCategory.PERSISTENCE
    if stage in (
        FailureStage.CONTEXT_RESOLVER,
        FailureStage.CLASSIFY,
    ):
        return FailureCategory.PIPELINE_STEP
    return FailureCategory.INTERNAL


async def run_diagnostic(
    request_id: str,
    destination: str,
    port: int | None,
    time_window: str,
    requester: str,
    requester_hints: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> DiagnosticResult:
    """Run the full 7-step diagnostic pipeline.

    Steps:
    1. validate_request
    2. source_readiness_check
    3. context_resolver
    4. bounded_probes
    5. authoritative_correlation
    6. classify
    7. persist_and_report
    """
    if settings is None:
        settings = get_settings()

    bind_request_context(request_id=request_id, actor=requester)
    current_stage = FailureStage.PIPELINE

    try:
        current_stage = FailureStage.PIPELINE
        await persist_and_report._update_request_status_db(
            uuid.UUID(request_id),
            RequestStatus.RUNNING,
            settings=settings,
        )

        # --- Step 1: Validate ---
        current_stage = FailureStage.VALIDATE_REQUEST
        dest_type, normalized_dest, validated_port = validate_request.run(destination, port)

        # --- Step 2: Source readiness ---
        current_stage = FailureStage.SOURCE_READINESS_CHECK
        readiness_report = await source_readiness_check.run(settings)
        readiness = readiness_report.to_dict()

        # --- Step 3: Context resolution ---
        current_stage = FailureStage.CONTEXT_RESOLVER
        ctx = context_resolver.run(readiness, requester_hints)

        # --- Time window ---
        now = datetime.now(tz=UTC)
        deltas = {
            "now": 1 * 60,
            "last_15m": 15 * 60,
            "last_60m": 60 * 60,
        }
        seconds = deltas.get(time_window, 15 * 60)
        tw_start = now.timestamp() - seconds
        tw_end = now.timestamp()
        tw_start_str = datetime.fromtimestamp(tw_start, tz=UTC).isoformat()
        tw_end_str = datetime.fromtimestamp(tw_end, tz=UTC).isoformat()

        # --- Step 4: Bounded probes ---
        current_stage = FailureStage.BOUNDED_PROBES
        probe_report = await bounded_probes.run(
            destination=normalized_dest,
            port=validated_port,
            dest_type=dest_type.value,
            settings=settings,
        )

        # --- Step 5: Authoritative correlation ---
        current_stage = FailureStage.AUTHORITATIVE_CORRELATION
        evidence = await authoritative_correlation.run(
            request_id=request_id,
            destination=normalized_dest,
            port=validated_port,
            time_window_start=tw_start_str,
            time_window_end=tw_end_str,
            available_sources=readiness_report.available_sources,
            settings=settings,
        )

        # --- Step 6: Classify ---
        current_stage = FailureStage.CLASSIFY
        classification = classify.run(
            evidence=evidence,
            probe_results=probe_report.to_dict(),
            path_context=ctx.path_context,
            enforcement_plane=ctx.enforcement_plane,
            path_confidence=ctx.path_confidence,
            available_sources=readiness_report.available_sources,
        )

        # --- Step 7: Persist ---
        current_stage = FailureStage.PERSIST_AND_REPORT
        result = await persist_and_report.run(
            request_id=request_id,
            classification=classification,
            context=ctx,
            evidence=evidence,
            probe_results=probe_report.to_dict(),
            readiness=readiness,
        )

        return result

    except Exception as exc:
        logger.exception("diagnostic pipeline failed", request_id=request_id, error=str(exc))
        await persist_and_report._update_request_status_db(
            uuid.UUID(request_id),
            RequestStatus.FAILED,
            reason=str(exc),
            stage=current_stage,
            category=_failure_category_for_stage(current_stage),
            actor="worker",
            settings=settings,
        )
        raise
    finally:
        clear_request_context()
