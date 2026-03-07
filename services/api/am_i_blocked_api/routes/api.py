"""API routes for am-i-blocked."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from am_i_blocked_core.config import get_settings
from am_i_blocked_core.enums import DestinationType, RequestStatus
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import (
    DiagnosticRequest,
    DiagnosticRequestSubmitted,
    DiagnosticResult,
    RequestDetail,
)
from fastapi import APIRouter, HTTPException, Request, status

logger = get_logger(__name__)
router = APIRouter(tags=["diagnostic"])

# ---------------------------------------------------------------------------
# In-memory request store (replace with DB in production)
# ---------------------------------------------------------------------------
_requests: dict[str, dict] = {}
_results: dict[str, DiagnosticResult] = {}


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


@router.get("/healthz", summary="Liveness check")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness check")
async def readyz() -> dict[str, str]:
    # TODO: add DB and Redis connectivity checks
    return {"status": "ok"}


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

    _requests[str(request_id)] = {
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

    logger.info(
        "diagnostic request submitted",
        request_id=str(request_id),
        destination=payload.destination,
        requester=requester,
    )

    # TODO: Enqueue to worker via Redis task queue
    # await enqueue_job(request_id=str(request_id))

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
    record = _requests.get(str(request_id))
    if not record:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    result = _results.get(str(request_id))
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
        result=result,
    )


@router.get(
    "/requests/{request_id}/result",
    response_model=DiagnosticResult,
    summary="Get diagnostic result",
)
async def get_result(request_id: uuid.UUID) -> DiagnosticResult:
    """Retrieve the diagnostic result for a completed request."""
    if str(request_id) not in _requests:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    result = _results.get(str(request_id))
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Result for request {request_id} not yet available",
        )
    return result
