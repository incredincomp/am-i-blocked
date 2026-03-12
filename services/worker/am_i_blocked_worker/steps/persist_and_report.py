"""Step 7: Persist results and generate the evidence bundle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from am_i_blocked_core.config import Settings, get_settings
from am_i_blocked_core.db_models import AuditRow, RequestRow, ResultRow
from am_i_blocked_core.enums import FailureCategory, FailureStage, RequestStatus
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import (
    DiagnosticResult,
    EvidenceRecord,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .classify import ClassificationResult
from .context_resolver import ContextResult

logger = get_logger(__name__)
_engines: dict[str, AsyncEngine] = {}
_sessions: dict[str, async_sessionmaker] = {}


def _normalize_failure_stage(stage: str | FailureStage | None) -> FailureStage:
    if isinstance(stage, FailureStage):
        return stage
    if isinstance(stage, str):
        try:
            return FailureStage(stage)
        except ValueError:
            return FailureStage.UNKNOWN
    return FailureStage.UNKNOWN


def _normalize_failure_category(category: str | FailureCategory | None) -> FailureCategory:
    if isinstance(category, FailureCategory):
        return category
    if isinstance(category, str):
        try:
            return FailureCategory(category)
        except ValueError:
            return FailureCategory.UNKNOWN
    return FailureCategory.UNKNOWN


def _get_session_factory(database_url: str) -> async_sessionmaker:
    if database_url not in _sessions:
        if database_url not in _engines:
            _engines[database_url] = create_async_engine(database_url, pool_pre_ping=True)
        _sessions[database_url] = async_sessionmaker(
            _engines[database_url],
            expire_on_commit=False,
        )
    return _sessions[database_url]


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
    observed_facts = [f.model_dump() for f in result.observed_facts]
    available_sources = sorted(
        source
        for source, value in readiness.items()
        if isinstance(source, str) and source.strip() and isinstance(value, dict) and value.get("available") is True
    )
    unavailable_sources = sorted(
        source
        for source, value in readiness.items()
        if isinstance(source, str) and source.strip() and isinstance(value, dict) and value.get("available") is False
    )
    authoritative_fact_count = sum(
        1
        for fact in observed_facts
        if not (
            isinstance(fact.get("detail"), dict)
            and (
                fact["detail"].get("classification_role") == "enrichment_only_unverified"
                or fact["detail"].get("authoritative") is False
            )
        )
    )
    operator_handoff_summary = (
        f"verdict={result.verdict.value}; path={result.path_context.value}; "
        f"enforcement={result.enforcement_plane.value}; authoritative_facts={authoritative_fact_count}; "
        f"ready_sources={len(available_sources)}; unavailable_sources={len(unavailable_sources)}; "
        f"routing_reason={result.routing_recommendation.reason}"
    )

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
        "operator_handoff_summary": operator_handoff_summary,
        "summary": result.summary,
        "observed_facts": observed_facts,
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
) -> DiagnosticResult:
    """Persist the result and mark the request as complete."""
    result = build_result(request_id, classification, context)
    bundle = build_report_bundle(request_id, result, evidence, probe_results, readiness)
    persisted = await _persist_result_db(request_id, result, bundle)
    if not persisted:
        raise RuntimeError("result persistence unavailable")

    logger.info(
        "diagnostic complete",
        request_id=request_id,
        verdict=result.verdict.value,
        result_confidence=result.result_confidence,
        evidence_completeness=result.evidence_completeness,
    )

    return result


async def _persist_result_db(
    request_id: str,
    result: DiagnosticResult,
    bundle: dict[str, Any],
    settings: Settings | None = None,
) -> bool:
    """Persist result + request status in Postgres."""
    if settings is None:
        settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    req_uuid = uuid.UUID(request_id)

    try:
        async with session_factory() as session:
            request_row = await session.get(RequestRow, req_uuid)
            if request_row is not None:
                request_row.status = RequestStatus.COMPLETE.value

            result_row = await session.get(ResultRow, req_uuid)
            if result_row is None:
                result_row = ResultRow(
                    request_id=req_uuid,
                    verdict=result.verdict.value,
                    owner_team=result.routing_recommendation.owner_team.value,
                    result_confidence=result.result_confidence,
                    evidence_completeness=result.evidence_completeness,
                    summary=result.summary,
                    next_steps_json=result.routing_recommendation.next_steps,
                    report_json=bundle,
                )
                session.add(result_row)
            else:
                result_row.verdict = result.verdict.value
                result_row.owner_team = result.routing_recommendation.owner_team.value
                result_row.result_confidence = result.result_confidence
                result_row.evidence_completeness = result.evidence_completeness
                result_row.summary = result.summary
                result_row.next_steps_json = result.routing_recommendation.next_steps
                result_row.report_json = bundle

            await session.commit()
        return True
    except Exception as exc:
        logger.warning(
            "result persistence failed",
            request_id=request_id,
            error=str(exc),
        )
        return False


async def _update_request_status_db(
    request_id: uuid.UUID,
    status_value: str | RequestStatus,
    reason: str | None = None,
    stage: str | FailureStage | None = None,
    category: str | FailureCategory | None = None,
    actor: str = "worker",
    settings: Settings | None = None,
) -> bool:
    """Persist request status in Postgres."""
    if settings is None:
        settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    normalized = status_value.value if isinstance(status_value, RequestStatus) else status_value
    try:
        async with session_factory() as session:
            row = await session.get(RequestRow, request_id)
            if row is None:
                return False
            row.status = normalized
            if normalized == RequestStatus.FAILED.value:
                normalized_stage = _normalize_failure_stage(stage).value
                normalized_category = _normalize_failure_category(category).value
                params = {
                    "reason": reason or "unknown",
                    "stage": normalized_stage,
                    "category": normalized_category,
                }
                session.add(
                    AuditRow(
                        request_id=request_id,
                        actor=actor,
                        action="request_failed",
                        params_json=params,
                    )
                )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning(
            "request status persistence failed",
            request_id=str(request_id),
            status=normalized,
            error=str(exc),
        )
        return False
