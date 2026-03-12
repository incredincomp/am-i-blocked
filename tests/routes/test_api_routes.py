"""Route smoke tests for the FastAPI application."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from am_i_blocked_api import create_app
from am_i_blocked_api.routes import api as api_routes
from am_i_blocked_core.db_models import AuditRow, RequestRow
from am_i_blocked_core.enums import DestinationType, RequestStatus
from am_i_blocked_core.models import DiagnosticResult
from fastapi.testclient import TestClient

_ORIG_LOAD_RESULT_RECORD = api_routes._load_result_record
_ORIG_LOAD_REQUEST_RECORD = api_routes._load_request_record


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_db_storage():
    with patch(
        "am_i_blocked_api.routes.api._persist_request_db",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        "am_i_blocked_api.routes.api._load_request_record",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "am_i_blocked_api.routes.api._load_result_record",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "am_i_blocked_api.routes.api.enqueue_job",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


class TestHealthEndpoints:
    def test_healthz_returns_ok(self, client):
        resp = client.get("/api/v1/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_readyz_returns_ok(self, client):
        with patch(
            "am_i_blocked_api.routes.api.check_database_readiness",
            new_callable=AsyncMock,
            return_value={"available": True, "reason": None},
        ), patch(
            "am_i_blocked_api.routes.api.check_redis_readiness",
            new_callable=AsyncMock,
            return_value={"available": True, "reason": None},
        ):
            resp = client.get("/api/v1/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_readyz_returns_degraded_when_dependency_unavailable(self, client):
        with patch(
            "am_i_blocked_api.routes.api.check_database_readiness",
            new_callable=AsyncMock,
            return_value={"available": False, "reason": "db down"},
        ), patch(
            "am_i_blocked_api.routes.api.check_redis_readiness",
            new_callable=AsyncMock,
            return_value={"available": True, "reason": None},
        ):
            resp = client.get("/api/v1/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"


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

    def test_submit_enqueues_job_payload(self, client):
        with patch(
            "am_i_blocked_api.routes.api.enqueue_job",
            new_callable=AsyncMock,
            return_value=None,
        ) as enqueue:
            resp = client.post(
                "/api/v1/am-i-blocked",
                json={"destination": "api.example.com", "port": 443, "time_window": "last_15m"},
            )

        assert resp.status_code == 202
        payload = enqueue.await_args.args[1]
        assert payload["destination"] == "api.example.com"
        assert payload["port"] == 443
        assert payload["time_window"] == "last_15m"
        assert payload["request_id"] == resp.json()["request_id"]

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

    def test_submit_returns_503_when_persistence_unavailable(self, client):
        with patch(
            "am_i_blocked_api.routes.api._persist_request_db",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.post(
                "/api/v1/am-i-blocked",
                json={"destination": "api.example.com", "time_window": "last_15m"},
            )
        assert resp.status_code == 503

    def test_submit_returns_503_when_queue_unavailable(self, client):
        with patch(
            "am_i_blocked_api.routes.api.enqueue_job",
            new_callable=AsyncMock,
            side_effect=RuntimeError("redis unavailable"),
        ), patch(
            "am_i_blocked_api.routes.api._update_request_status_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/api/v1/am-i-blocked",
                json={"destination": "api.example.com", "time_window": "last_15m"},
            )
        assert resp.status_code == 503


class TestGetRequest:
    def test_get_known_request(self, client):
        request_id = "11111111-1111-1111-1111-111111111111"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.PENDING,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
                "time_window_start": "2026-03-08T00:00:00Z",
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"] == request_id
        assert data["destination_value"] == "api.example.com"

    def test_get_unknown_request_returns_404(self, client):
        resp = client.get("/api/v1/requests/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_request_returns_503_when_db_unavailable(self, client):
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            side_effect=api_routes.DependencyUnavailableError("database unavailable"),
        ):
            resp = client.get("/api/v1/requests/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 503

    def test_get_request_uses_db_record_when_available(self, client):
        submit = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com"},
        )
        request_id = submit.json()["request_id"]
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.PENDING,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
                "time_window_start": "2026-03-08T00:00:00Z",
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
                "failure_reason": "queue timeout",
                "failure_stage": "queue_enqueue",
                "failure_category": "dependency",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}")
        assert resp.status_code == 200
        assert resp.json()["failure_reason"] == "queue timeout"
        assert resp.json()["failure_stage"] == "queue_enqueue"
        assert resp.json()["failure_category"] == "dependency"

    def test_get_request_normalizes_malformed_audit_stage_and_category_to_unknown(self, client):
        request_id = uuid.UUID("a1a1a1a1-a1a1-4a1a-a1a1-a1a1a1a1a1a1")
        request_row = RequestRow(
            request_id=request_id,
            status=RequestStatus.FAILED.value,
            destination_type=DestinationType.FQDN.value,
            destination_value="api.example.com",
            port=443,
            time_window_start=datetime(2026, 3, 8, 0, 0, tzinfo=UTC),
            time_window_end=datetime(2026, 3, 8, 0, 15, tzinfo=UTC),
            requester="anonymous",
            created_at=datetime(2026, 3, 8, 0, 0, tzinfo=UTC),
        )
        audit_row = AuditRow(
            request_id=request_id,
            actor="worker",
            action="request_failed",
            params_json={
                "reason": "synthetic failure reason",
                "stage": "totally_bad_stage",
                "category": "totally_bad_category",
            },
            timestamp=datetime(2026, 3, 8, 0, 1, tzinfo=UTC),
        )

        class _FakeRequestSession:
            async def get(self, model, key):  # type: ignore[no-untyped-def]
                if model is RequestRow and key == request_id:
                    return request_row
                return None

            async def execute(self, _stmt):  # type: ignore[no-untyped-def]
                return SimpleNamespace(scalar_one_or_none=lambda: audit_row)

        class _FakeRequestSessionContext:
            async def __aenter__(self):
                return _FakeRequestSession()

            async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
                return None

        def _fake_request_session_factory():
            return _FakeRequestSessionContext()

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_request_session_factory,
        ), patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new=_ORIG_LOAD_REQUEST_RECORD,
        ), patch(
            "am_i_blocked_api.routes.api._load_result_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get(f"/api/v1/requests/{request_id}")

        assert resp.status_code == 200
        assert resp.json()["failure_reason"] == "synthetic failure reason"
        assert resp.json()["failure_stage"] == "unknown"
        assert resp.json()["failure_category"] == "unknown"


class TestFailureMetadataHelpers:
    def test_extract_failure_metadata_reads_structured_fields(self):
        metadata = api_routes._extract_failure_metadata(
            {
                "reason": "queue timeout",
                "stage": "queue_enqueue",
                "category": "dependency",
            }
        )
        assert metadata == {
            "reason": "queue timeout",
            "stage": "queue_enqueue",
            "category": "dependency",
        }

    def test_extract_failure_metadata_supports_legacy_reason_key(self):
        metadata = api_routes._extract_failure_metadata({"error": "legacy error message"})
        assert metadata == {
            "reason": "legacy error message",
            "stage": None,
            "category": None,
        }

    def test_extract_failure_metadata_normalizes_unknown_values(self):
        metadata = api_routes._extract_failure_metadata(
            {
                "reason": "oops",
                "stage": "non_standard_stage",
                "category": "non_standard_category",
            }
        )
        assert metadata == {
            "reason": "oops",
            "stage": "unknown",
            "category": "unknown",
        }


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

    def test_result_returns_503_when_db_unavailable(self, client):
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            side_effect=api_routes.DependencyUnavailableError("database unavailable"),
        ):
            resp = client.get("/api/v1/requests/00000000-0000-0000-0000-000000000001/result")
        assert resp.status_code == 503

    def test_result_returns_persisted_result_when_available(self, client):
        request_id = "99999999-9999-9999-9999-999999999999"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["request_id"] == request_id

    def test_evidence_bundle_download_returns_attachment(self, client):
        request_id = "77777777-7777-7777-7777-777777777777"
        with patch(
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
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Insufficient evidence",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result/evidence-bundle")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert (
            resp.headers["content-disposition"]
            == f'attachment; filename="evidence-{request_id}.json"'
        )
        assert resp.json()["request_id"] == request_id

    def test_handoff_note_download_returns_plain_text_attachment(self, client):
        request_id = "81818181-8181-8181-8181-818181818181"
        with patch(
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
                    "verdict": "denied",
                    "enforcement_plane": "onprem_palo",
                    "path_context": "vpn_gp_onprem_static",
                    "path_confidence": 0.8,
                    "result_confidence": 0.85,
                    "evidence_completeness": 0.8,
                    "operator_handoff_summary": "verdict=denied; path=vpn_gp_onprem_static; enforcement=onprem_palo",
                    "summary": "On-prem PAN-OS deny detected.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "SecOps",
                        "reason": "On-prem policy deny evidence found",
                        "next_steps": ["Review PAN-OS rule", "Open SecOps ticket"],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result/handoff-note")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert (
            resp.headers["content-disposition"]
            == f'attachment; filename="handoff-{request_id}.txt"'
        )
        assert "Am I Blocked - Operator Handoff" in resp.text
        assert "Request ID: 81818181-8181-8181-8181-818181818181" in resp.text
        assert "Verdict: denied" in resp.text
        assert (
            "Operator handoff summary: verdict=denied; path=vpn_gp_onprem_static; enforcement=onprem_palo"
            in resp.text
        )
        assert "Context:" in resp.text
        assert "- Destination: api.example.com:443 (fqdn)" in resp.text
        assert "- Time window: 2026-03-08T00:00:00+00:00 to 2026-03-08T00:15:00+00:00" in resp.text
        assert "Routing:" in resp.text
        assert "- Reason: On-prem policy deny evidence found" in resp.text
        assert "Evidence snapshot:" in resp.text
        assert "- Observed facts: total=0, authoritative=0, enrichment_only=0" in resp.text
        assert "Readiness snapshot:" in resp.text
        assert "- Sources checked: 0" in resp.text
        assert "- Review PAN-OS rule" in resp.text
        assert "- Open SecOps ticket" in resp.text

    def test_handoff_note_download_handles_missing_optional_context(self, client):
        request_id = "82828282-8282-8282-8282-828282828282"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": DestinationType.UNKNOWN,
                "destination_value": "",
                "port": None,
                "time_window_start": None,
                "time_window_end": None,
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
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result/handoff-note")

        assert resp.status_code == 200
        assert "- Destination: n/a" in resp.text
        assert "- Time window: n/a" in resp.text
        assert "Operator handoff summary:" not in resp.text
        assert "- Reason: n/a" in resp.text
        assert "Unknown signals:" not in resp.text
        assert "Next steps:" in resp.text
        assert "- none provided" in resp.text

    def test_handoff_note_download_includes_unknown_signals_and_summaries(self, client):
        request_id = "83838383-8383-8383-8383-838383838383"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
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
                    "summary": "Insufficient evidence.",
                    "unknown_reason_signals": [
                        "No authoritative deny evidence was found; this is not confirmation that access is allowed."
                    ],
                    "source_readiness_summary": {
                        "total_sources": 3,
                        "available_sources": ["panos"],
                        "unavailable_sources": ["scm"],
                        "unknown_sources": ["torq"],
                    },
                    "observed_fact_summary": {
                        "total_facts": 2,
                        "authoritative_facts": 1,
                        "enrichment_only_facts": 1,
                        "authoritative_sources": ["scm"],
                        "enrichment_only_sources": ["logscale"],
                    },
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Telemetry incomplete",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result/handoff-note")

        assert resp.status_code == 200
        assert "- Observed facts: total=2, authoritative=1, enrichment_only=1" in resp.text
        assert "- Authoritative sources: scm" in resp.text
        assert "- Enrichment-only sources: logscale" in resp.text
        assert "- Sources checked: 3" in resp.text
        assert "- Available: panos" in resp.text
        assert "- Unavailable: scm" in resp.text
        assert "- Unknown: torq" in resp.text
        assert "Unknown signals:" in resp.text
        assert (
            "- No authoritative deny evidence was found; this is not confirmation that access is allowed."
            in resp.text
        )

    def test_evidence_bundle_download_denied_path_preserves_authoritative_metadata_and_readiness(self, client):
        request_id = "78787878-7878-7878-7878-787878787878"
        with patch(
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
                    "verdict": "denied",
                    "enforcement_plane": "onprem_palo",
                    "path_context": "vpn_gp_onprem_static",
                    "path_confidence": 0.8,
                    "result_confidence": 0.85,
                    "evidence_completeness": 0.8,
                    "summary": "On-prem PAN-OS deny detected.",
                    "observed_facts": [
                        {
                            "source": "panos",
                            "summary": "On-prem PAN deny: rule=block-ext",
                            "detail": {
                                "action": "deny",
                                "authoritative": True,
                                "rule_name": "block-ext",
                                "rule_metadata": {
                                    "rule_name": "block-ext",
                                    "action": "deny",
                                    "description": "Block external traffic",
                                },
                            },
                        }
                    ],
                    "unknown_reason_signals": [],
                    "source_readiness_summary": {
                        "total_sources": 3,
                        "available_sources": ["panos", "scm"],
                        "unavailable_sources": ["sdwan"],
                        "unknown_sources": [],
                    },
                    "source_readiness_details": [
                        {"source": "panos", "status": "ready", "reason": "probe ok", "latency_ms": 9},
                        {"source": "scm", "status": "ready", "reason": "reachable", "latency_ms": 12},
                        {"source": "sdwan", "status": "timeout", "reason": "upstream timeout", "latency_ms": None},
                    ],
                    "routing_recommendation": {
                        "owner_team": "SecOps",
                        "reason": "On-prem PAN deny evidence found",
                        "next_steps": ["Review PAN-OS rule"],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result/evidence-bundle")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert (
            resp.headers["content-disposition"]
            == f'attachment; filename="evidence-{request_id}.json"'
        )
        payload = resp.json()
        assert payload["request_id"] == request_id
        assert payload["verdict"] == "denied"
        assert payload["observed_facts"][0]["detail"]["rule_metadata"]["rule_name"] == "block-ext"
        assert payload["source_readiness_summary"]["total_sources"] == 3
        assert payload["source_readiness_summary"]["unavailable_sources"] == ["sdwan"]
        assert len(payload["source_readiness_details"]) == 3

    def test_evidence_bundle_unknown_reason_signals_match_result_payload(self, client):
        request_id = "79797979-7979-7979-7979-797979797979"
        expected_signals = [
            "No authoritative deny evidence was found; this is not confirmation that access is allowed.",
            "One or more data sources were degraded or unavailable, which reduced confidence.",
        ]
        with patch(
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
                    "path_confidence": 0.3,
                    "result_confidence": 0.2,
                    "evidence_completeness": 0.3,
                    "summary": "Insufficient evidence.",
                    "unknown_reason_signals": expected_signals,
                    "source_readiness_summary": {
                        "total_sources": 2,
                        "available_sources": ["panos"],
                        "unavailable_sources": ["scm"],
                        "unknown_sources": [],
                    },
                    "source_readiness_details": [
                        {
                            "source": "scm",
                            "status": "auth_failed",
                            "reason": "SCM auth failed (401)",
                            "latency_ms": 14,
                        }
                    ],
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Insufficient evidence",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            result_resp = client.get(f"/api/v1/requests/{request_id}/result")
            bundle_resp = client.get(f"/api/v1/requests/{request_id}/result/evidence-bundle")

        assert result_resp.status_code == 200
        assert bundle_resp.status_code == 200
        assert (
            bundle_resp.headers["content-disposition"]
            == f'attachment; filename="evidence-{request_id}.json"'
        )

        result_payload = result_resp.json()
        bundle_payload = bundle_resp.json()
        assert result_payload["unknown_reason_signals"] == expected_signals
        assert bundle_payload["unknown_reason_signals"] == expected_signals
        assert bundle_payload["unknown_reason_signals"] == result_payload["unknown_reason_signals"]
        assert bundle_payload["source_readiness_summary"] == result_payload["source_readiness_summary"]
        assert bundle_payload["source_readiness_details"] == result_payload["source_readiness_details"]

    def test_evidence_bundle_handoff_fields_match_result_payload(self, client):
        request_id = "80808080-8080-8080-8080-808080808080"
        with patch(
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
                    "verdict": "denied",
                    "destination_type": "fqdn",
                    "destination_value": "api.example.com",
                    "destination_port": 443,
                    "enforcement_plane": "onprem_palo",
                    "path_context": "campus_non_sdwan",
                    "path_confidence": 0.8,
                    "result_confidence": 0.9,
                    "evidence_completeness": 0.8,
                    "time_window_start": "2026-03-08T00:00:00Z",
                    "time_window_end": "2026-03-08T00:15:00Z",
                    "summary": "Authoritative policy deny was observed.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "SecOps",
                        "reason": "On-prem policy deny evidence matches destination and port.",
                        "next_steps": ["Review deny policy"],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            result_resp = client.get(f"/api/v1/requests/{request_id}/result")
            bundle_resp = client.get(f"/api/v1/requests/{request_id}/result/evidence-bundle")

        assert result_resp.status_code == 200
        assert bundle_resp.status_code == 200
        assert (
            bundle_resp.headers["content-disposition"]
            == f'attachment; filename="evidence-{request_id}.json"'
        )

        result_payload = result_resp.json()
        bundle_payload = bundle_resp.json()
        handoff_fields = [
            "destination_type",
            "destination_value",
            "destination_port",
            "time_window_start",
            "time_window_end",
        ]
        for field in handoff_fields:
            assert bundle_payload[field] == result_payload[field]
        assert (
            bundle_payload["routing_recommendation"]["reason"]
            == result_payload["routing_recommendation"]["reason"]
        )

    def test_result_includes_panos_rule_metadata_when_present(self, client):
        request_id = "12121212-1212-1212-1212-121212121212"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "vpn_gp_onprem_static",
                "path_confidence": 0.8,
                "result_confidence": 0.85,
                "evidence_completeness": 0.8,
                "summary": "On-prem PAN-OS deny detected.",
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "On-prem PAN deny: rule=block-ext",
                        "detail": {
                            "action": "deny",
                            "authoritative": True,
                            "rule_name": "block-ext",
                            "rule_metadata": {
                                "rule_name": "block-ext",
                                "action": "deny",
                                "description": "Block external traffic",
                            },
                        },
                    }
                ],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem PAN deny evidence found",
                    "next_steps": ["Review PAN-OS rule"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        detail = resp.json()["observed_facts"][0]["detail"]
        assert detail["rule_metadata"]["rule_name"] == "block-ext"
        assert detail["rule_metadata"]["description"] == "Block external traffic"

    def test_result_unknown_includes_confidence_reason_signals(self, client):
        request_id = "21212121-2121-2121-2121-212121212121"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [
                    "No authoritative deny evidence was found; this is not confirmation that access is allowed.",
                    "One or more data sources were degraded or unavailable, which reduced confidence.",
                    "Path context confidence is low, so route or policy context may be incomplete.",
                    "Bounded checks were inconclusive or incomplete for this time window.",
                ],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["unknown_reason_signals"] == [
            "No authoritative deny evidence was found; this is not confirmation that access is allowed.",
            "One or more data sources were degraded or unavailable, which reduced confidence.",
            "Path context confidence is low, so route or policy context may be incomplete.",
            "Bounded checks were inconclusive or incomplete for this time window.",
        ]

    def test_result_includes_source_readiness_summary(self, client):
        request_id = "56565656-5656-5656-5656-565656565656"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.4,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "source_readiness_summary": {
                    "total_sources": 4,
                    "available_sources": ["panos"],
                    "unavailable_sources": ["scm", "sdwan"],
                    "unknown_sources": ["torq"],
                },
                "unknown_reason_signals": [],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        summary = resp.json()["source_readiness_summary"]
        assert summary["total_sources"] == 4
        assert summary["unavailable_sources"] == ["scm", "sdwan"]

    def test_result_includes_source_readiness_details(self, client):
        request_id = "57575757-5757-5757-5757-575757575757"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.4,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "source_readiness_summary": {
                    "total_sources": 2,
                    "available_sources": ["panos"],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "source_readiness_details": [
                    {
                        "source": "scm",
                        "status": "auth_failed",
                        "reason": "SCM auth failed (401)",
                        "latency_ms": 14,
                    },
                ],
                "unknown_reason_signals": [],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        details = resp.json()["source_readiness_details"]
        assert len(details) == 1
        assert details[0]["source"] == "scm"
        assert details[0]["status"] == "auth_failed"

    def test_result_includes_observed_fact_summary(self, client):
        request_id = "58585858-5858-5858-5858-585858585858"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.8,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 2,
                    "authoritative_facts": 1,
                    "enrichment_only_facts": 1,
                    "authoritative_sources": ["panos"],
                    "enrichment_only_sources": ["logscale"],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "policy deny found",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        summary = resp.json()["observed_fact_summary"]
        assert summary["total_facts"] == 2
        assert summary["authoritative_facts"] == 1
        assert summary["enrichment_only_sources"] == ["logscale"]

    def test_result_includes_routing_recommendation_reason(self, client):
        request_id = "59595959-5959-5959-5959-595959595959"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.9,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 1,
                    "authoritative_facts": 1,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": ["panos"],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem policy deny evidence matches destination and port.",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert (
            resp.json()["routing_recommendation"]["reason"]
            == "On-prem policy deny evidence matches destination and port."
        )

    def test_result_includes_operator_handoff_summary_when_present(self, client):
        request_id = "60606060-6060-6060-6060-606060606060"
        expected_summary = (
            "verdict=denied; path=campus_non_sdwan; enforcement=onprem_palo; "
            "authoritative_facts=1; ready_sources=1; unavailable_sources=1; "
            "routing_reason=On-prem policy deny evidence found"
        )
        with patch(
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
                    "verdict": "denied",
                    "enforcement_plane": "onprem_palo",
                    "path_context": "campus_non_sdwan",
                    "path_confidence": 0.9,
                    "result_confidence": 0.9,
                    "evidence_completeness": 0.8,
                    "operator_handoff_summary": expected_summary,
                    "summary": "Authoritative policy deny was observed.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "SecOps",
                        "reason": "On-prem policy deny evidence found",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["operator_handoff_summary"] == expected_summary

    def test_result_handles_missing_operator_handoff_summary_gracefully(self, client):
        request_id = "61616161-6161-6161-6161-616161616161"
        with patch(
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
                    "operator_handoff_summary": "",
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Telemetry incomplete",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["operator_handoff_summary"] is None

    @pytest.mark.parametrize(
        ("destination_type", "destination_value", "port"),
        [
            (DestinationType.FQDN, "api.example.com", None),
            (DestinationType.IP, "10.20.30.40", 8443),
            (None, None, None),
        ],
    )
    def test_result_includes_destination_context_for_ticket_handoff(
        self,
        client,
        destination_type,
        destination_value,
        port,
    ):
        request_id = "5c5c5c5c-5c5c-5c5c-5c5c-5c5c5c5c5c5c"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": destination_type,
                "destination_value": destination_value,
                "port": port,
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
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Insufficient evidence",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["destination_type"] == (
            destination_type.value if isinstance(destination_type, DestinationType) else None
        )
        assert resp.json()["destination_value"] == destination_value
        assert resp.json()["destination_port"] == port

    def test_result_includes_time_window_context_from_request_record(self, client):
        request_id = "5a5a5a5a-5a5a-5a5a-5a5a-5a5a5a5a5a5a"
        with patch(
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
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Insufficient evidence",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["time_window_start"] == "2026-03-08T00:00:00Z"
        assert resp.json()["time_window_end"] == "2026-03-08T00:15:00Z"

    @pytest.mark.parametrize(
        ("time_window_start", "time_window_end"),
        [
            (None, "2026-03-08T00:15:00Z"),
            ("2026-03-08T00:00:00Z", None),
            (None, None),
        ],
    )
    def test_result_handles_partial_or_missing_time_window_context(
        self,
        client,
        time_window_start,
        time_window_end,
    ):
        request_id = "5b5b5b5b-5b5b-5b5b-5b5b-5b5b5b5b5b5b"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": 443,
                "time_window_start": time_window_start,
                "time_window_end": time_window_end,
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
                    "summary": "Insufficient evidence.",
                    "observed_facts": [],
                    "routing_recommendation": {
                        "owner_team": "Unknown",
                        "reason": "Insufficient evidence",
                        "next_steps": [],
                    },
                    "created_at": "2026-03-08T00:00:00Z",
                }
            ),
        ):
            resp = client.get(f"/api/v1/requests/{request_id}/result")

        assert resp.status_code == 200
        assert resp.json()["time_window_start"] == time_window_start
        assert resp.json()["time_window_end"] == time_window_end


class TestUIRoutes:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Am I Blocked" in resp.text

    def test_request_page_pending(self, client):
        request_id = "33333333-3333-3333-3333-333333333333"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.PENDING,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
                "time_window_start": "2026-03-08T00:00:00Z",
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_request_page_renders_source_readiness_summary(self, client):
        request_id = "67676767-6767-6767-6767-676767676767"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [
                    "One or more data sources were degraded or unavailable, which reduced confidence."
                ],
                "source_readiness_summary": {
                    "total_sources": 3,
                    "available_sources": ["panos"],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": ["torq"],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Source readiness" in resp.text
        assert "Sources checked:" in resp.text
        assert "Unavailable: scm" in resp.text

    def test_request_page_renders_source_readiness_details(self, client):
        request_id = "68686868-6868-6868-6868-686868686868"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [
                    "One or more data sources were degraded or unavailable, which reduced confidence."
                ],
                "source_readiness_summary": {
                    "total_sources": 2,
                    "available_sources": ["panos"],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "source_readiness_details": [
                    {
                        "source": "scm",
                        "status": "timeout",
                        "reason": "SCM auth probe timed out",
                        "latency_ms": None,
                    }
                ],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Source readiness details" in resp.text
        assert "Status: <strong>timeout</strong>" in resp.text
        assert "Reason: SCM auth probe timed out" in resp.text

    def test_request_page_renders_observed_fact_summary(self, client):
        request_id = "69696969-6969-6969-6969-696969696969"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.9,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 3,
                    "authoritative_facts": 2,
                    "enrichment_only_facts": 1,
                    "authoritative_sources": ["panos", "scm"],
                    "enrichment_only_sources": ["logscale"],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "policy deny found",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Evidence summary" in resp.text
        assert "Observed facts: <strong>3</strong>" in resp.text
        assert "Authoritative sources: panos, scm" in resp.text
        assert "Enrichment-only sources: logscale" in resp.text

    def test_request_page_renders_routing_recommendation_reason_in_context_block(self, client):
        request_id = "70707070-7070-7070-7070-707070707070"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.9,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 1,
                    "authoritative_facts": 1,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": ["panos"],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem policy deny evidence matches destination and port.",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert (
            "Routing context: On-prem policy deny evidence matches destination and port."
            in resp.text
        )

    def test_request_page_hides_empty_routing_recommendation_reason(self, client):
        request_id = "71717171-7171-7171-7171-717171717171"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": [],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 0,
                    "authoritative_facts": 0,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": [],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Routing context:" not in resp.text

    def test_request_page_renders_time_window_range_in_context_block(self, client):
        request_id = "72727272-7272-7272-7272-727272727272"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.9,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 1,
                    "authoritative_facts": 1,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": ["panos"],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem policy deny evidence matches destination and port.",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Time window:" in resp.text
        assert "2026-03-08T00:00:00Z to 2026-03-08T00:15:00Z" in resp.text

    def test_request_page_renders_partial_time_window_context(self, client):
        request_id = "73737373-7373-7373-7373-737373737373"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": 443,
                "time_window_start": None,
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
            },
        ), patch(
            "am_i_blocked_api.routes.api._load_result_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": [],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 0,
                    "authoritative_facts": 0,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": [],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Time window:" in resp.text
        assert "end 2026-03-08T00:15:00Z" in resp.text

    def test_request_page_hides_time_window_when_values_missing(self, client):
        request_id = "74747474-7474-7474-7474-747474747474"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.COMPLETE,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": 443,
                "time_window_start": None,
                "time_window_end": None,
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
            },
        ), patch(
            "am_i_blocked_api.routes.api._load_result_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": [],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 0,
                    "authoritative_facts": 0,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": [],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Time window:" not in resp.text

    @pytest.mark.parametrize(
        (
            "destination_type",
            "destination_value",
            "destination_port",
            "expected_fragment",
            "expected_type_fragment",
        ),
        [
            ("fqdn", "api.example.com", None, "api.example.com", "(fqdn)"),
            ("ip", "10.20.30.40", 8443, "10.20.30.40:8443", "(ip)"),
            (None, None, None, None, None),
        ],
    )
    def test_request_page_destination_context_line_behaves_gracefully(
        self,
        client,
        destination_type,
        destination_value,
        destination_port,
        expected_fragment,
        expected_type_fragment,
    ):
        request_id = "75757575-7575-7575-7575-757575757575"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "destination_type": destination_type,
                "destination_value": destination_value,
                "destination_port": destination_port,
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": [],
                    "unavailable_sources": ["scm"],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 0,
                    "authoritative_facts": 0,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": [],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        if expected_fragment is None:
            assert "Destination:" not in resp.text
        else:
            assert "Destination:" in resp.text
            assert expected_fragment in resp.text
            if expected_type_fragment is not None:
                assert expected_type_fragment in resp.text

    def test_request_page_renders_compact_operator_handoff_context_block(self, client):
        request_id = "76767676-7676-7676-7676-767676767676"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "destination_type": "fqdn",
                "destination_value": "api.example.com",
                "destination_port": 443,
                "enforcement_plane": "onprem_palo",
                "path_context": "campus_non_sdwan",
                "path_confidence": 0.9,
                "result_confidence": 0.9,
                "evidence_completeness": 0.9,
                "summary": "Authoritative policy deny was observed.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 1,
                    "available_sources": ["panos"],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_fact_summary": {
                    "total_facts": 1,
                    "authoritative_facts": 1,
                    "enrichment_only_facts": 0,
                    "authoritative_sources": ["panos"],
                    "enrichment_only_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem policy deny evidence matches destination and port.",
                    "next_steps": [],
                },
                "operator_handoff_summary": (
                    "verdict=denied; path=campus_non_sdwan; enforcement=onprem_palo; "
                    "authoritative_facts=1; ready_sources=1; unavailable_sources=0; "
                    "routing_reason=On-prem policy deny evidence matches destination and port."
                ),
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Routing context: On-prem policy deny evidence matches destination and port." in resp.text
        assert "Handoff summary:" in resp.text
        assert "verdict=denied; path=campus_non_sdwan; enforcement=onprem_palo;" in resp.text
        assert "Destination:" in resp.text
        assert "api.example.com:443" in resp.text
        assert "(fqdn)" in resp.text
        assert "Time window:" in resp.text
        assert "2026-03-08T00:00:00Z to 2026-03-08T00:15:00Z" in resp.text

    def test_request_page_handles_missing_source_readiness_details(self, client):
        request_id = "69696969-6969-6969-6969-696969696969"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "source_readiness_summary": {
                    "total_sources": 0,
                    "available_sources": [],
                    "unavailable_sources": [],
                    "unknown_sources": [],
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "No per-source readiness details available." in resp.text

    def test_request_page_unknown_returns_404(self, client):
        resp = client.get("/requests/00000000-0000-0000-0000-000000000002")
        assert resp.status_code == 404

    def test_request_page_failed_shows_reason(self, client):
        request_id = "44444444-4444-4444-4444-444444444444"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.FAILED,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
                "time_window_start": "2026-03-08T00:00:00Z",
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
                "failure_reason": "queue timeout",
                "failure_stage": "queue_enqueue",
                "failure_category": "dependency",
            },
        ):
            resp = client.get(f"/requests/{request_id}")
        assert resp.status_code == 200
        assert "Failure reason: queue timeout" in resp.text
        assert "Failure stage: queue_enqueue" in resp.text
        assert "Failure category: dependency" in resp.text
        assert "First-hop triage" in resp.text
        assert "Suggested action: Check Redis queue availability and worker queue connectivity, then retry." in resp.text

    def test_request_page_failed_unknown_category_uses_generic_hint(self, client):
        request_id = "55555555-5555-5555-5555-555555555555"
        with patch(
            "am_i_blocked_api.routes.api._load_request_record",
            new_callable=AsyncMock,
            return_value={
                "request_id": request_id,
                "status": RequestStatus.FAILED,
                "destination_type": DestinationType.FQDN,
                "destination_value": "api.example.com",
                "port": None,
                "time_window_start": "2026-03-08T00:00:00Z",
                "time_window_end": "2026-03-08T00:15:00Z",
                "requester": "anonymous",
                "created_at": "2026-03-08T00:00:00Z",
                "failure_reason": "unexpected fault",
                "failure_stage": "non_standard_stage",
                "failure_category": "non_standard_category",
            },
        ):
            resp = client.get(f"/requests/{request_id}")
        assert resp.status_code == 200
        assert "Suggested action: Capture request id and logs, then escalate for manual triage." in resp.text

    def test_request_page_result_labels_enrichment_and_authoritative_facts(self, client):
        request_id = "66666666-6666-6666-6666-666666666666"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "On-prem PAN deny: rule=block-ext",
                        "detail": {"action": "deny", "rule_name": "block-ext"},
                    },
                    {
                        "source": "logscale",
                        "summary": "LogScale enrichment-only signal (UNVERIFIED) observed; excluded from deny authority decisions.",
                        "detail": {
                            "classification_role": "enrichment_only_unverified",
                            "authoritative": False,
                        },
                    },
                ],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "Telemetry incomplete",
                    "next_steps": ["Check source readiness"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Authoritative signal" in resp.text
        assert "Enrichment only" in resp.text

    def test_request_page_result_includes_evidence_bundle_download_link(self, client):
        request_id = "88888888-8888-8888-8888-888888888888"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.2,
                "summary": "Insufficient evidence.",
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Telemetry incomplete",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert f"/api/v1/requests/{request_id}/result/evidence-bundle" in resp.text
        assert f"/api/v1/requests/{request_id}/result/handoff-note" in resp.text
        assert 'id="copy-handoff-note-btn"' in resp.text
        assert 'id="copy-handoff-note-status"' in resp.text
        assert 'id="copy-handoff-note-fallback"' in resp.text
        assert 'id="copy-handoff-note-fallback-link"' in resp.text
        assert "Copy handoff note" in resp.text
        assert "Copy failed. Use" in resp.text
        assert "navigator.clipboard.writeText" in resp.text
        assert "fetch(noteUrl" in resp.text

    def test_request_page_unknown_renders_confidence_signals(self, client):
        request_id = "91919191-9191-9191-9191-919191919191"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "result_confidence": 0.2,
                "evidence_completeness": 0.3,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [
                    "No authoritative deny evidence was found; this is not confirmation that access is allowed.",
                    "Path context confidence is low, so route or policy context may be incomplete.",
                ],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Why this is unknown" in resp.text
        assert "Unknown is not the same as allowed. A missing deny signal is not proof of allow." in resp.text
        assert "Path confidence: <strong>20%</strong>" in resp.text
        assert "Evidence completeness: <strong>30%</strong>" in resp.text
        assert (
            "<li>No authoritative deny evidence was found; this is not confirmation that access is allowed.</li>"
            in resp.text
        )
        assert (
            "<li>Path context confidence is low, so route or policy context may be incomplete.</li>" in resp.text
        )

    def test_request_page_unknown_without_reason_signals_uses_fallback_message(self, client):
        request_id = "92929292-9292-9292-9292-929292929292"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "unknown",
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.6,
                "result_confidence": 0.3,
                "evidence_completeness": 0.7,
                "summary": "Insufficient evidence.",
                "unknown_reason_signals": [],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "Why this is unknown" in resp.text
        assert (
            "No additional confidence-reducing signals were recorded for this unknown result." in resp.text
        )

    def test_request_page_renders_panos_rule_metadata_when_present(self, client):
        request_id = "98989898-9898-9898-9898-989898989898"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "vpn_gp_onprem_static",
                "path_confidence": 0.8,
                "result_confidence": 0.85,
                "evidence_completeness": 0.8,
                "summary": "On-prem PAN-OS deny detected.",
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "On-prem PAN deny: rule=block-ext",
                        "detail": {
                            "action": "deny",
                            "authoritative": True,
                            "rule_metadata": {
                                "rule_name": "block-ext",
                                "action": "deny",
                                "description": "Block external traffic",
                                "disabled": False,
                                "tags": ["internet", "critical"],
                            },
                        },
                    }
                ],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem PAN deny evidence found",
                    "next_steps": ["Review PAN-OS rule"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "PAN-OS rule metadata" in resp.text
        assert "<strong>Rule</strong>: block-ext" in resp.text
        assert "<strong>Action</strong>: deny" in resp.text
        assert "<strong>Description</strong>: Block external traffic" in resp.text
        assert "<strong>Disabled</strong>: no" in resp.text
        assert "<strong>Tags</strong>: internet, critical" in resp.text

    def test_request_page_omits_panos_rule_metadata_when_absent(self, client):
        request_id = "78787878-7878-7878-7878-787878787878"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "vpn_gp_onprem_static",
                "path_confidence": 0.8,
                "result_confidence": 0.85,
                "evidence_completeness": 0.8,
                "summary": "On-prem PAN-OS deny detected.",
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "On-prem PAN deny: rule=block-ext",
                        "detail": {
                            "action": "deny",
                            "authoritative": True,
                        },
                    }
                ],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem PAN deny evidence found",
                    "next_steps": ["Review PAN-OS rule"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "PAN-OS rule metadata" not in resp.text

    def test_request_page_handles_malformed_panos_rule_metadata_gracefully(self, client):
        request_id = "67676767-6767-6767-6767-676767676767"
        with patch(
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
            return_value={
                "request_id": request_id,
                "verdict": "denied",
                "enforcement_plane": "onprem_palo",
                "path_context": "vpn_gp_onprem_static",
                "path_confidence": 0.8,
                "result_confidence": 0.85,
                "evidence_completeness": 0.8,
                "summary": "On-prem PAN-OS deny detected.",
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "On-prem PAN deny: rule=block-ext",
                        "detail": {
                            "action": "deny",
                            "authoritative": True,
                            "rule_metadata": "not-a-dict",
                        },
                    }
                ],
                "routing_recommendation": {
                    "owner_team": "SecOps",
                    "reason": "On-prem PAN deny evidence found",
                    "next_steps": ["Review PAN-OS rule"],
                },
                "created_at": "2026-03-08T00:00:00Z",
            },
        ):
            resp = client.get(f"/requests/{request_id}")

        assert resp.status_code == 200
        assert "On-prem PAN deny: rule=block-ext" in resp.text
        assert "PAN-OS rule metadata" not in resp.text


class _FakeResultSession:
    def __init__(self, row):
        self._row = row

    async def get(self, model, key):  # type: ignore[no-untyped-def]
        if model.__name__ == "ResultRow":
            return self._row
        return None


class _FakeResultSessionContext:
    def __init__(self, row):
        self._session = _FakeResultSession(row)

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
        return None


def _fake_result_session_factory(row):
    def _factory():
        return _FakeResultSessionContext(row)

    return _factory


class TestLoadResultRecordConfidenceFallback:
    @pytest.mark.anyio
    async def test_load_result_record_unknown_derives_reasons_from_confidence_and_readiness(self):
        request_id = uuid.UUID("31313131-3131-3131-3131-313131313131")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.2,
            evidence_completeness=0.2,
            summary="Insufficient evidence to determine verdict.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "source_readiness": {
                    "panos": {"available": False, "reason": "not configured"},
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.unknown_reason_signals == [
            "No authoritative deny evidence was found; this is not confirmation that access is allowed.",
            "One or more data sources were degraded or unavailable, which reduced confidence.",
            "Path context confidence is low, so route or policy context may be incomplete.",
            "Bounded checks were inconclusive or incomplete for this time window.",
        ]
        assert result.source_readiness_summary.total_sources == 1
        assert result.source_readiness_summary.unavailable_sources == ["panos"]
        assert len(result.source_readiness_details) == 1
        assert result.source_readiness_details[0].source == "panos"
        assert result.source_readiness_details[0].status == "unavailable"

    @pytest.mark.anyio
    async def test_load_result_record_unknown_handles_missing_or_malformed_confidence_values(self):
        request_id = uuid.UUID("32323232-3232-3232-3232-323232323232")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.2,
            evidence_completeness=0.2,
            summary="Insufficient evidence.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": "not-a-number",
                "unknown_reason_signals": ["custom reason"],
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )
        row.evidence_completeness = None  # type: ignore[assignment]
        row.result_confidence = "bad"  # type: ignore[assignment]

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.path_confidence == 0.0
        assert result.evidence_completeness == 0.0
        assert result.result_confidence == 0.0
        assert result.unknown_reason_signals == ["custom reason"]
        assert result.source_readiness_summary.total_sources == 0
        assert result.source_readiness_details == []

    @pytest.mark.anyio
    async def test_load_result_record_handles_partial_or_malformed_readiness_entries(self):
        request_id = uuid.UUID("33333333-4444-5555-6666-777777777777")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.1,
            evidence_completeness=0.1,
            summary="Insufficient evidence.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.1,
                "source_readiness": {
                    "scm": {"status": "auth_failed", "reason": "bad token"},
                    "panos": {"available": True},
                    "logscale": {"latency_ms": 7},
                    "torq": "bad-shape",
                },
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        details = {item.source: item for item in result.source_readiness_details}
        assert details["scm"].status == "auth_failed"
        assert details["scm"].reason == "bad token"
        assert details["panos"].status == "ready"
        assert details["logscale"].status == "unknown"
        assert "torq" not in details

    @pytest.mark.anyio
    async def test_load_result_record_summarizes_observed_fact_authority_mix(self):
        request_id = uuid.UUID("44444444-5555-6666-7777-888888888888")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.1,
            evidence_completeness=0.1,
            summary="Insufficient evidence.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.1,
                "observed_facts": [
                    {
                        "source": "panos",
                        "summary": "Policy deny observed",
                        "detail": {"action": "deny", "authoritative": True},
                    },
                    {
                        "source": "logscale",
                        "summary": "enrichment record",
                        "detail": {"classification_role": "enrichment_only_unverified"},
                    },
                    {
                        "source": "scm",
                        "summary": "authoritative deny",
                        "detail": {"authoritative": True},
                    },
                ],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Insufficient evidence",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.observed_fact_summary.total_facts == 3
        assert result.observed_fact_summary.authoritative_facts == 2
        assert result.observed_fact_summary.enrichment_only_facts == 1
        assert result.observed_fact_summary.authoritative_sources == ["panos", "scm"]
        assert result.observed_fact_summary.enrichment_only_sources == ["logscale"]

    @pytest.mark.anyio
    async def test_load_result_record_handles_missing_or_null_routing_reason_gracefully(self):
        request_id = uuid.UUID("99999999-aaaa-bbbb-cccc-111111111111")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.2,
            evidence_completeness=0.2,
            summary="Insufficient evidence.",
            next_steps_json=["check source health"],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": None,
                    "next_steps": ["  ", "retry after readiness recovery"],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.routing_recommendation.owner_team == "Unknown"
        assert result.routing_recommendation.reason == "loaded from persisted result"
        assert result.routing_recommendation.next_steps == ["retry after readiness recovery"]

    @pytest.mark.anyio
    async def test_load_result_record_includes_operator_handoff_summary_when_present(self):
        request_id = uuid.UUID("12121212-3434-5656-7878-909090909090")
        summary = (
            "verdict=unknown; path=unknown; enforcement=unknown; "
            "authoritative_facts=0; ready_sources=1; unavailable_sources=1; routing_reason=Telemetry incomplete"
        )
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.2,
            evidence_completeness=0.2,
            summary="Insufficient evidence.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "operator_handoff_summary": summary,
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Telemetry incomplete",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.operator_handoff_summary == summary

    @pytest.mark.anyio
    async def test_load_result_record_ignores_blank_operator_handoff_summary(self):
        request_id = uuid.UUID("98989898-7676-5454-3232-101010101010")
        row = api_routes.ResultRow(
            request_id=request_id,
            verdict="unknown",
            owner_team="Unknown",
            result_confidence=0.2,
            evidence_completeness=0.2,
            summary="Insufficient evidence.",
            next_steps_json=[],
            report_json={
                "enforcement_plane": "unknown",
                "path_context": "unknown",
                "path_confidence": 0.2,
                "operator_handoff_summary": "   ",
                "observed_facts": [],
                "routing_recommendation": {
                    "owner_team": "Unknown",
                    "reason": "Telemetry incomplete",
                    "next_steps": [],
                },
                "generated_at": "2026-03-08T00:00:00Z",
            },
        )

        with patch(
            "am_i_blocked_api.routes.api.get_settings",
            return_value=SimpleNamespace(database_url="postgresql+psycopg://test/routes"),
        ), patch(
            "am_i_blocked_api.routes.api._get_session_factory",
            return_value=_fake_result_session_factory(row),
        ):
            result = await _ORIG_LOAD_RESULT_RECORD(request_id)

        assert result is not None
        assert result.operator_handoff_summary is None
