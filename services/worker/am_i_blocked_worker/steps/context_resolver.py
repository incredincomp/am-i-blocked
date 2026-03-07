"""Step 3: Infer path context from available signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from am_i_blocked_core.enums import EnforcementPlane, PathContext
from am_i_blocked_core.logging_helpers import get_logger

logger = get_logger(__name__)


@dataclass
class ContextResult:
    path_context: PathContext
    enforcement_plane: EnforcementPlane
    path_confidence: float  # 0.0 - 1.0
    site: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)


def run(
    readiness_sources: dict[str, dict[str, Any]],
    requester_hints: dict[str, Any] | None = None,
) -> ContextResult:
    """Infer path context from readiness signals and optional client hints.

    Decision logic (deterministic, no ML):
    1. If SCM available → likely Prisma Access path
    2. If PAN-OS available + SD-WAN available → SD-WAN path
    3. If PAN-OS available + no SD-WAN → on-prem GlobalProtect
    4. If nothing is available → unknown

    Caller may pass requester_hints with keys such as:
    - "sdwan_site": str — explicit site ID
    - "client_type": "vpn" | "sdwan" | "campus"
    - "tunnel_type": "prisma" | "gp"
    """
    hints = requester_hints or {}
    signals: dict[str, Any] = {}

    panos_ok = readiness_sources.get("panos", {}).get("available", False)
    scm_ok = readiness_sources.get("scm", {}).get("available", False)
    sdwan_ok = readiness_sources.get("sdwan", {}).get("available", False)

    signals["panos_available"] = panos_ok
    signals["scm_available"] = scm_ok
    signals["sdwan_available"] = sdwan_ok
    signals["hints"] = hints

    # Explicit client-side hint takes highest precedence
    client_type = hints.get("client_type")
    tunnel_type = hints.get("tunnel_type")

    if tunnel_type == "prisma" or (scm_ok and client_type in (None, "vpn")):
        return ContextResult(
            path_context=PathContext.VPN_PRISMA_ACCESS,
            enforcement_plane=EnforcementPlane.STRATA_CLOUD,
            path_confidence=0.7 if scm_ok else 0.4,
            site=hints.get("sdwan_site"),
            signals=signals,
        )

    if client_type == "sdwan" or sdwan_ok:
        return ContextResult(
            path_context=PathContext.SDWAN_OPSCENTER,
            enforcement_plane=EnforcementPlane.ONPREM_PALO,
            path_confidence=0.6 if sdwan_ok else 0.3,
            site=hints.get("sdwan_site"),
            signals=signals,
        )

    if panos_ok:
        return ContextResult(
            path_context=PathContext.VPN_GP_ONPREM_STATIC,
            enforcement_plane=EnforcementPlane.ONPREM_PALO,
            path_confidence=0.5,
            site=hints.get("sdwan_site"),
            signals=signals,
        )

    return ContextResult(
        path_context=PathContext.UNKNOWN,
        enforcement_plane=EnforcementPlane.UNKNOWN,
        path_confidence=0.0,
        site=None,
        signals=signals,
    )
