"""API routes for am-i-blocked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from am_i_blocked_core.config import get_settings
from am_i_blocked_core.db_models import AuditRow, RequestRow, ResultRow
from am_i_blocked_core.enums import (
    DestinationType,
    FailureCategory,
    FailureStage,
    RequestStatus,
)
from am_i_blocked_core.health_checks import (
    check_database_readiness,
    check_redis_readiness,
)
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import (
    DiagnosticRequest,
    DiagnosticRequestSubmitted,
    DiagnosticResult,
    RequestDetail,
)
from am_i_blocked_core.queue import enqueue_job
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

logger = get_logger(__name__)
router = APIRouter(tags=["diagnostic"])

_engines: dict[str, AsyncEngine] = {}
_sessions: dict[str, async_sessionmaker] = {}


class DependencyUnavailableError(RuntimeError):
    """Raised when Postgres/Redis dependencies are unavailable for a request."""


def _coerce_confidence(value: object, default: float = 0.0) -> float:
    try:
        coerced = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, coerced))


def _normalize_optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalize_optional_destination_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _normalize_optional_destination_port(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _normalize_optional_destination_type(value: object) -> DestinationType | None:
    if isinstance(value, DestinationType):
        return value
    if isinstance(value, str):
        try:
            return DestinationType(value)
        except ValueError:
            return None
    return None


def _normalize_optional_handoff_summary(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_optional_request_status(value: object) -> RequestStatus | None:
    if isinstance(value, RequestStatus):
        return value
    if isinstance(value, str):
        try:
            return RequestStatus(value)
        except ValueError:
            return None
    return None


def _normalize_optional_failure_stage(value: object) -> str | None:
    if isinstance(value, FailureStage):
        return value.value
    if isinstance(value, str) and value.strip():
        try:
            return FailureStage(value).value
        except ValueError:
            return FailureStage.UNKNOWN.value
    return None


def _normalize_optional_failure_category(value: object) -> str | None:
    if isinstance(value, FailureCategory):
        return value.value
    if isinstance(value, str) and value.strip():
        try:
            return FailureCategory(value).value
        except ValueError:
            return FailureCategory.UNKNOWN.value
    return None


def _format_handoff_destination_values(
    destination_value: str | None,
    destination_port: int | None,
    destination_type: DestinationType | None,
) -> str:
    if not destination_value:
        return "n/a"
    destination = destination_value
    if destination_port is not None:
        destination = f"{destination}:{destination_port}"
    if destination_type is not None:
        destination = f"{destination} ({destination_type.value})"
    return destination


def _format_handoff_destination(result: DiagnosticResult) -> str:
    return _format_handoff_destination_values(
        result.destination_value,
        result.destination_port,
        result.destination_type,
    )


def _format_handoff_time_window_values(
    start_time: datetime | None,
    end_time: datetime | None,
) -> str:
    start = start_time.isoformat() if start_time else None
    end = end_time.isoformat() if end_time else None
    if start and end:
        return f"{start} to {end}"
    if start:
        return f"start {start}"
    if end:
        return f"end {end}"
    return "n/a"


def _format_handoff_time_window(result: DiagnosticResult) -> str:
    return _format_handoff_time_window_values(
        result.time_window_start,
        result.time_window_end,
    )


def _build_handoff_note(result: DiagnosticResult) -> str:
    recommendation = result.routing_recommendation
    reason = recommendation.reason.strip() if recommendation.reason.strip() else "n/a"
    next_steps = [step.strip() for step in recommendation.next_steps if step.strip()]

    def _join_or_none(values: list[str]) -> str:
        return ", ".join(values) if values else "none"

    evidence_summary = result.observed_fact_summary
    readiness_summary = result.source_readiness_summary

    lines = [
        "Am I Blocked - Operator Handoff",
        f"Request ID: {result.request_id}",
        f"Verdict: {result.verdict}",
        f"Summary: {result.summary}",
    ]
    if isinstance(result.operator_handoff_summary, str) and result.operator_handoff_summary.strip():
        lines.append(f"Operator handoff summary: {result.operator_handoff_summary.strip()}")

    lines.extend(
        [
            "",
            "Context:",
            f"- Destination: {_format_handoff_destination(result)}",
            f"- Time window: {_format_handoff_time_window(result)}",
            f"- Path context: {result.path_context}",
            f"- Enforcement plane: {result.enforcement_plane}",
            "",
            "Routing:",
            f"- Owner team: {recommendation.owner_team}",
            f"- Reason: {reason}",
            "",
            "Evidence snapshot:",
            (
                "- Observed facts: "
                f"total={evidence_summary.total_facts}, "
                f"authoritative={evidence_summary.authoritative_facts}, "
                f"enrichment_only={evidence_summary.enrichment_only_facts}"
            ),
            f"- Authoritative sources: {_join_or_none(evidence_summary.authoritative_sources)}",
            f"- Enrichment-only sources: {_join_or_none(evidence_summary.enrichment_only_sources)}",
            "",
            "Readiness snapshot:",
            f"- Sources checked: {readiness_summary.total_sources}",
            f"- Available: {_join_or_none(readiness_summary.available_sources)}",
            f"- Unavailable: {_join_or_none(readiness_summary.unavailable_sources)}",
            f"- Unknown: {_join_or_none(readiness_summary.unknown_sources)}",
        ]
    )

    if result.verdict.value == "unknown" and result.unknown_reason_signals:
        lines.extend(["", "Unknown signals:"])
        lines.extend(f"- {signal}" for signal in result.unknown_reason_signals)

    lines.extend(["", "Next steps:"])
    if next_steps:
        lines.extend(f"- {step}" for step in next_steps)
    else:
        lines.append("- none provided")

    return "\n".join(lines)


def _build_failed_request_handoff_note(record: dict[str, Any]) -> str:
    request_id = record.get("request_id")
    destination_type = _normalize_optional_destination_type(record.get("destination_type"))
    destination_value = _normalize_optional_destination_value(record.get("destination_value"))
    destination_port = _normalize_optional_destination_port(record.get("port"))
    time_window_start = _normalize_optional_datetime(record.get("time_window_start"))
    time_window_end = _normalize_optional_datetime(record.get("time_window_end"))
    failure_stage = _normalize_optional_failure_stage(record.get("failure_stage"))
    failure_category = _normalize_optional_failure_category(record.get("failure_category"))
    failure_reason = (
        record.get("failure_reason").strip()
        if isinstance(record.get("failure_reason"), str) and record.get("failure_reason").strip()
        else None
    )

    lines = [
        "Am I Blocked - Failed Request Handoff",
        f"Request ID: {request_id}",
        "Status: failed",
        "",
        "Context:",
        (
            "- Destination: "
            f"{_format_handoff_destination_values(destination_value, destination_port, destination_type)}"
        ),
        f"- Time window: {_format_handoff_time_window_values(time_window_start, time_window_end)}",
    ]

    if failure_stage or failure_category or failure_reason:
        lines.extend(["", "Failure diagnostics:"])
        if failure_stage:
            lines.append(f"- Stage: {failure_stage}")
        if failure_category:
            lines.append(f"- Category: {failure_category}")
        if failure_reason:
            lines.append(f"- Reason: {failure_reason}")

    return "\n".join(lines)


def _derive_unknown_reason_signals(
    report: dict[str, Any],
    path_confidence: float,
    evidence_completeness: float,
) -> list[str]:
    signals: list[str] = []
    summary = report.get("summary")
    if isinstance(summary, str):
        lowered = summary.lower()
        if "insufficient evidence" in lowered or "no policy deny" in lowered:
            signals.append(
                "No authoritative deny evidence was found; this is not confirmation that access is allowed."
            )

    readiness = report.get("source_readiness")
    if isinstance(readiness, dict):
        readiness_incomplete = False
        for value in readiness.values():
            if isinstance(value, dict) and value.get("available") is False:
                readiness_incomplete = True
                break
        if readiness_incomplete:
            signals.append("One or more data sources were degraded or unavailable, which reduced confidence.")

    if path_confidence < 0.5:
        signals.append("Path context confidence is low, so route or policy context may be incomplete.")
    if evidence_completeness < 0.6:
        signals.append("Bounded checks were inconclusive or incomplete for this time window.")

    return list(dict.fromkeys(signals))


def _summarize_source_readiness(report: dict[str, Any]) -> dict[str, Any]:
    """Build a compact readiness summary from persisted report payload."""
    readiness = report.get("source_readiness")
    if not isinstance(readiness, dict):
        return {
            "total_sources": 0,
            "available_sources": [],
            "unavailable_sources": [],
            "unknown_sources": [],
        }

    available_sources: list[str] = []
    unavailable_sources: list[str] = []
    unknown_sources: list[str] = []

    for source, value in readiness.items():
        if not isinstance(source, str) or not source.strip():
            continue
        if isinstance(value, dict):
            available_flag = value.get("available")
            if available_flag is True:
                available_sources.append(source)
            elif available_flag is False:
                unavailable_sources.append(source)
            else:
                unknown_sources.append(source)
        else:
            unknown_sources.append(source)

    return {
        "total_sources": len(available_sources) + len(unavailable_sources) + len(unknown_sources),
        "available_sources": sorted(available_sources),
        "unavailable_sources": sorted(unavailable_sources),
        "unknown_sources": sorted(unknown_sources),
    }


def _build_source_readiness_details(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Build compact per-source readiness entries for operator rendering."""
    readiness = report.get("source_readiness")
    if not isinstance(readiness, dict):
        return []

    details: list[dict[str, Any]] = []
    for source, value in sorted(readiness.items()):
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(value, dict):
            continue

        has_meaningful_data = any(
            key in value for key in ("status", "reason", "available", "latency_ms")
        )
        if not has_meaningful_data:
            continue

        status_raw = value.get("status")
        if isinstance(status_raw, str) and status_raw.strip():
            status = status_raw.strip()
        else:
            available = value.get("available")
            if available is True:
                status = "ready"
            elif available is False:
                status = "unavailable"
            else:
                status = "unknown"

        reason_raw = value.get("reason")
        reason = reason_raw.strip() if isinstance(reason_raw, str) and reason_raw.strip() else None

        latency = value.get("latency_ms")
        latency_ms = latency if isinstance(latency, int) and latency >= 0 else None

        details.append(
            {
                "source": source.strip(),
                "status": status,
                "reason": reason,
                "latency_ms": latency_ms,
            }
        )
    return details


