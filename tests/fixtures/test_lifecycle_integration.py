"""Integration-style lifecycle tests for submit -> queue -> worker -> persist -> result."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from am_i_blocked_api import create_app
from am_i_blocked_core.db_models import AuditRow, RequestRow, ResultRow
from am_i_blocked_core.enums import (
    EvidenceKind,
    EvidenceSource,
    RequestStatus,
)
from am_i_blocked_core.models import EvidenceRecord
from am_i_blocked_worker import main as worker_main
from am_i_blocked_worker.steps.source_readiness_check import ReadinessReport
from fastapi.testclient import TestClient


@dataclass
class _FakeDb:
    requests: dict[uuid.UUID, RequestRow] = field(default_factory=dict)
    results: dict[uuid.UUID, ResultRow] = field(default_factory=dict)
    audit: list[AuditRow] = field(default_factory=list)


class _FakeSession:
    def __init__(self, db: _FakeDb) -> None:
        self._db = db

    async def get(self, model, key):  # type: ignore[no-untyped-def]
        if model is RequestRow:
            return self._db.requests.get(key)
        if model is ResultRow:
            return self._db.results.get(key)
        return None

    def add(self, obj) -> None:  # type: ignore[no-untyped-def]
        if isinstance(obj, RequestRow):
            self._db.requests[obj.request_id] = obj
        elif isinstance(obj, ResultRow):
            self._db.results[obj.request_id] = obj
        elif isinstance(obj, AuditRow):
            self._db.audit.append(obj)

    async def commit(self) -> None:
        return None


class _FakeSessionContext:
    def __init__(self, db: _FakeDb) -> None:
        self._session = _FakeSession(db)

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


def _fake_session_factory(db: _FakeDb):
    def _factory():
        return _FakeSessionContext(db)

    return _factory


class _FakePanosAdapter:
    def __init__(self, deny: bool, request_id: str, metadata_mode: str = "none") -> None:
        self._deny = deny
        self._request_id = request_id
        self._metadata_mode = metadata_mode

    async def query_evidence(self, **kwargs) -> list[EvidenceRecord]:  # type: ignore[no-untyped-def]
        req_id = kwargs.get("request_id", self._request_id)
        request_uuid = uuid.UUID(req_id)
        if self._deny:
            normalized = {
                "action": "deny",
                "action_raw": "reset-client",
                "authoritative": True,
                "rule_name": "block-ext",
                "event_ts": "2026-01-01T00:10:00Z",
            }
            if self._metadata_mode == "present":
                normalized["rule_metadata"] = {
                    "rule_name": "block-ext",
                    "action": "deny",
                    "description": "Block external traffic",
                    "disabled": False,
                    "tags": ["internet", "critical"],
                }
            elif self._metadata_mode == "malformed":
                normalized["rule_metadata"] = "not-a-dict"
            return [
                EvidenceRecord(
                    request_id=request_uuid,
                    source=EvidenceSource.PANOS,
                    kind=EvidenceKind.TRAFFIC_LOG,
                    normalized=normalized,
                )
            ]

        return [
            EvidenceRecord(
                request_id=request_uuid,
                source=EvidenceSource.PANOS,
                kind=EvidenceKind.TRAFFIC_LOG,
                normalized={"action": "allow", "authoritative": True, "rule_name": "allow-ext"},
            ),
            EvidenceRecord(
                request_id=request_uuid,
                source=EvidenceSource.PANOS,
                kind=EvidenceKind.TRAFFIC_LOG,
                normalized={"authoritative": True},
            ),
        ]


def _settings(database_url: str, redis_url: str):
    return SimpleNamespace(
        app_identity_header="X-Forwarded-User",
        anonymous_user="anonymous",
        database_url=database_url,
        redis_url=redis_url,
        panos_fw_hosts=["10.0.0.1"],
        panos_api_key="test-key",
        panos_verify_ssl=False,
        scm_client_id=None,
        scm_client_secret=None,
        scm_tsg_id=None,
        logscale_url=None,
        logscale_token=None,
        logscale_repo=None,
        sdwan_api_url=None,
        sdwan_api_key=None,
        torq_client_id=None,
        torq_client_secret=None,
        enable_bounded_probes=False,
        probe_dns_timeout_s=1.0,
        probe_tcp_timeout_s=1.0,
        probe_tls_timeout_s=1.0,
        probe_http_timeout_s=1.0,
        log_level="WARNING",
        log_format="console",
        worker_concurrency=1,
        job_timeout_s=30,
    )


def _readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "reason": "test", "latency_ms": 1})
    return report


async def _run_lifecycle_case(
    deny: bool,
    *,
    metadata_mode: str = "none",
) -> tuple[dict, str, _FakeDb]:
    db = _FakeDb()
    queue: list[dict] = []
    settings = _settings(
        database_url="postgresql+psycopg://test/lifecycle",
        redis_url="redis://test/0",
    )

    async def _enqueue_job(_redis_url: str, payload: dict) -> None:
        queue.append(payload)

    async def _dequeue_job(_redis_url: str, timeout_s: int = 5) -> dict | None:
        if queue:
            return queue.pop(0)
        return None

    app = create_app()
    with TestClient(app) as client, patch(
        "am_i_blocked_api.routes.api.get_settings",
        return_value=settings,
    ), patch(
        "am_i_blocked_api.routes.api.enqueue_job",
        side_effect=_enqueue_job,
    ), patch(
        "am_i_blocked_api.routes.api._get_session_factory",
        return_value=_fake_session_factory(db),
    ), patch(
        "am_i_blocked_worker.steps.persist_and_report._get_session_factory",
        return_value=_fake_session_factory(db),
    ), patch(
        "am_i_blocked_worker.steps.persist_and_report.get_settings",
        return_value=settings,
    ), patch(
        "am_i_blocked_worker.pipeline.get_settings",
        return_value=settings,
    ), patch(
        "am_i_blocked_worker.steps.source_readiness_check.run",
        return_value=_readiness_report(),
    ), patch(
        "am_i_blocked_worker.main.dequeue_job",
        side_effect=_dequeue_job,
    ), patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=_FakePanosAdapter(
            deny=deny,
            request_id=str(uuid.uuid4()),
            metadata_mode=metadata_mode,
        ),
    ):
        submit = client.post(
            "/api/v1/am-i-blocked",
            json={"destination": "api.example.com", "port": 443, "time_window": "last_15m"},
        )
        assert submit.status_code == 202
        request_id = submit.json()["request_id"]

        # Queue enqueue happened.
        assert len(queue) == 1
        queued_job = queue[0]
        assert queued_job["request_id"] == request_id

        # Worker dequeue + dispatch.
        job = await worker_main.dequeue_job(settings.redis_url)
        assert job is not None
        assert job["request_id"] == request_id
        assert len(queue) == 0
        await worker_main._process_job(job)

        # Result retrieval via API (persisted state).
        result_resp = client.get(f"/api/v1/requests/{request_id}/result")
        assert result_resp.status_code == 200
        ui_resp = client.get(f"/requests/{request_id}")
        assert ui_resp.status_code == 200

    return result_resp.json(), ui_resp.text, db


@pytest.mark.anyio
async def test_lifecycle_deny_path_persists_and_retrieves_panos_metadata_in_api_and_ui() -> None:
    result, ui_html, db = await _run_lifecycle_case(deny=True, metadata_mode="present")
    request_id = uuid.UUID(result["request_id"])

    # Persisted lifecycle state.
    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # Deny verdict from authoritative PAN-OS evidence.
    assert result["verdict"] == "denied"
    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    panos_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "panos"
        and ev.get("normalized", {}).get("action") == "deny"
        and ev.get("normalized", {}).get("authoritative") is True
    ]
    assert panos_deny
    assert panos_deny[0]["normalized"]["rule_metadata"]["rule_name"] == "block-ext"
    assert panos_deny[0]["normalized"]["rule_metadata"]["description"] == "Block external traffic"
    panos_fact_detail = next(f["detail"] for f in result["observed_facts"] if f["source"] == "panos")
    assert panos_fact_detail["rule_metadata"]["rule_name"] == "block-ext"
    assert panos_fact_detail["rule_metadata"]["tags"] == ["internet", "critical"]
    assert "PAN-OS rule metadata" in ui_html
    assert "<strong>Rule</strong>: block-ext" in ui_html
    assert "<strong>Action</strong>: deny" in ui_html


@pytest.mark.anyio
async def test_lifecycle_deny_path_with_malformed_metadata_still_persists_and_renders() -> None:
    result, ui_html, db = await _run_lifecycle_case(deny=True, metadata_mode="malformed")
    request_id = uuid.UUID(result["request_id"])

    # Persisted lifecycle state.
    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # Deny authority remains from PAN-OS deny evidence even when metadata is malformed.
    assert result["verdict"] == "denied"
    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    panos_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "panos"
        and ev.get("normalized", {}).get("action") == "deny"
        and ev.get("normalized", {}).get("authoritative") is True
    ]
    assert panos_deny
    assert panos_deny[0]["normalized"]["rule_metadata"] == "not-a-dict"
    panos_fact_detail = next(f["detail"] for f in result["observed_facts"] if f["source"] == "panos")
    assert panos_fact_detail["rule_metadata"] == "not-a-dict"
    assert "PAN-OS rule metadata" not in ui_html
    assert "On-prem PAN deny: rule=block-ext" in ui_html


@pytest.mark.anyio
async def test_lifecycle_no_authoritative_evidence_does_not_produce_denied() -> None:
    result, _ui_html, db = await _run_lifecycle_case(deny=False)
    request_id = uuid.UUID(result["request_id"])

    # Persisted lifecycle state.
    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # No authoritative deny evidence survives and verdict is not denied.
    assert result["verdict"] != "denied"
    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    panos_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "panos"
        and ev.get("normalized", {}).get("action") == "deny"
        and ev.get("normalized", {}).get("authoritative") is True
    ]
    assert panos_deny == []
