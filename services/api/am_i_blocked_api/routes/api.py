"""API routes for am-i-blocked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

logger = get_logger(__name__)
router = APIRouter(tags=["diagnostic"])

_engines: dict[str, AsyncEngine] = {}
_sessions: dict[str, async_sessionmaker] = {}


class DependencyUnavailableError(RuntimeError):
    """Raised when Postgres/Redis dependencies are unavailable for a request."""


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
        payload = {
            "request_id": str(request_id),
            "verdict": row.verdict,
            "enforcement_plane": report.get("enforcement_plane", "unknown"),
            "path_context": report.get("path_context", "unknown"),
            "path_confidence": report.get("path_confidence", 0.0),
            "result_confidence": row.result_confidence,
            "evidence_completeness": row.evidence_completeness,
            "summary": row.summary,
            "observed_facts": report.get("observed_facts", []),
            "routing_recommendation": report.get(
                "routing_recommendation",
                {
                    "owner_team": row.owner_team,
                    "reason": "loaded from persisted result",
                    "next_steps": row.next_steps_json or [],
                },
            ),
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
        payload = result.model_dump(mode="json")
    else:
        payload = DiagnosticResult.model_validate(result).model_dump(mode="json")

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="evidence-{request_id}.json"'},
    )