def _summarize_observed_facts(report: dict[str, Any]) -> dict[str, Any]:
    """Build a compact authority/enrichment summary from observed facts."""
    observed_facts = report.get("observed_facts")
    if not isinstance(observed_facts, list):
        return {
            "total_facts": 0,
            "authoritative_facts": 0,
            "enrichment_only_facts": 0,
            "authoritative_sources": [],
            "enrichment_only_sources": [],
        }

    total_facts = 0
    authoritative_facts = 0
    enrichment_only_facts = 0
    authoritative_sources: set[str] = set()
    enrichment_only_sources: set[str] = set()

    for fact in observed_facts:
        if not isinstance(fact, dict):
            continue
        total_facts += 1
        source = fact.get("source")
        normalized_source = source.strip() if isinstance(source, str) and source.strip() else None

        detail = fact.get("detail")
        detail_dict = detail if isinstance(detail, dict) else {}
        is_enrichment = (
            detail_dict.get("classification_role") == "enrichment_only_unverified"
            or detail_dict.get("authoritative") is False
        )

        if is_enrichment:
            enrichment_only_facts += 1
            if normalized_source:
                enrichment_only_sources.add(normalized_source)
        else:
            authoritative_facts += 1
            if normalized_source:
                authoritative_sources.add(normalized_source)

    return {
        "total_facts": total_facts,
        "authoritative_facts": authoritative_facts,
        "enrichment_only_facts": enrichment_only_facts,
        "authoritative_sources": sorted(authoritative_sources),
        "enrichment_only_sources": sorted(enrichment_only_sources),
    }


