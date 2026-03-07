"""PAN-OS adapter - traffic log and rule metadata queries."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from am_i_blocked_core.enums import EvidenceKind, EvidenceSource
from am_i_blocked_core.models import EvidenceRecord

from ..base import BaseAdapter


class PANOSAdapter(BaseAdapter):
    """Adapter for PAN-OS on-prem firewall management planes.

    Uses a hybrid strategy:
    - XML API for log retrieval (job-based async polling)
    - REST API for some metadata / config retrieval

    Concurrency against the management plane is intentionally conservative.

    TODO: Implement actual XML API job submission and polling.
    TODO: Implement REST API token refresh.
    TODO: Handle multi-vsys environments.
    """

    def __init__(
        self,
        fw_hosts: list[str],
        api_key: str,
        *,
        verify_ssl: bool = True,
        max_concurrent: int = 2,
    ) -> None:
        self._fw_hosts = fw_hosts
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._max_concurrent = max_concurrent

    async def check_readiness(self) -> dict[str, Any]:
        """Ping each firewall's XML API and return aggregate readiness."""
        if not self._fw_hosts:
            return {"available": False, "reason": "No PAN-OS hosts configured", "latency_ms": None}

        reachable: list[str] = []
        for host in self._fw_hosts:
            try:
                async with httpx.AsyncClient(verify=self._verify_ssl, timeout=5.0) as client:
                    # Lightweight version check via XML API
                    resp = await client.get(
                        f"https://{host}/api/?type=version&key={self._api_key}"
                    )
                    if resp.status_code == 200:
                        reachable.append(host)
            except Exception:
                pass

        available = len(reachable) > 0
        return {
            "available": available,
            "reason": f"{len(reachable)}/{len(self._fw_hosts)} firewalls reachable",
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
        """Query traffic logs on PAN-OS for the given destination.

        TODO: Build XPath query and submit async log retrieval job via XML API.
        TODO: Poll job status until complete or timeout.
        TODO: Parse log entries and map to EvidenceRecord.
        TODO: Query security rule metadata via REST API to enrich evidence.
        """
        # Stub: return empty evidence with a clear marker
        return [
            EvidenceRecord(
                evidence_id=uuid.uuid4(),
                request_id=uuid.UUID(request_id),
                source=EvidenceSource.PANOS,
                kind=EvidenceKind.TRAFFIC_LOG,
                normalized={
                    "stub": True,
                    "message": "PAN-OS adapter not yet wired - TODO: implement XML API job polling",
                    "fw_hosts": self._fw_hosts,
                    "destination": destination,
                    "port": port,
                },
                raw_ref=None,
                redacted={},
            )
        ]

    async def lookup_rule_metadata(self, rule_name: str, vsys: str = "vsys1") -> dict[str, Any]:
        """Retrieve rule metadata from the firewall REST API.

        TODO: Implement REST API call to retrieve security rule details.
        """
        return {
            "stub": True,
            "message": "TODO: implement PAN-OS REST API rule metadata lookup",
            "rule_name": rule_name,
            "vsys": vsys,
        }
