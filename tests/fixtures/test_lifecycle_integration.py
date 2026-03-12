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


class _FakeSCMAdapter:
    def __init__(self, mode: str, request_id: str) -> None:
        self._mode = mode
        self._request_id = request_id

    async def query_evidence(self, **kwargs) -> list[EvidenceRecord]:  # type: ignore[no-untyped-def]
        req_id = kwargs.get("request_id", self._request_id)
        request_uuid = uuid.UUID(req_id)
        if self._mode == "deny":
            return [
                EvidenceRecord(
                    request_id=request_uuid,
                    source=EvidenceSource.SCM,
                    kind=EvidenceKind.TRAFFIC_LOG,
                    normalized={
                        "authoritative": True,
                        "action": "deny",
                        "decision": "deny",
                        "source_system": "strata_cloud_manager",
                        "destination": "api.example.com",
                        "port": 443,
                        "event_ts": "2026-01-01T00:10:00Z",
                        "rule_name": "cloud-block",
                        "rule_id": "policy-123",
                        "reason": "Cloud policy deny",
                    },
                )
            ]
        if self._mode == "decrypt_deny":
            return [
                EvidenceRecord(
                    request_id=request_uuid,
                    source=EvidenceSource.SCM,
                    kind=EvidenceKind.DECRYPT_LOG,
                    normalized={
                        "authoritative": True,
                        "action": "decrypt_deny",
                        "decision": "decrypt-deny",
                        "source_system": "prisma_access",
                        "destination": "api.example.com",
                        "port": 443,
                        "event_ts": "2026-01-01T00:10:00Z",
                        "decrypt_error": "Certificate inspection blocked by policy",
                        "reason": "Decryption policy deny",
                    },
                )
            ]
        if self._mode == "non_authoritative_deny":
            # Intentionally deny-like shape that should fail authority gate because authoritative=false.
            return [
                EvidenceRecord(
                    request_id=request_uuid,
                    source=EvidenceSource.SCM,
                    kind=EvidenceKind.TRAFFIC_LOG,
                    normalized={
                        "authoritative": False,
                        "action": "deny",
                        "decision": "deny",
                        "source_system": "strata_cloud_manager",
                        "destination": "api.example.com",
                        "port": 443,
                        "event_ts": "2026-01-01T00:10:00Z",
                        "rule_name": "cloud-block-should-drop",
                        "reason": "Non-authoritative deny-like signal",
                    },
                )
            ]
        if self._mode == "malformed_decision_shape":
            # Intentionally deny-like candidate with malformed decision structure and no usable action.
            # This should fail closed and never become authoritative deny evidence.
            return [
                EvidenceRecord(
                    request_id=request_uuid,
                    source=EvidenceSource.SCM,
                    kind=EvidenceKind.TRAFFIC_LOG,
                    normalized={
                        "authoritative": True,
                        "decision": {"value": "deny"},
                        "source_system": "strata_cloud_manager",
                        "destination": "api.example.com",
                        "port": 443,
                        "event_ts": "2026-01-01T00:10:00Z",
                        "rule_name": "cloud-block-malformed",
                        "reason": "Malformed decision structure",
                    },
                )
            ]
        return []


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


def _readiness_report(source: str = "panos") -> ReadinessReport:
    report = ReadinessReport()
    report.record(source, {"available": True, "reason": "test", "latency_ms": 1})
    return report


def _mixed_readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "status": "ready", "reason": "probe ok", "latency_ms": 5})
    report.record(
        "scm",
        {"available": False, "status": "not_configured", "reason": "missing credentials", "latency_ms": None},
    )
    report.record(
        "sdwan",
        {"available": False, "status": "auth_failed", "reason": "invalid api key", "latency_ms": 7},
    )
    report.record("torq", {"available": False, "status": "timeout", "reason": "request timed out", "latency_ms": None})
    return report


def _fallback_readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "status": "ready", "reason": "probe ok", "latency_ms": 5})
    report.record("scm", {"available": True, "reason": "configured and reachable", "latency_ms": 11})
    report.record("sdwan", {"available": False, "reason": "auth error", "latency_ms": 9})
    report.record("torq", {"reason": "status missing and available missing", "latency_ms": None})
    return report


def _details_skip_readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "status": "ready", "reason": "probe ok", "latency_ms": 3})
    report.record("scm", {"available": True, "reason": "reachable"})
    report.record("logscale", {})
    return report


