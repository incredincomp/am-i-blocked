"""Browser-level UI tests for result-page handoff-note copy control."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from am_i_blocked_api import create_app
from am_i_blocked_core.enums import DestinationType, RequestStatus
from am_i_blocked_core.models import DiagnosticResult
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright


def _result_page_html(request_id: str) -> str:
    app = create_app()
    with TestClient(app) as client, patch(
        "am_i_blocked_api.routes.api._load_request_record",
        new_callable=AsyncMock,
        return_value={
            "request_id": request_id,
            "status": RequestStatus.COMPLETE,
            "destination_type": DestinationType.FQDN,
            "destination_value": "api.example.com",
            "port": 443,
            "time_window_start": "2026-03-08T00:00:00Z",
            "time_window_end": "2026-03-08T00:15:00Z",
            "requester": "anonymous",
            "created_at": "2026-03-08T00:00:00Z",
        },
    ), patch(
        "am_i_blocked_api.routes.api._load_result_record",
        new_callable=AsyncMock,
        return_value=DiagnosticResult.model_validate(
            {
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "operator_handoff_summary": "verdict=unknown; path=unknown",
                "summary": "Insufficient evidence.",
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Telemetry incomplete",
                    "next_steps": ["Check sources"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            }
        ),
    ):
        response = client.get(f"/requests/{request_id}")
    assert response.status_code == 200
    return response.text


def test_copy_handoff_note_success_shows_success_state():
    request_id = "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a"
    html = _result_page_html(request_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(
            """
            () => {
              window.__fetchUrls = [];
              window.__copiedText = null;
              window.fetch = async (url) => {
                window.__fetchUrls.push(String(url));
                return new Response("HANDOFF NOTE BODY", { status: 200 });
              };
              window.__handoffNoteWriteText = async (text) => { window.__copiedText = text; };
            }
            """
        )
        page.click("#copy-handoff-note-btn")
        page.wait_for_function(
            "() => document.querySelector('#copy-handoff-note-status').textContent.length > 0"
        )

        assert page.inner_text("#copy-handoff-note-status") == "Handoff note copied to clipboard."
        fallback_classes = page.get_attribute("#copy-handoff-note-fallback", "class") or ""
        assert "hidden" in fallback_classes
        assert page.evaluate("() => window.__copiedText") == "HANDOFF NOTE BODY"
        fetched = page.evaluate("() => window.__fetchUrls")
        assert fetched == [f"/api/v1/requests/{request_id}/result/handoff-note"]
        browser.close()


def test_copy_handoff_note_clipboard_failure_shows_fallback_state():
    request_id = "1b1b1b1b-1b1b-4b1b-8b1b-1b1b1b1b1b1b"
    html = _result_page_html(request_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(
            """
            () => {
              window.fetch = async () => new Response("HANDOFF NOTE BODY", { status: 200 });
              window.__handoffNoteWriteText = async () => { throw new Error("clipboard blocked"); };
            }
            """
        )
        page.click("#copy-handoff-note-btn")
        page.wait_for_function(
            "() => document.querySelector('#copy-handoff-note-status').textContent.includes('could not complete')"
        )

        assert (
            page.inner_text("#copy-handoff-note-status")
            == "Copy could not complete in this browser/session."
        )
        fallback_classes = page.get_attribute("#copy-handoff-note-fallback", "class") or ""
        assert "hidden" not in fallback_classes
        fallback_href = page.get_attribute("#copy-handoff-note-fallback-link", "href")
        assert fallback_href == f"/api/v1/requests/{request_id}/result/handoff-note"
        browser.close()


def test_copy_handoff_note_fetch_failure_shows_fallback_state():
    request_id = "2c2c2c2c-2c2c-4c2c-8c2c-2c2c2c2c2c2c"
    html = _result_page_html(request_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        page.evaluate(
            """
            () => {
              window.__fetchUrls = [];
              window.__writeCalled = false;
              window.fetch = async (url) => {
                window.__fetchUrls.push(String(url));
                return new Response("upstream unavailable", { status: 503 });
              };
              window.__handoffNoteWriteText = async () => { window.__writeCalled = true; };
            }
            """
        )

        assert page.locator("#copy-handoff-note-btn").count() == 1
        page.click("#copy-handoff-note-btn")
        page.wait_for_function(
            "() => document.querySelector('#copy-handoff-note-status').textContent.includes('could not complete')"
        )

        assert (
            page.inner_text("#copy-handoff-note-status")
            == "Copy could not complete in this browser/session."
        )
        fallback_classes = page.get_attribute("#copy-handoff-note-fallback", "class") or ""
        assert "hidden" not in fallback_classes
        fallback_href = page.get_attribute("#copy-handoff-note-fallback-link", "href")
        assert fallback_href == f"/api/v1/requests/{request_id}/result/handoff-note"
        fetched = page.evaluate("() => window.__fetchUrls")
        assert fetched == [f"/api/v1/requests/{request_id}/result/handoff-note"]
        assert page.evaluate("() => window.__writeCalled") is False
        browser.close()