def _normalize_routing_recommendation(report: dict[str, Any], row: ResultRow) -> dict[str, Any]:
    """Return a model-safe routing recommendation payload from persisted report data."""
    fallback_reason = "loaded from persisted result"
    recommendation = report.get("routing_recommendation")

    if not isinstance(recommendation, dict):
        return {
            "owner_team": row.owner_team,
            "reason": fallback_reason,
            "next_steps": row.next_steps_json or [],
        }

    owner_team_raw = recommendation.get("owner_team")
    owner_team = owner_team_raw.strip() if isinstance(owner_team_raw, str) and owner_team_raw.strip() else row.owner_team

    reason_raw = recommendation.get("reason")
    reason = reason_raw.strip() if isinstance(reason_raw, str) and reason_raw.strip() else fallback_reason

    next_steps_raw = recommendation.get("next_steps")
    if isinstance(next_steps_raw, list):
        next_steps = [step.strip() for step in next_steps_raw if isinstance(step, str) and step.strip()]
    else:
        next_steps = []

    return {
        "owner_team": owner_team,
        "reason": reason,
        "next_steps": next_steps,
    }


def _get_session_factory(database_url: str) -> async_sessionmaker:
    if database_url not in _sessions:
        if database_url not in _engines:
            _engines[database_url] = create_async_engine(
                database_url,
                pool_pre_ping=True,
            )
        _sessions[database_url] = async_sessionmaker(
            _engines[database_url],
            expire_on_commit=False,
        )
    return _sessions[database_url]


