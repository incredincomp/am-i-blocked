"""Step 6: Rules-based classification engine."""

from __future__ import annotations

from typing import Any

from am_i_blocked_core.enums import (
    EnforcementPlane,
    EvidenceKind,
    EvidenceSource,
    OwnerTeam,
    PathContext,
    Verdict,
)
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import (
    EvidenceRecord,
    ObservedFact,
    RoutingRecommendation,
)

logger = get_logger(__name__)


def _is_authoritative_for_deny(source: EvidenceSource) -> bool:
    """Return whether source can contribute to deny-authoritative decisions."""
    return source in (EvidenceSource.PANOS, EvidenceSource.SCM)


class ClassificationResult:
    def __init__(
        self,
        verdict: Verdict,
        enforcement_plane: EnforcementPlane,
        owner_team: OwnerTeam,
        result_confidence: float,
        evidence_completeness: float,
        summary: str,
        observed_facts: list[ObservedFact],
        routing_recommendation: RoutingRecommendation,
    ) -> None:
        self.verdict = verdict
        self.enforcement_plane = enforcement_plane
        self.owner_team = owner_team
        self.result_confidence = result_confidence
        self.evidence_completeness = evidence_completeness
        self.summary = summary
        self.observed_facts = observed_facts
        self.routing_recommendation = routing_recommendation


def _evidence_completeness(
    evidence: list[EvidenceRecord],
    available_sources: list[str],
) -> float:
    """Compute evidence completeness as fraction of available sources that returned real data."""
    if not available_sources:
        return 0.0
    sources_with_data = {
        e.source.value for e in evidence if not e.normalized.get("stub", False)
    }
    return len(sources_with_data) / len(available_sources)