def _nondict_readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "status": "ready", "reason": "probe ok", "latency_ms": 4})
    report.record("scm", {"available": True, "reason": "reachable"})
    report.sources["torq"] = "non-dict-shape"
    return report


def _bundle_readiness_report() -> ReadinessReport:
    report = ReadinessReport()
    report.record("panos", {"available": True, "status": "ready", "reason": "probe ok", "latency_ms": 6})
    report.record("scm", {"available": True, "reason": "reachable", "latency_ms": 8})
    report.record("sdwan", {"available": False, "status": "timeout", "reason": "upstream timeout", "latency_ms": 13})
    return report


async def _run_lifecycle_case(
    deny: bool,
    *,
    metadata_mode: str = "none",
    source: str = "panos",
    scm_mode: str = "deny",
    readiness_report: ReadinessReport | None = None,
    bundle_sink: dict[str, object] | None = None,
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
    if source == "scm":
        fake_adapter = _FakeSCMAdapter(mode=scm_mode, request_id=str(uuid.uuid4()))
    else:
        fake_adapter = _FakePanosAdapter(
            deny=deny,
            request_id=str(uuid.uuid4()),
            metadata_mode=metadata_mode,
        )
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
        return_value=readiness_report or _readiness_report(source=source),
    ), patch(
        "am_i_blocked_worker.main.dequeue_job",
        side_effect=_dequeue_job,
    ), patch(
        "am_i_blocked_worker.steps.authoritative_correlation._build_adapter",
        return_value=fake_adapter,
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
        bundle_resp = client.get(f"/api/v1/requests/{request_id}/result/evidence-bundle")
        assert bundle_resp.status_code == 200
        ui_resp = client.get(f"/requests/{request_id}")
        assert ui_resp.status_code == 200
        if bundle_sink is not None:
            bundle_sink["payload"] = bundle_resp.json()
            bundle_sink["content_disposition"] = bundle_resp.headers.get("Content-Disposition")

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


@pytest.mark.anyio
async def test_lifecycle_scm_authoritative_deny_survives_persist_and_result_api() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=True,
        source="scm",
        scm_mode="deny",
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value
    assert result["verdict"] == "denied"
    assert result["enforcement_plane"] == "strata_cloud"

    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    scm_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "scm"
        and ev.get("normalized", {}).get("authoritative") is True
        and ev.get("normalized", {}).get("action") == "deny"
    ]
    assert len(scm_deny) == 1
    assert scm_deny[0]["normalized"]["source_system"] == "strata_cloud_manager"
    assert scm_deny[0]["normalized"]["rule_name"] == "cloud-block"


@pytest.mark.anyio
async def test_lifecycle_scm_authoritative_decrypt_deny_survives_persist_and_result_api() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=True,
        source="scm",
        scm_mode="decrypt_deny",
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value
    assert result["verdict"] == "denied"

    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    scm_decrypt_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "scm"
        and ev.get("kind") == "decrypt_log"
        and ev.get("normalized", {}).get("authoritative") is True
        and ev.get("normalized", {}).get("action") == "decrypt_deny"
    ]
    assert len(scm_decrypt_deny) == 1
    assert "decrypt_error" in scm_decrypt_deny[0]["normalized"]
    assert scm_decrypt_deny[0]["normalized"]["source_system"] == "prisma_access"


@pytest.mark.anyio
async def test_lifecycle_scm_non_authoritative_deny_fails_closed_and_not_denied() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=True,
        source="scm",
        scm_mode="non_authoritative_deny",
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # Deny-like SCM record is present at adapter output but must be dropped before authority.
    assert result["verdict"] != "denied"

    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    scm_authoritative_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "scm"
        and ev.get("normalized", {}).get("action") == "deny"
        and ev.get("normalized", {}).get("authoritative") is True
    ]
    assert scm_authoritative_deny == []


@pytest.mark.anyio
async def test_lifecycle_scm_malformed_decision_shape_fails_closed_and_not_denied() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=True,
        source="scm",
        scm_mode="malformed_decision_shape",
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # SCM candidate resembles deny context but malformed decision shape must fail closed.
    assert result["verdict"] != "denied"

    evidence_records = db.results[request_id].report_json.get("evidence_records", [])
    scm_authoritative_deny = [
        ev
        for ev in evidence_records
        if ev.get("source") == "scm"
        and ev.get("normalized", {}).get("action") == "deny"
        and ev.get("normalized", {}).get("authoritative") is True
    ]
    assert scm_authoritative_deny == []


