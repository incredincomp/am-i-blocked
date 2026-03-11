"""CrowdStrike Falcon LogScale adapter - enrichment query layer."""

from __future__ import annotations

import time
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
        *,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._repo = (repo or "").strip()
        self._token = (token or "").strip()
        self._request_timeout_seconds = max(1.0, float(request_timeout_seconds))

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def check_readiness(self) -> dict[str, Any]:
        """Check LogScale API availability with one bounded repository probe."""
        if not self._base_url or not self._repo or not self._token:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "LogScale URL, repo, or token not configured",
                "latency_ms": None,
            }

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.get(
                    f"{self._base_url}/api/v1/repositories/{self._repo}",
                    headers=self._headers,
                )
        except httpx.TimeoutException:
            return {
                "available": False,
                "status": "timeout",
                "reason": "LogScale readiness probe timed out",
                "latency_ms": None,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status": "unreachable",
                "reason": "LogScale endpoint unreachable",
                "latency_ms": None,
            }
        except httpx.RequestError as exc:
            return {
                "available": False,
                "status": "unreachable",
                "reason": f"LogScale request failed: {exc}",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "status": "internal_error",
                "reason": f"LogScale readiness internal error: {exc}",
                "latency_ms": None,
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "auth_failed",
                "reason": "LogScale auth failed (401)",
                "latency_ms": latency_ms,
            }
        if response.status_code == 403:
            return {
                "available": False,
                "status": "unauthorized",
                "reason": "LogScale auth unauthorized (403)",
                "latency_ms": latency_ms,
            }
        if response.status_code < 200 or response.status_code >= 300:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": f"LogScale readiness probe returned HTTP {response.status_code}",
                "latency_ms": latency_ms,
            }

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if not isinstance(payload, dict):
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "LogScale readiness probe returned non-JSON object response",
                "latency_ms": latency_ms,
            }

        return {
            "available": True,
            "status": "ready",
            "reason": "LogScale readiness probe succeeded",
            "latency_ms": latency_ms,
        }

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
                    "classification_role": "enrichment_only_unverified",
                    "authoritative": False,
                    "message": "UNVERIFIED: LogScale adapter async query flow not yet implemented",
                    "repo": self._repo,
                    "destination": destination,
                    "port": port,
                    "time_window_start": time_window_start,
                    "time_window_end": time_window_end,
                },
                raw_ref=None,
                redacted={},
            )
        ]