def _get_requester(request: Request) -> str:
    """Extract requester identity from reverse-proxy injected header."""
    settings = get_settings()
    return request.headers.get(settings.app_identity_header, settings.anonymous_user)


def _classify_destination(dest: str) -> DestinationType:
    import ipaddress
    try:
        ipaddress.ip_address(dest)
        return DestinationType.IP
    except ValueError:
        pass
    if dest.startswith("http://") or dest.startswith("https://"):
        return DestinationType.URL
    if "." in dest:
        return DestinationType.FQDN
    return DestinationType.UNKNOWN


def _time_window_bounds(time_window: str) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    deltas = {
        "now": timedelta(minutes=1),
        "last_15m": timedelta(minutes=15),
        "last_60m": timedelta(hours=1),
    }
    delta = deltas.get(time_window, timedelta(minutes=15))
    return now - delta, now


async def _persist_request_db(record: dict) -> bool:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            session.add(
                RequestRow(
                    request_id=record["request_id"],
                    requester=record["requester"],
                    destination_type=record["destination_type"].value,
                    destination_value=record["destination_value"],
                    port=record["port"],
                    time_window_start=record["time_window_start"],
                    time_window_end=record["time_window_end"],
                    status=record["status"].value,
                )
            )
            session.add(
                AuditRow(
                    request_id=record["request_id"],
                    actor="api",
                    action="request_submitted",
                    params_json={"status": record["status"].value},
                )
            )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning("request persistence failed", request_id=str(record["request_id"]), error=str(exc))
        return False


async def _update_request_status_db(
    request_id: uuid.UUID,
    status_value: RequestStatus,
    reason: str | None = None,
    stage: str | FailureStage | None = None,
    category: str | FailureCategory | None = None,
) -> None:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            row = await session.get(RequestRow, request_id)
            if row is None:
                return
            row.status = status_value.value
            if status_value == RequestStatus.FAILED:
                if isinstance(stage, FailureStage):
                    normalized_stage = stage.value
                elif isinstance(stage, str):
                    try:
                        normalized_stage = FailureStage(stage).value
                    except ValueError:
                        normalized_stage = FailureStage.UNKNOWN.value
                else:
                    normalized_stage = FailureStage.QUEUE_ENQUEUE.value

                if isinstance(category, FailureCategory):
                    normalized_category = category.value
                elif isinstance(category, str):
                    try:
                        normalized_category = FailureCategory(category).value
                    except ValueError:
                        normalized_category = FailureCategory.UNKNOWN.value
                else:
                    normalized_category = FailureCategory.DEPENDENCY.value
                params = {
                    "reason": reason or "queue unavailable",
                    "stage": normalized_stage,
                    "category": normalized_category,
                }
                session.add(
                    AuditRow(
                        request_id=request_id,
                        actor="api",
                        action="request_failed",
                        params_json=params,
                    )
                )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "request status update failed",
            request_id=str(request_id),
            status=status_value.value,
            error=str(exc),
        )


