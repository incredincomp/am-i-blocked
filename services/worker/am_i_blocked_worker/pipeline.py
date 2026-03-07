"""Diagnostic pipeline orchestrator - runs all steps in sequence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from am_i_blocked_core.config import Settings, get_settings
from am_i_blocked_core.enums import RequestStatus
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


async def run_diagnostic(
    request_id: str,
    destination: str,
    port: int | None,
    time_window: str,
    requester: str,
    request_store: dict,
    result_store: dict,
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

    try:
        # Mark running
        if request_id in request_store:
            request_store[request_id]["status"] = RequestStatus.RUNNING

        # --- Step 1: Validate ---
        dest_type, normalized_dest, validated_port = validate_request.run(destination, port)

        # --- Step 2: Source readiness ---
        readiness_report = await source_readiness_check.run(settings)
        readiness = readiness_report.to_dict()

        # --- Step 3: Context resolution ---
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
        probe_report = await bounded_probes.run(
            destination=normalized_dest,
            port=validated_port,
            dest_type=dest_type.value,
            settings=settings,
        )

        # --- Step 5: Authoritative correlation ---
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
        classification = classify.run(
            evidence=evidence,
            probe_results=probe_report.to_dict(),
            path_context=ctx.path_context,
            enforcement_plane=ctx.enforcement_plane,
            path_confidence=ctx.path_confidence,
            available_sources=readiness_report.available_sources,
        )

        # --- Step 7: Persist ---
        result = await persist_and_report.run(
            request_id=request_id,
            classification=classification,
            context=ctx,
            evidence=evidence,
            probe_results=probe_report.to_dict(),
            readiness=readiness,
            request_store=request_store,
            result_store=result_store,
        )

        return result

    except Exception as exc:
        logger.exception("diagnostic pipeline failed", request_id=request_id, error=str(exc))
        if request_id in request_store:
            request_store[request_id]["status"] = RequestStatus.FAILED
        raise
    finally:
        clear_request_context()