@pytest.mark.anyio
async def test_lifecycle_mixed_source_readiness_survives_persist_and_result_api() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        readiness_report=_mixed_readiness_report(),
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    persisted_readiness = db.results[request_id].report_json.get("source_readiness")
    assert isinstance(persisted_readiness, dict)
    assert persisted_readiness["panos"]["status"] == "ready"
    assert persisted_readiness["scm"]["status"] == "not_configured"
    assert persisted_readiness["sdwan"]["status"] == "auth_failed"
    assert persisted_readiness["torq"]["status"] == "timeout"

    summary = result["source_readiness_summary"]
    assert summary == {
        "total_sources": 4,
        "available_sources": ["panos"],
        "unavailable_sources": ["scm", "sdwan", "torq"],
        "unknown_sources": [],
    }

    details = {item["source"]: item for item in result["source_readiness_details"]}
    assert set(details) == {"panos", "scm", "sdwan", "torq"}
    assert details["panos"]["status"] == "ready"
    assert details["panos"]["reason"] == "probe ok"
    assert details["panos"]["latency_ms"] == 5

    assert details["scm"]["status"] == "not_configured"
    assert details["scm"]["reason"] == "missing credentials"
    assert details["scm"]["latency_ms"] is None

    assert details["sdwan"]["status"] == "auth_failed"
    assert details["sdwan"]["reason"] == "invalid api key"
    assert details["sdwan"]["latency_ms"] == 7

    assert details["torq"]["status"] == "timeout"
    assert details["torq"]["reason"] == "request timed out"
    assert details["torq"]["latency_ms"] is None


@pytest.mark.anyio
async def test_lifecycle_source_readiness_fallback_status_survives_persist_and_result_api() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        readiness_report=_fallback_readiness_report(),
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    persisted_readiness = db.results[request_id].report_json.get("source_readiness")
    assert isinstance(persisted_readiness, dict)
    assert "status" not in persisted_readiness["scm"]
    assert "status" not in persisted_readiness["sdwan"]
    assert "status" not in persisted_readiness["torq"]

    summary = result["source_readiness_summary"]
    assert summary == {
        "total_sources": 4,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": ["sdwan"],
        "unknown_sources": ["torq"],
    }

    details = {item["source"]: item for item in result["source_readiness_details"]}
    assert set(details) == {"panos", "scm", "sdwan", "torq"}

    # Explicit status remains unchanged.
    assert details["panos"]["status"] == "ready"
    assert details["panos"]["reason"] == "probe ok"
    assert details["panos"]["latency_ms"] == 5

    # Fallback derivation from available flag remains stable end-to-end.
    assert details["scm"]["status"] == "ready"
    assert details["scm"]["reason"] == "configured and reachable"
    assert details["scm"]["latency_ms"] == 11

    assert details["sdwan"]["status"] == "unavailable"
    assert details["sdwan"]["reason"] == "auth error"
    assert details["sdwan"]["latency_ms"] == 9

    assert details["torq"]["status"] == "unknown"
    assert details["torq"]["reason"] == "status missing and available missing"
    assert details["torq"]["latency_ms"] is None


@pytest.mark.anyio
async def test_lifecycle_source_readiness_details_skip_meaningless_entries() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        readiness_report=_details_skip_readiness_report(),
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    persisted_readiness = db.results[request_id].report_json.get("source_readiness")
    assert isinstance(persisted_readiness, dict)
    assert persisted_readiness["logscale"] == {}

    summary = result["source_readiness_summary"]
    assert summary == {
        "total_sources": 3,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": [],
        "unknown_sources": ["logscale"],
    }

    details = {item["source"]: item for item in result["source_readiness_details"]}
    assert set(details) == {"panos", "scm"}
    assert "logscale" not in details

    assert details["panos"]["status"] == "ready"
    assert details["panos"]["reason"] == "probe ok"
    assert details["panos"]["latency_ms"] == 3

    assert details["scm"]["status"] == "ready"
    assert details["scm"]["reason"] == "reachable"
    assert details["scm"]["latency_ms"] is None


@pytest.mark.anyio
async def test_lifecycle_source_readiness_nondict_entries_are_unknown_in_summary_and_skipped_in_details() -> None:
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        readiness_report=_nondict_readiness_report(),
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    persisted_readiness = db.results[request_id].report_json.get("source_readiness")
    assert isinstance(persisted_readiness, dict)
    assert persisted_readiness["torq"] == "non-dict-shape"

    summary = result["source_readiness_summary"]
    assert summary == {
        "total_sources": 3,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": [],
        "unknown_sources": ["torq"],
    }

    details = {item["source"]: item for item in result["source_readiness_details"]}
    assert set(details) == {"panos", "scm"}
    assert "torq" not in details

    assert details["panos"]["status"] == "ready"
    assert details["panos"]["reason"] == "probe ok"
    assert details["panos"]["latency_ms"] == 4

    assert details["scm"]["status"] == "ready"
    assert details["scm"]["reason"] == "reachable"
    assert details["scm"]["latency_ms"] is None