def _extract_failure_metadata(params: dict | None) -> dict[str, str | None]:
    metadata: dict[str, str | None] = {
        "reason": None,
        "stage": None,
        "category": None,
    }
    if not params:
        return metadata

    for key in ("reason", "error", "message"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            metadata["reason"] = value
            break

    for key in ("stage", "failure_stage"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            try:
                metadata["stage"] = FailureStage(value).value
            except ValueError:
                metadata["stage"] = FailureStage.UNKNOWN.value
            break

    for key in ("category", "failure_category"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            try:
                metadata["category"] = FailureCategory(value).value
            except ValueError:
                metadata["category"] = FailureCategory.UNKNOWN.value
            break
    return metadata


async def _load_failure_metadata(request_id: uuid.UUID) -> dict[str, str | None]:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            stmt = (
                select(AuditRow)
                .where(AuditRow.request_id == request_id)
                .where(AuditRow.action == "request_failed")
                .order_by(AuditRow.timestamp.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return {"reason": None, "stage": None, "category": None}
        return _extract_failure_metadata(row.params_json)
    except Exception as exc:
        raise DependencyUnavailableError(f"database unavailable: {exc}") from exc


async def _load_request_audit_events(request_id: uuid.UUID) -> list[dict[str, Any]]:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            stmt = (
                select(AuditRow)
                .where(AuditRow.request_id == request_id)
                .order_by(AuditRow.timestamp.asc())
            )
            rows = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "action": row.action,
                "actor": row.actor,
                "timestamp": row.timestamp,
                "params": row.params_json if isinstance(row.params_json, dict) else {},
            }
            for row in rows
        ]
    except Exception as exc:
        raise DependencyUnavailableError(f"database unavailable: {exc}") from exc


async def _load_request_record(request_id: uuid.UUID) -> dict | None:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            row = await session.get(RequestRow, request_id)
        if row is None:
            return None
        return {
            "request_id": row.request_id,
            "status": RequestStatus(row.status),
            "destination_type": DestinationType(row.destination_type),
            "destination_value": row.destination_value,
            "port": row.port,
            "time_window_start": row.time_window_start,
            "time_window_end": row.time_window_end,
            "requester": row.requester,
            "created_at": row.created_at,
            **(
                {
                    "failure_reason": (failure := await _load_failure_metadata(request_id)).get("reason"),
                    "failure_stage": failure.get("stage"),
                    "failure_category": failure.get("category"),
                }
                if row.status == RequestStatus.FAILED.value
                else {
                    "failure_reason": None,
                    "failure_stage": None,
                    "failure_category": None,
                }
            ),
        }
    except Exception as exc:
        raise DependencyUnavailableError(f"database unavailable: {exc}") from exc


async def _load_result_record(request_id: uuid.UUID) -> DiagnosticResult | None:
    settings = get_settings()
    session_factory = _get_session_factory(settings.database_url)
    try:
        async with session_factory() as session:
            row = await session.get(ResultRow, request_id)
        if row is None:
            return None
        report = row.report_json or {}
        path_confidence = _coerce_confidence(report.get("path_confidence"), default=0.0)
        result_confidence = _coerce_confidence(row.result_confidence, default=0.0)
        evidence_completeness = _coerce_confidence(row.evidence_completeness, default=0.0)
        verdict = str(row.verdict)
        unknown_reason_signals: list[str] = []
        if verdict == "unknown":
            report_unknown_signals = report.get("unknown_reason_signals")
            if isinstance(report_unknown_signals, list):
                unknown_reason_signals = [
                    item.strip()
                    for item in report_unknown_signals
                    if isinstance(item, str) and item.strip()
                ]
            if not unknown_reason_signals:
                report_with_summary = dict(report)
                if "summary" not in report_with_summary:
                    report_with_summary["summary"] = row.summary
                unknown_reason_signals = _derive_unknown_reason_signals(
                    report=report_with_summary,
                    path_confidence=path_confidence,
                    evidence_completeness=evidence_completeness,
                )
        payload = {
            "request_id": str(request_id),
            "verdict": verdict,
            "destination_type": None,
            "destination_value": None,
            "destination_port": None,
            "enforcement_plane": report.get("enforcement_plane", "unknown"),
            "path_context": report.get("path_context", "unknown"),
            "path_confidence": path_confidence,
            "result_confidence": result_confidence,
            "evidence_completeness": evidence_completeness,
            "time_window_start": None,
            "time_window_end": None,
            "operator_handoff_summary": (
                report.get("operator_handoff_summary").strip()
                if isinstance(report.get("operator_handoff_summary"), str)
                and report.get("operator_handoff_summary").strip()
                else None
            ),
            "summary": row.summary,
            "unknown_reason_signals": unknown_reason_signals,
            "source_readiness_summary": _summarize_source_readiness(report),
            "source_readiness_details": _build_source_readiness_details(report),
            "observed_fact_summary": _summarize_observed_facts(report),
            "observed_facts": report.get("observed_facts", []),
            "routing_recommendation": _normalize_routing_recommendation(report, row),
            "created_at": report.get("generated_at", datetime.now(tz=UTC).isoformat()),
        }
        return DiagnosticResult.model_validate(payload)
    except Exception as exc:
        raise DependencyUnavailableError(f"database unavailable: {exc}") from exc


@router.get("/healthz", summary="Liveness check")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness check")
async def readyz() -> dict[str, object]:
    settings = get_settings()
    db = await check_database_readiness(settings.database_url)
    redis = await check_redis_readiness(settings.redis_url)
    overall = "ok" if db["available"] and redis["available"] else "degraded"
    return {"status": overall, "checks": {"database": db, "redis": redis}}


@router.post(
    "/am-i-blocked",
    response_model=DiagnosticRequestSubmitted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a diagnostic request",
)
async def submit_diagnostic(
    payload: DiagnosticRequest,
    request: Request,
) -> DiagnosticRequestSubmitted:
    """Submit a new 'am I blocked?' diagnostic request.

    Returns a request_id that can be polled for results.
    The actual diagnostic work is performed asynchronously by the worker.
    """
    request_id = uuid.uuid4()
    requester = _get_requester(request)
    time_start, time_end = _time_window_bounds(payload.time_window)
    dest_type = _classify_destination(payload.destination)

    record = {
        "request_id": request_id,
        "status": RequestStatus.PENDING,
        "destination_type": dest_type,
        "destination_value": payload.destination,
        "port": payload.port,
        "time_window_start": time_start,
        "time_window_end": time_end,
        "requester": requester,
        "created_at": datetime.now(tz=UTC),
    }
    if not await _persist_request_db(record):
        raise HTTPException(status_code=503, detail="Persistence unavailable")

    logger.info(
        "diagnostic request submitted",
        request_id=str(request_id),
        destination=payload.destination,
        requester=requester,
    )

    settings = get_settings()
    try:
        await enqueue_job(
            settings.redis_url,
            {
                "request_id": str(request_id),
                "destination": payload.destination,
                "port": payload.port,
                "time_window": payload.time_window.value,
                "requester": requester,
            },
        )
    except Exception as exc:
        await _update_request_status_db(
            request_id,
            RequestStatus.FAILED,
            reason=str(exc),
            stage=FailureStage.QUEUE_ENQUEUE,
            category=FailureCategory.DEPENDENCY,
        )
        raise HTTPException(status_code=503, detail="Queue unavailable") from None

    return DiagnosticRequestSubmitted(
        request_id=request_id,
        status=RequestStatus.PENDING,
        status_url=f"/api/v1/requests/{request_id}",
    )


@router.get(
    "/requests/{request_id}",
    response_model=RequestDetail,
    summary="Get request status",
)
async def get_request(request_id: uuid.UUID) -> RequestDetail:
    """Retrieve the current status of a diagnostic request."""
    try:
        record = await _load_request_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not record:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    try:
        result = await _load_result_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    return RequestDetail(
        request_id=record["request_id"],
        status=record["status"],
        destination_type=record["destination_type"],
        destination_value=record["destination_value"],
        port=record["port"],
        time_window_start=record["time_window_start"],
        time_window_end=record["time_window_end"],
        requester=record["requester"],
        created_at=record["created_at"],
        failure_reason=record.get("failure_reason"),
        failure_stage=record.get("failure_stage"),
        failure_category=record.get("failure_category"),
        result=result,
    )


@router.get(
    "/requests/{request_id}/result",
    response_model=DiagnosticResult,
    summary="Get diagnostic result",
)
async def get_result(request_id: uuid.UUID) -> DiagnosticResult:
    """Retrieve the diagnostic result for a completed request."""
    try:
        record = await _load_request_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not record:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    try:
        result = await _load_result_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Result for request {request_id} not yet available",
        )
    result.destination_type = _normalize_optional_destination_type(record.get("destination_type"))
    result.destination_value = _normalize_optional_destination_value(record.get("destination_value"))
    result.destination_port = _normalize_optional_destination_port(record.get("port"))
    result.time_window_start = _normalize_optional_datetime(record.get("time_window_start"))
    result.time_window_end = _normalize_optional_datetime(record.get("time_window_end"))
    result.operator_handoff_summary = _normalize_optional_handoff_summary(
        result.operator_handoff_summary
    )
    return result


@router.get(
    "/requests/{request_id}/result/evidence-bundle",
    summary="Download diagnostic evidence bundle JSON",
)
async def download_evidence_bundle(request_id: uuid.UUID) -> JSONResponse:
    """Download a JSON evidence bundle for operator ticketing/escalation."""
    try:
        record = await _load_request_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not record:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    try:
        result = await _load_result_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Result for request {request_id} not yet available",
        )

    if isinstance(result, DiagnosticResult):
        normalized_result = result
    else:
        normalized_result = DiagnosticResult.model_validate(result)

    normalized_result.destination_type = _normalize_optional_destination_type(
        record.get("destination_type")
    )
    normalized_result.destination_value = _normalize_optional_destination_value(
        record.get("destination_value")
    )
    normalized_result.destination_port = _normalize_optional_destination_port(record.get("port"))
    normalized_result.time_window_start = _normalize_optional_datetime(record.get("time_window_start"))
    normalized_result.time_window_end = _normalize_optional_datetime(record.get("time_window_end"))
    normalized_result.operator_handoff_summary = _normalize_optional_handoff_summary(
        normalized_result.operator_handoff_summary
    )
    payload = normalized_result.model_dump(mode="json")

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="evidence-{request_id}.json"'},
    )


