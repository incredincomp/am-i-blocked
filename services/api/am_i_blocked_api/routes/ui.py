"""Server-rendered UI routes."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

from am_i_blocked_core.enums import FailureCategory, FailureStage, RequestStatus
from am_i_blocked_core.models import DiagnosticResult
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["ui"])

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


def _normalize_failure_stage(value: object) -> FailureStage:
    if isinstance(value, FailureStage):
        return value
    if isinstance(value, str):
        try:
            return FailureStage(value)
        except ValueError:
            return FailureStage.UNKNOWN
    return FailureStage.UNKNOWN


def _normalize_failure_category(value: object) -> FailureCategory:
    if isinstance(value, FailureCategory):
        return value
    if isinstance(value, str):
        try:
            return FailureCategory(value)
        except ValueError:
            return FailureCategory.UNKNOWN
    return FailureCategory.UNKNOWN


def _build_triage_hint(record: dict) -> dict[str, str] | None:
    status = record.get("status")
    normalized_status = status.value if isinstance(status, RequestStatus) else str(status)
    if normalized_status != RequestStatus.FAILED.value:
        return None

    stage = _normalize_failure_stage(record.get("failure_stage"))
    category = _normalize_failure_category(record.get("failure_category"))

    stage_actions = {
        FailureStage.QUEUE_ENQUEUE: "Check Redis queue availability and worker queue connectivity, then retry.",
        FailureStage.VALIDATE_REQUEST: "Verify destination, optional port, and time window, then resubmit.",
        FailureStage.SOURCE_READINESS_CHECK: "Check source readiness and auth material before rerunning.",
        FailureStage.BOUNDED_PROBES: "Verify bounded-probe network path and probe timeout settings.",
        FailureStage.AUTHORITATIVE_CORRELATION: "Check authoritative adapter connectivity and credentials.",
        FailureStage.CLASSIFY: "Review classification inputs and worker logs for malformed evidence.",
        FailureStage.PERSIST_AND_REPORT: "Check Postgres write path and rerun once persistence is healthy.",
    }
    category_actions = {
        FailureCategory.DEPENDENCY: "Validate dependency health (DB, Redis, or adapter endpoints) before retry.",
        FailureCategory.VALIDATION: "Correct request input values and resubmit.",
        FailureCategory.PIPELINE_STEP: "Inspect worker logs for this stage and rerun after correction.",
        FailureCategory.PERSISTENCE: "Restore persistence dependencies before retrying this request.",
        FailureCategory.INTERNAL: "Escalate to platform engineering with request id and failure details.",
        FailureCategory.UNKNOWN: "Capture request id and logs, then escalate for manual triage.",
    }

    return {
        "stage": stage.value,
        "category": category.value,
        "first_hop_action": stage_actions.get(stage) or category_actions[category],
    }


def _normalize_lifecycle_timestamp(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return None


def _build_lifecycle_event_summary(event: dict[str, object]) -> str | None:
    action = event.get("action")
    params = event.get("params") if isinstance(event.get("params"), dict) else {}

    if action == "request_complete":
        verdict = params.get("verdict")
        if isinstance(verdict, str) and verdict.strip():
            return f"Verdict: {verdict.strip()}"
        return None

    if action == "request_failed":
        details: list[str] = []
        stage = params.get("stage")
        if isinstance(stage, str) and stage.strip():
            details.append(f"stage={stage.strip()}")
        category = params.get("category")
        if isinstance(category, str) and category.strip():
            details.append(f"category={category.strip()}")
        reason = params.get("reason")
        if isinstance(reason, str) and reason.strip():
            details.append(f"reason={reason.strip()}")
        return " | ".join(details) if details else None

    return None


def _build_lifecycle_events(
    record: dict,
    result: DiagnosticResult | None,
    audit_events: list[dict[str, object]],
) -> list[dict[str, str | None]]:
    label_map = {
        "request_submitted": "Submitted",
        "request_running": "Running",
        "request_complete": "Complete",
        "request_failed": "Failed",
    }

    lifecycle_events: list[dict[str, str | None]] = []
    seen_actions: set[str] = set()

    for event in audit_events:
        action = event.get("action")
        if not isinstance(action, str) or action not in label_map:
            continue
        seen_actions.add(action)
        lifecycle_events.append(
            {
                "label": label_map[action],
                "timestamp": _normalize_lifecycle_timestamp(event.get("timestamp")),
                "summary": _build_lifecycle_event_summary(event),
            }
        )

    created_at = _normalize_lifecycle_timestamp(record.get("created_at"))
    if "request_submitted" not in seen_actions and created_at:
        lifecycle_events.insert(
            0,
            {
                "label": "Submitted",
                "timestamp": created_at,
                "summary": None,
            },
        )

    if result is not None and "request_complete" not in seen_actions:
        lifecycle_events.append(
            {
                "label": "Complete",
                "timestamp": result.created_at.isoformat(),
                "summary": f"Verdict: {result.verdict}",
            }
        )

    return lifecycle_events


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Landing page with the diagnostic form."""
    return templates.TemplateResponse(request, "index.html")


@router.get("/requests/{request_id}", response_class=HTMLResponse, include_in_schema=False)
async def request_page(request: Request, request_id: uuid.UUID) -> HTMLResponse:
    """Result page for a specific diagnostic request."""
    # Import here to avoid circular import
    from .api import (
        DependencyUnavailableError,
        _load_request_audit_events,
        _load_request_record,
        _load_result_record,
    )

    try:
        record = await _load_request_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")

    try:
        result = await _load_result_record(request_id)
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    if isinstance(result, dict):
        result = DiagnosticResult.model_validate(result)
    try:
        lifecycle_events = _build_lifecycle_events(
            record,
            result,
            await _load_request_audit_events(request_id),
        )
    except DependencyUnavailableError:
        raise HTTPException(status_code=503, detail="Persistence unavailable") from None
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "record": record,
            "result": result,
            "lifecycle_events": lifecycle_events,
            "triage_hint": _build_triage_hint(record),
            "request_id": str(request_id),
        },
    )
