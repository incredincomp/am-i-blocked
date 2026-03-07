"""SD-WAN adapter - path, site, and health signal queries."""

from __future__ import annotations

import uuid
from typing import Any

from am_i_blocked_core.enums import EvidenceKind, EvidenceSource
from am_i_blocked_core.models import EvidenceRecord

from ..base import BaseAdapter


class SDWANAdapter(BaseAdapter):
    """Adapter for Palo Alto SD-WAN OpsCenter.

    SD-WAN is used initially as a path/site/health signal source.
    Payloads are kept generic and extensible - do not hardcode detailed
    payload assumptions in early versions.

    TODO: Implement OpsCenter API authentication.
    TODO: Implement site/path health query.
    TODO: Implement tunnel status query.
    TODO: Map OpsCenter response fields to normalized evidence.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        verify_ssl: bool = True,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._verify_ssl = verify_ssl

    async def check_readiness(self) -> dict[str, Any]:
        """Check SD-WAN OpsCenter API availability.

        TODO: Implement actual health endpoint probe.
        """
        if not self._api_url:
            return {"available": False, "reason": "SD-WAN API URL not configured", "latency_ms": None}

        return {
            "available": False,
            "reason": "TODO: SD-WAN readiness check not yet implemented",
            "latency_ms": None,
        }

    async def query_evidence(
        self,
        destination: str,
        port: int | None,
        time_window_start: str,
        time_window_end: str,
        request_id: str,
    ) -> list[EvidenceRecord]:
        """Query SD-WAN for path and health signals relevant to the destination.

        TODO: Query OpsCenter for site-level path status.
        TODO: Query for SD-WAN application path health.
        TODO: Normalize response into path signal evidence.
        """
        return [
            EvidenceRecord(
                evidence_id=uuid.uuid4(),
                request_id=uuid.UUID(request_id),
                source=EvidenceSource.SDWAN,
                kind=EvidenceKind.PATH_SIGNAL,
                normalized={
                    "stub": True,
                    "message": "SD-WAN adapter not yet wired - TODO: implement OpsCenter queries",
                    "destination": destination,
                },
                raw_ref=None,
                redacted={},
            )
        ]

    async def get_site_health(self, site_id: str) -> dict[str, Any]:
        """Get health signals for a specific SD-WAN site.

        TODO: Implement OpsCenter site health API call.
        """
        return {
            "stub": True,
            "message": "TODO: implement SD-WAN site health lookup",
            "site_id": site_id,
        }
