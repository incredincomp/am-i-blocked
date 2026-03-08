"""PAN-OS adapter - traffic log and rule metadata queries."""

from __future__ import annotations

import asyncio
import uuid
import xml.etree.ElementTree as ET
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
        poll_max_attempts: int = 5,
        poll_interval_seconds: float = 0.2,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        self._fw_hosts = fw_hosts
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._max_concurrent = max_concurrent
        self._poll_max_attempts = max(1, poll_max_attempts)
        self._poll_interval_seconds = max(0.0, poll_interval_seconds)
        self._request_timeout_seconds = max(1.0, request_timeout_seconds)

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
        """Query traffic logs on PAN-OS for deny/reset actions via XML job polling."""
        request_uuid = uuid.UUID(request_id)
        if not self._fw_hosts:
            return []

        query = self._build_traffic_query(destination=destination, port=port)
        evidence: list[EvidenceRecord] = []
        for host in self._fw_hosts:
            job_id = await self._submit_traffic_log_job(host=host, query=query)
            if job_id is None:
                continue
            entries = await self._poll_log_job(host=host, job_id=job_id)
            for entry in entries:
                record = self._normalize_entry(entry=entry, request_id=request_uuid, host=host)
                if record is not None:
                    evidence.append(record)
        return evidence

    def _build_traffic_query(self, destination: str, port: int | None) -> str:
        """Build a conservative PAN-OS XML traffic-log query string.

        Query field semantics can vary by environment/version; this query shape is
        intentionally narrow and should be treated as UNVERIFIED until validated
        against target firewalls.
        """
        destination_clean = destination.replace("'", "")
        clauses = [f"(addr.dst eq '{destination_clean}')"]
        if port is not None:
            clauses.append(f"(port.dst eq {port})")
        return " and ".join(clauses)

    async def _submit_traffic_log_job(self, host: str, query: str) -> str | None:
        """Submit a PAN-OS XML traffic-log job and return the job id."""
        root = await self._call_xml_api(
            host=host,
            params={
                "type": "log",
                "log-type": "traffic",
                "query": query,
            },
        )
        if root is None:
            return None
        job_id = root.findtext(".//job")
        if job_id is None:
            return None
        return job_id.strip() or None

    async def _poll_log_job(self, host: str, job_id: str) -> list[dict[str, str]]:
        """Poll PAN-OS XML log job until completion or timeout."""
        for attempt in range(self._poll_max_attempts):
            root = await self._call_xml_api(
                host=host,
                params={
                    "type": "log",
                    "action": "get",
                    "job-id": job_id,
                },
            )
            if root is None:
                return []

            status = (root.findtext(".//status") or "").strip().upper()
            if status == "FIN":
                return self._extract_log_entries(root)

            if attempt < self._poll_max_attempts - 1 and self._poll_interval_seconds > 0:
                await asyncio.sleep(self._poll_interval_seconds)

        return []

    async def _call_xml_api(self, host: str, params: dict[str, Any]) -> ET.Element | None:
        """Call PAN-OS XML API and parse response root safely."""
        call_params = dict(params)
        call_params["key"] = self._api_key
        try:
            async with httpx.AsyncClient(
                verify=self._verify_ssl,
                timeout=self._request_timeout_seconds,
            ) as client:
                response = await client.get(f"https://{host}/api/", params=call_params)
                response.raise_for_status()
        except Exception:
            return None

        try:
            return ET.fromstring(response.text)
        except ET.ParseError:
            return None

    def _extract_log_entries(self, root: ET.Element) -> list[dict[str, str]]:
        """Extract raw log entries from PAN-OS XML polling response."""
        entries: list[dict[str, str]] = []
        for entry_node in root.findall(".//logs/entry"):
            entry: dict[str, str] = {}
            for child in entry_node:
                if child.tag and child.text is not None:
                    entry[child.tag] = child.text.strip()
            entries.append(entry)
        return entries

    def _normalize_entry(
        self,
        entry: dict[str, str],
        request_id: uuid.UUID,
        host: str,
    ) -> EvidenceRecord | None:
        """Normalize only deny/reset-like entries into authoritative evidence."""
        action_raw = (entry.get("action") or "").strip().lower()
        if not action_raw:
            return None
        if action_raw not in {"deny", "reset-both", "reset-client", "reset-server"}:
            return None

        normalized: dict[str, Any] = {
            "action": "deny",
            "action_raw": action_raw,
            "authoritative": True,
            "device_host": host,
        }

        if rule_name := entry.get("rule"):
            normalized["rule_name"] = rule_name
        if event_ts := entry.get("time_generated") or entry.get("receive_time"):
            normalized["event_ts"] = event_ts
        if dst_ip := entry.get("dst"):
            normalized["dst"] = dst_ip
        if dst_port := entry.get("dport"):
            normalized["dport"] = dst_port

        return EvidenceRecord(
            evidence_id=uuid.uuid4(),
            request_id=request_id,
            source=EvidenceSource.PANOS,
            kind=EvidenceKind.TRAFFIC_LOG,
            normalized=normalized,
            raw_ref=None,
            redacted={},
        )

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
