"""Server-rendered UI routes."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["ui"])

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Landing page with the diagnostic form."""
    return templates.TemplateResponse(request, "index.html")


@router.get("/requests/{request_id}", response_class=HTMLResponse, include_in_schema=False)
async def request_page(request: Request, request_id: uuid.UUID) -> HTMLResponse:
    """Result page for a specific diagnostic request."""
    # Import here to avoid circular import
    from .api import _requests, _results

    record = _requests.get(str(request_id))
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")

    result = _results.get(str(request_id))
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "record": record,
            "result": result,
            "request_id": str(request_id),
        },
    )
