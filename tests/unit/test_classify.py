"""Unit tests for the classification engine."""

from __future__ import annotations

import uuid

from am_i_blocked_core.enums import (
    EnforcementPlane,
    EvidenceKind,
    EvidenceSource,
    OwnerTeam,
    PathContext,
    Verdict,
)
from am_i_blocked_core.models import EvidenceRecord
from am_i_blocked_worker.steps.classify import run


def _req_id() -> str:
    return str(uuid.uuid4())


def _ev(source: EvidenceSource, kind: EvidenceKind, normalized: dict, request_id: str | None = None) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid.uuid4(),
        request_id=uuid.UUID(request_id or _req_id()),
        source=source,
        kind=kind,
        normalized=normalized,
    )


CONTEXT_UNKNOWN = PathContext.UNKNOWN
PLANE_UNKNOWN = EnforcementPlane.UNKNOWN


class TestCloudDenyRule:
    def test_cloud_deny_gives_denied_secops_strata(self):
        evidence = [
            _ev(EvidenceSource.SCM, EvidenceKind.TRAFFIC_LOG, {"action": "deny", "rule_name": "block-saas"})
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=PathContext.VPN_PRISMA_ACCESS,
            enforcement_plane=EnforcementPlane.STRATA_CLOUD,
            path_confidence=0.7,
            available_sources=["scm"],
        )
        assert result.verdict == Verdict.DENIED
        assert result.enforcement_plane == EnforcementPlane.STRATA_CLOUD
        assert result.owner_team == OwnerTeam.SECOPS
        assert result.result_confidence >= 0.8


class TestOnPremDenyRule:
    def test_onprem_deny_gives_denied_secops_onprem(self):
        evidence = [
            _ev(EvidenceSource.PANOS, EvidenceKind.TRAFFIC_LOG, {"action": "deny", "rule_name": "block-ext"})
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=PathContext.VPN_GP_ONPREM_STATIC,
            enforcement_plane=EnforcementPlane.ONPREM_PALO,
            path_confidence=0.5,
            available_sources=["panos"],
        )
        assert result.verdict == Verdict.DENIED
        assert result.enforcement_plane == EnforcementPlane.ONPREM_PALO
        assert result.owner_team == OwnerTeam.SECOPS


class TestDecryptFailureRule:
    def test_decrypt_failure_gives_denied_secops(self):
        evidence = [
            _ev(EvidenceSource.PANOS, EvidenceKind.DECRYPT_LOG, {"decrypt_error": "cert_not_trusted"})
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["panos"],
        )
        assert result.verdict == Verdict.DENIED
        assert result.owner_team == OwnerTeam.SECOPS


class TestSDWANDegradedRule:
    def test_sdwan_degraded_no_deny_gives_unknown_netops(self, sdwan_degraded_evidence):
        result = run(
            evidence=sdwan_degraded_evidence,
            probe_results={},
            path_context=PathContext.SDWAN_OPSCENTER,
            enforcement_plane=EnforcementPlane.ONPREM_PALO,
            path_confidence=0.6,
            available_sources=["sdwan"],
        )
        assert result.verdict == Verdict.UNKNOWN
        assert result.owner_team == OwnerTeam.NETOPS
        assert "path degradation" in result.summary.lower() or "sdwan" in result.summary.lower()


class TestHTTPResponseRule:
    def test_tcp_ok_http_5xx_gives_allowed_or_unknown_appops(self):
        result = run(
            evidence=[],
            probe_results={
                "tcp": {"success": True, "connected": True},
                "http": {"success": True, "status_code": 503},
            },
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=[],
        )
        assert result.verdict in (Verdict.ALLOWED, Verdict.UNKNOWN)
        assert result.owner_team in (OwnerTeam.APPOPS, OwnerTeam.VENDOR)

    def test_tcp_ok_http_200_gives_allowed(self):
        result = run(
            evidence=[],
            probe_results={
                "tcp": {"success": True},
                "http": {"success": True, "status_code": 200},
            },
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=[],
        )
        assert result.verdict == Verdict.ALLOWED


class TestIncompleteTelemetryRule:
    def test_stub_evidence_gives_unknown(self, incomplete_evidence):
        result = run(
            evidence=incomplete_evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["panos", "scm"],
        )
        assert result.verdict == Verdict.UNKNOWN
        assert result.result_confidence <= 0.2


class TestEvidenceCompleteness:
    def test_all_stub_gives_zero_completeness(self, incomplete_evidence):
        result = run(
            evidence=incomplete_evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["panos", "scm"],
        )
        assert result.evidence_completeness == 0.0


class TestLogScaleAuthorityGuards:
    def test_logscale_deny_like_field_does_not_produce_denied(self):
        evidence = [
            _ev(
                EvidenceSource.LOGSCALE,
                EvidenceKind.TRAFFIC_LOG,
                {
                    "action": "deny",
                    "classification_role": "enrichment_only_unverified",
                    "authoritative": False,
                },
            )
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["logscale"],
        )
        assert result.verdict != Verdict.DENIED
        assert result.verdict == Verdict.UNKNOWN

    def test_logscale_decrypt_error_does_not_produce_denied(self):
        evidence = [
            _ev(
                EvidenceSource.LOGSCALE,
                EvidenceKind.DECRYPT_LOG,
                {
                    "decrypt_error": "cert_not_trusted",
                    "classification_role": "enrichment_only_unverified",
                    "authoritative": False,
                },
            )
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["logscale"],
        )
        assert result.verdict != Verdict.DENIED
        assert result.verdict == Verdict.UNKNOWN

    def test_logscale_enrichment_only_is_labeled_in_observed_facts(self):
        evidence = [
            _ev(
                EvidenceSource.LOGSCALE,
                EvidenceKind.TRAFFIC_LOG,
                {
                    "stub": True,
                    "classification_role": "enrichment_only_unverified",
                    "authoritative": False,
                    "repo": "ng-siem",
                    "message": "UNVERIFIED enrichment sample",
                },
            )
        ]
        result = run(
            evidence=evidence,
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=["logscale"],
        )
        assert result.verdict == Verdict.UNKNOWN
        assert any(
            f.source == EvidenceSource.LOGSCALE
            and "enrichment-only signal" in f.summary.lower()
            for f in result.observed_facts
        )

    def test_no_sources_gives_zero_completeness(self):
        result = run(
            evidence=[],
            probe_results={},
            path_context=CONTEXT_UNKNOWN,
            enforcement_plane=PLANE_UNKNOWN,
            path_confidence=0.0,
            available_sources=[],
        )
        assert result.evidence_completeness == 0.0
