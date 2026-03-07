"""CrowdStrike Falcon LogScale adapter - enrichment query layer."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from am_i_blocked_core.enums import EvidenceKind, EvidenceSource
from am_i_blocked_core.models import EvidenceRecord

from ..base import BaseAdapter


class LogScaleAdapter(BaseAdapter):
    """Adapter for CrowdStrike Falcon LogScale (NG SIEM).

    LogScale is treated as an enrichment and secondary correlation layer.
    It is NOT the source-of-truth for policy decisions.

    Query model:
    - Submit an async query job
    - Poll for completion
    - Normalize results into EvidenceRecord entries

    TODO: Implement async query job submission.
    TODO: Implement job status polling with exponential backoff.
    TODO: Implement result pagination.
    TODO: Implement query result normalization.
    """

    def __init__(
        self,
        base_url: str,
        repo: str,
        token: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._repo = repo
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def check_readiness(self) -> dict[str, Any]:
        """Check LogScale API availability.

        TODO: Use /api/v1/status or repository endpoint for a lightweight ping.
        """
        if not self._base_url or not self._token:
            return {"available": False, "reason": "LogScale credentials not configured", "latency_ms": None}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/repositories/{self._repo}",
                    headers=self._headers,
                )
                available = resp.status_code in (200, 403)  # 403 = auth issue but reachable
                return {
                    "available": available,
                    "reason": f"HTTP {resp.status_code}",
                    "latency_ms": None,
                }
        except Exception as exc:
            return {"available": False, "reason": str(exc), "latency_ms": None}

    async def query_evidence(
        self,
        destination: str,
        port: int | None,
        time_window_start: str,
        time_window_end: str,
        request_id: str,
    ) -> list[EvidenceRecord]:
        """Submit an async LogScale query and return normalized evidence.

        TODO: Build LogScale query string scoped to destination and time window.
        TODO: POST to /api/v1/repositories/{repo}/queryjobs to create async job.
        TODO: Poll GET /api/v1/repositories/{repo}/queryjobs/{id} until done.
        TODO: Normalize matched events to EvidenceRecord entries.
        """
        return [
            EvidenceRecord(
                evidence_id=uuid.uuid4(),
                request_id=uuid.UUID(request_id),
                source=EvidenceSource.LOGSCALE,
                kind=EvidenceKind.TRAFFIC_LOG,
                normalized={
                    "stub": True,
                    "message": "LogScale adapter not yet wired - TODO: implement async query job",
                    "repo": self._repo,
                    "destination": destination,
                    "port": port,
                },
                raw_ref=None,
                redacted={},
            )
        ]