def run(
    evidence: list[EvidenceRecord],
    probe_results: dict[str, Any],
    path_context: PathContext,
    enforcement_plane: EnforcementPlane,
    path_confidence: float,
    available_sources: list[str],
) -> ClassificationResult:
    """Apply deterministic classification rules to produce a verdict.

    Rules (evaluated top-down, first match wins):
    1. Cloud policy deny evidence exists → denied / SecOps / strata_cloud
    2. On-prem PAN deny evidence exists → denied / SecOps / onprem_palo
    3. Decrypt failure evidence (strong) → denied / SecOps
    4. SD-WAN degradation + no deny → unknown / NetOps
    5. TCP/TLS success + HTTP 5xx → unknown or allowed / AppOps or Vendor
    6. Fallback: insufficient evidence → unknown
    """
    observed: list[ObservedFact] = []
    completeness = _evidence_completeness(evidence, available_sources)

    # Categorise evidence
    has_cloud_deny = False
    has_onprem_deny = False
    has_decrypt_failure = False
    has_sdwan_degradation = False
    has_any_deny = False

    for ev in evidence:
        if ev.source == EvidenceSource.LOGSCALE and (
            ev.normalized.get("classification_role") == "enrichment_only_unverified"
            or ev.normalized.get("authoritative") is False
        ):
            observed.append(
                ObservedFact(
                    source=ev.source,
                    summary=(
                        "LogScale enrichment-only signal (UNVERIFIED) observed; "
                        "excluded from deny authority decisions."
                    ),
                    detail={
                        "classification_role": ev.normalized.get("classification_role"),
                        "authoritative": ev.normalized.get("authoritative"),
                        "repo": ev.normalized.get("repo"),
                        "message": ev.normalized.get("message"),
                    },
                )
            )
        if ev.normalized.get("stub"):
            continue
        action = ev.normalized.get("action", "").lower()
        if action == "deny" and _is_authoritative_for_deny(ev.source):
            has_any_deny = True
            if ev.source == EvidenceSource.SCM:
                has_cloud_deny = True
                observed.append(
                    ObservedFact(
                        source=ev.source,
                        summary=f"Cloud policy deny: rule={ev.normalized.get('rule_name', 'unknown')}",
                        detail=ev.normalized,
                    )
                )
            elif ev.source == EvidenceSource.PANOS:
                has_onprem_deny = True
                observed.append(
                    ObservedFact(
                        source=ev.source,
                        summary=f"On-prem PAN deny: rule={ev.normalized.get('rule_name', 'unknown')}",
                        detail=ev.normalized,
                    )
                )
        if (
            ev.kind == EvidenceKind.DECRYPT_LOG
            and ev.normalized.get("decrypt_error")
            and _is_authoritative_for_deny(ev.source)
        ):
            has_decrypt_failure = True
            observed.append(
                ObservedFact(
                    source=ev.source,
                    summary="Decrypt failure detected",
                    detail=ev.normalized,
                )
            )
        if ev.kind == EvidenceKind.PATH_SIGNAL and ev.normalized.get("degraded"):
            has_sdwan_degradation = True
            observed.append(
                ObservedFact(
                    source=ev.source,
                    summary="SD-WAN path degradation observed",
                    detail=ev.normalized,
                )
            )

    # Probe facts
    tcp_ok = probe_results.get("tcp", {}).get("success", False)
    tls_ok = probe_results.get("tls", {}).get("success", False)
    http_status = probe_results.get("http", {}).get("status_code")

    if probe_results.get("dns", {}).get("success"):
        observed.append(
            ObservedFact(
                source=EvidenceSource.PROBE_DNS,
                summary=f"DNS resolved: {probe_results['dns'].get('resolved_ips', [])}",
            )
        )
    if tcp_ok:
        observed.append(ObservedFact(source=EvidenceSource.PROBE_TCP, summary="TCP connection succeeded"))
    if tls_ok:
        observed.append(ObservedFact(source=EvidenceSource.PROBE_TLS, summary="TLS handshake succeeded"))
    if http_status:
        observed.append(
            ObservedFact(
                source=EvidenceSource.PROBE_HTTP,
                summary=f"HTTP response: {http_status}",
            )
        )

    # -----------------------------------------------------------------
    # Rule evaluation
    # -----------------------------------------------------------------

    # Rule 1: Cloud deny
    if has_cloud_deny:
        return ClassificationResult(
            verdict=Verdict.DENIED,
            enforcement_plane=EnforcementPlane.STRATA_CLOUD,
            owner_team=OwnerTeam.SECOPS,
            result_confidence=0.9,
            evidence_completeness=completeness,
            summary="Cloud policy deny detected in Strata/Prisma evidence.",
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.SECOPS,
                reason="Cloud policy deny evidence found",
                next_steps=[
                    "Review the identified Prisma Access security rule",
                    "Open a SecOps ticket referencing the rule name and request ID",
                    "Download the evidence bundle and attach to the ticket",
                ],
            ),
        )

    # Rule 2: On-prem deny
    if has_onprem_deny:
        return ClassificationResult(
            verdict=Verdict.DENIED,
            enforcement_plane=EnforcementPlane.ONPREM_PALO,
            owner_team=OwnerTeam.SECOPS,
            result_confidence=0.85,
            evidence_completeness=completeness,
            summary="On-prem PAN-OS deny detected.",
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.SECOPS,
                reason="On-prem PAN deny evidence found",
                next_steps=[
                    "Review the identified PAN-OS security rule",
                    "Open a SecOps ticket with the firewall hostname and rule name",
                    "Download the evidence bundle and attach to the ticket",
                ],
            ),
        )

    # Rule 3: Decrypt failure (strong signal)
    if has_decrypt_failure:
        return ClassificationResult(
            verdict=Verdict.DENIED,
            enforcement_plane=enforcement_plane,
            owner_team=OwnerTeam.SECOPS,
            result_confidence=0.6,
            evidence_completeness=completeness,
            summary="Decrypt failure evidence found. Traffic may be blocked by decryption policy.",
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.SECOPS,
                reason="Decrypt failure strongly suggests policy deny",
                next_steps=[
                    "Review decryption policy rules for the destination",
                    "Check certificate trust store if decrypt bypass is expected",
                ],
            ),
        )

    # Rule 4: SD-WAN degradation without deny
    if has_sdwan_degradation and not has_any_deny:
        return ClassificationResult(
            verdict=Verdict.UNKNOWN,
            enforcement_plane=enforcement_plane,
            owner_team=OwnerTeam.NETOPS,
            result_confidence=0.5,
            evidence_completeness=completeness,
            summary=(
                "No policy deny found, but SD-WAN path degradation was observed. "
                "The issue may be network path quality rather than a security policy decision."
            ),
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.NETOPS,
                reason="SD-WAN path degradation without deny evidence",
                next_steps=[
                    "Check SD-WAN OpsCenter for site health and tunnel status",
                    "Escalate to NetOps for path investigation",
                ],
            ),
        )

    # Rule 5: TCP/TLS success + HTTP 5xx → AppOps / Vendor issue
    if (tcp_ok or tls_ok) and http_status and 500 <= http_status < 600:
        return ClassificationResult(
            verdict=Verdict.ALLOWED,
            enforcement_plane=enforcement_plane,
            owner_team=OwnerTeam.APPOPS,
            result_confidence=0.65,
            evidence_completeness=completeness,
            summary=(
                f"Network path appears open (TCP/TLS succeeded) but server returned HTTP {http_status}. "
                "This is likely an application-layer issue, not a network block."
            ),
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.APPOPS,
                reason="Network is open, application returning server error",
                next_steps=[
                    f"Investigate application server returning HTTP {http_status}",
                    "Escalate to AppOps or Vendor",
                ],
            ),
        )

    # Rule 6: TCP/TLS success + HTTP 2xx/3xx - allowed
    if (tcp_ok or tls_ok) and http_status and http_status < 400:
        return ClassificationResult(
            verdict=Verdict.ALLOWED,
            enforcement_plane=enforcement_plane,
            owner_team=OwnerTeam.APPOPS,
            result_confidence=0.8,
            evidence_completeness=completeness,
            summary="Network connectivity probes succeeded and server responded positively.",
            observed_facts=observed,
            routing_recommendation=RoutingRecommendation(
                owner_team=OwnerTeam.APPOPS,
                reason="All probes passed",
                next_steps=["Verify application-layer authentication if access is still denied"],
            ),
        )

    # Fallback: insufficient evidence
    return ClassificationResult(
        verdict=Verdict.UNKNOWN,
        enforcement_plane=enforcement_plane,
        owner_team=OwnerTeam.SECOPS,
        result_confidence=0.1,
        evidence_completeness=completeness,
        summary=(
            "Insufficient evidence to determine verdict. "
            "Source telemetry may be unavailable, stubbed, or the destination is not yet indexed."
        ),
        observed_facts=observed,
        routing_recommendation=RoutingRecommendation(
            owner_team=OwnerTeam.SECOPS,
            reason="Telemetry incomplete or sources not available",
            next_steps=[
                "Verify adapter credentials are configured",
                "Check source readiness in /readyz endpoint",
                "Review worker logs for adapter errors",
                "Expand the time window and resubmit",
            ],
        ),
    )
