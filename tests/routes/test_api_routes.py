"""Route smoke tests for the FastAPI application."""

from __future__ import annotations

import pytest
from am_i_blocked_api import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    def test_healthz_returns_ok(self, client):
        resp = client.get("/api/v1/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_readyz_returns_ok(self, client):
        resp = client.get("/api/v1/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestSubmitDiagnostic:
    def test_submit_valid_destination(self, client):
        resp = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com", "time_window": "last_15m"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "request_id" in data
        assert data["status"] == "pending"
        assert data["status_url"].startswith("/api/v1/requests/")

    def test_submit_with_port(self, client):
        resp = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "10.20.30.40", "port": 443, "time_window": "now"},
        )
        assert resp.status_code == 202

    def test_submit_url_destination(self, client):
        resp = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "https://api.example.com/v1", "time_window": "last_60m"},
        )
        assert resp.status_code == 202

    def test_submit_cidr_rejected(self, client):
        resp = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "10.0.0.0/8"},
        )
        assert resp.status_code == 422

    def test_submit_empty_destination_rejected(self, client):
        resp = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": ""},
        )
        assert resp.status_code == 422


class TestGetRequest:
    def test_get_known_request(self, client):
        submit = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com"},
        )
        request_id = submit.json()["request_id"]
        resp = client.get(f"/api/v1/requests/{request_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"] == request_id
        assert data["destination_value"] == "api.example.com"

    def test_get_unknown_request_returns_404(self, client):
        resp = client.get("/api/v1/requests/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestGetResult:
    def test_result_not_ready_returns_404(self, client):
        submit = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com"},
        )
        request_id = submit.json()["request_id"]
        resp = client.get(f"/api/v1/requests/{request_id}/result")
        assert resp.status_code == 404

    def test_result_unknown_request_returns_404(self, client):
        resp = client.get("/api/v1/requests/00000000-0000-0000-0000-000000000001/result")
        assert resp.status_code == 404


class TestUIRoutes:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Am I Blocked" in resp.text

    def test_request_page_pending(self, client):
        submit = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com"},
        )
        request_id = submit.json()["request_id"]
        resp = client.get(f"/requests/{request_id}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_request_page_unknown_returns_404(self, client):
        resp = client.get("/requests/00000000-0000-0000-0000-000000000002")
        assert resp.status_code == 404