@router.get(
    "/requests/{request_id}/result/handoff-note",
    summary="Download operator handoff note",
)
async def download_handoff_note(request_id: uuid.UUID) -> PlainTextResponse:
    """Download a compact plain-text handoff note for operator ticketing."""
    try:
        record = await _load_request_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not record:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    if _normalize_optional_request_status(record.get("status")) == RequestStatus.FAILED:
        handoff_note = _build_failed_request_handoff_note(record)
        return PlainTextResponse(
            content=handoff_note,
            headers={"Content-Disposition": f'attachment; filename="handoff-{request_id}.txt"'},
        )

    try:
        result = await _load_result_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Result for request {request_id} not yet available",
        )

    if isinstance(result, DiagnosticResult):
        normalized_result = result
    else:
        normalized_result = DiagnosticResult.model_validate(result)

    normalized_result.destination_type = _normalize_optional_destination_type(
        record.get("destination_type")
    )
    normalized_result.destination_value = _normalize_optional_destination_value(
        record.get("destination_value")
    )
    normalized_result.destination_port = _normalize_optional_destination_port(record.get("port"))
    normalized_result.time_window_start = _normalize_optional_datetime(record.get("time_window_start"))
    normalized_result.time_window_end = _normalize_optional_datetime(record.get("time_window_end"))
    normalized_result.operator_handoff_summary = _normalize_optional_handoff_summary(
        normalized_result.operator_handoff_summary
    )

    handoff_note = _build_handoff_note(normalized_result)
    return PlainTextResponse(
        content=handoff_note,
        headers={"Content-Disposition": f'attachment; filename="handoff-{request_id}.txt"'},
    )