@pytest.mark.anyio
async def test_lifecycle_evidence_bundle_includes_source_readiness_summary_and_details() -> None:
    bundle: dict[str, object] = {}
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        readiness_report=_bundle_readiness_report(),
        bundle_sink=bundle,
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value
    assert result["source_readiness_summary"] == {
        "total_sources": 3,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": ["sdwan"],
        "unknown_sources": [],
    }
    result_details = {item["source"]: item for item in result["source_readiness_details"]}
    assert set(result_details) == {"panos", "scm", "sdwan"}
    assert result_details["panos"]["status"] == "ready"
    assert result_details["scm"]["status"] == "ready"
    assert result_details["sdwan"]["status"] == "timeout"

    payload = bundle["payload"]
    assert isinstance(payload, dict)
    assert payload["request_id"] == result["request_id"]
    assert payload["source_readiness_summary"] == result["source_readiness_summary"]
    assert payload["source_readiness_details"] == result["source_readiness_details"]
    assert isinstance(bundle["content_disposition"], str)
    assert f'evidence-{result["request_id"]}.json' in bundle["content_disposition"]


@pytest.mark.anyio
async def test_lifecycle_evidence_bundle_preserves_authoritative_observed_fact_metadata() -> None:
    bundle: dict[str, object] = {}
    result, _ui_html, db = await _run_lifecycle_case(
        deny=True,
        metadata_mode="present",
        readiness_report=_bundle_readiness_report(),
        bundle_sink=bundle,
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    # Normal result path contains authoritative PAN-OS observed-fact metadata.
    panos_fact = next(f for f in result["observed_facts"] if f["source"] == "panos")
    assert panos_fact["detail"]["rule_metadata"]["rule_name"] == "block-ext"
    assert panos_fact["detail"]["rule_metadata"]["action"] == "deny"
    assert panos_fact["detail"]["rule_metadata"]["description"] == "Block external traffic"
    assert panos_fact["detail"]["rule_metadata"]["tags"] == ["internet", "critical"]

    # Readiness parity remains present.
    assert result["source_readiness_summary"] == {
        "total_sources": 3,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": ["sdwan"],
        "unknown_sources": [],
    }
    assert len(result["source_readiness_details"]) == 3

    payload = bundle["payload"]
    assert isinstance(payload, dict)
    bundle_panos_fact = next(f for f in payload["observed_facts"] if f["source"] == "panos")
    assert bundle_panos_fact["detail"]["rule_metadata"] == panos_fact["detail"]["rule_metadata"]
    assert payload["source_readiness_summary"] == result["source_readiness_summary"]
    assert payload["source_readiness_details"] == result["source_readiness_details"]


@pytest.mark.anyio
async def test_lifecycle_evidence_bundle_preserves_unknown_reason_signals_with_readiness_and_metadata_fields() -> None:
    bundle: dict[str, object] = {}
    result, _ui_html, db = await _run_lifecycle_case(
        deny=False,
        source="scm",
        scm_mode="malformed_decision_shape",
        readiness_report=_bundle_readiness_report(),
        bundle_sink=bundle,
    )
    request_id = uuid.UUID(result["request_id"])

    assert request_id in db.requests
    assert request_id in db.results
    assert db.requests[request_id].status == RequestStatus.COMPLETE.value

    assert result["verdict"] == "unknown"
    assert isinstance(result["unknown_reason_signals"], list)
    assert len(result["unknown_reason_signals"]) > 0
    assert result["source_readiness_summary"] == {
        "total_sources": 3,
        "available_sources": ["panos", "scm"],
        "unavailable_sources": ["sdwan"],
        "unknown_sources": [],
    }
    assert len(result["source_readiness_details"]) == 3

    payload = bundle["payload"]
    assert isinstance(payload, dict)
    assert payload["verdict"] == "unknown"
    assert payload["unknown_reason_signals"] == result["unknown_reason_signals"]
    assert payload["source_readiness_summary"] == result["source_readiness_summary"]
    assert payload["source_readiness_details"] == result["source_readiness_details"]
