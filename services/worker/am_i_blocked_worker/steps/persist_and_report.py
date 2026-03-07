"""Step 7: Persist results and generate the evidence bundle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from am_i_blocked_core.enums import RequestStatus
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import (
    DiagnosticResult,
    EvidenceRecord,
)

from .classify import ClassificationResult
from .context_resolver import ContextResult

logger = get_logger(__name__)


def build_result(
    request_id: str,
    classification: ClassificationResult,
    context: ContextResult,
) -> DiagnosticResult:
    """Assemble a DiagnosticResult from classification and context data."""
    return DiagnosticResult(
        request_id=uuid.UUID(request_id),
        verdict=classification.verdict,
        enforcement_plane=classification.enforcement_plane,
        path_context=context.path_context,
        path_confidence=context.path_confidence,
        result_confidence=classification.result_confidence,
        evidence_completeness=classification.evidence_completeness,
        summary=classification.summary,
        observed_facts=classification.observed_facts,
        routing_recommendation=classification.routing_recommendation,
        created_at=datetime.now(tz=UTC),
    )


def build_report_bundle(
    request_id: str,
    result: DiagnosticResult,
    evidence: list[EvidenceRecord],
    probe_results: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Generate a ticket-ready JSON evidence bundle.

    Raw evidence references are included for privileged consumers.
    Redacted evidence is safe for general distribution.
    """
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "request_id": str(request_id),
        "verdict": result.verdict.value,
        "enforcement_plane": result.enforcement_plane.value,
        "path_context": result.path_context.value,
        "path_confidence": result.path_confidence,
        "result_confidence": result.result_confidence,
        "evidence_completeness": result.evidence_completeness,
        "summary": result.summary,
        "observed_facts": [f.model_dump() for f in result.observed_facts],
        "routing_recommendation": result.routing_recommendation.model_dump(),
        "probe_results": probe_results,
        "source_readiness": readiness,
        "evidence_records": [
            {
                "evidence_id": str(e.evidence_id),
                "source": e.source.value,
                "kind": e.kind.value,
                "normalized": e.normalized,
                "redacted": e.redacted,
                # raw_ref is intentionally excluded from the public bundle
            }
            for e in evidence
        ],
    }


async def run(
    request_id: str,
    classification: ClassificationResult,
    context: ContextResult,
    evidence: list[EvidenceRecord],
    probe_results: dict[str, Any],
    readiness: dict[str, Any],
    request_store: dict,  # In-memory store - replace with DB session in prod
    result_store: dict,
) -> DiagnosticResult:
    """Persist the result and mark the request as complete.

    TODO: Replace in-memory stores with SQLAlchemy async session writes.
    """
    result = build_result(request_id, classification, context)
    _bundle = build_report_bundle(request_id, result, evidence, probe_results, readiness)
    # TODO: persist _bundle to the result table's report_json column

    # Update result store
    result_store[request_id] = result

    # Update request status
    if request_id in request_store:
        request_store[request_id]["status"] = RequestStatus.COMPLETE

    logger.info(
        "diagnostic complete",
        request_id=request_id,
        verdict=result.verdict.value,
        result_confidence=result.result_confidence,
        evidence_completeness=result.evidence_completeness,
    )

    return result
