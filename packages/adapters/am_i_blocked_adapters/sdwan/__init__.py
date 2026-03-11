"""SD-WAN adapter - path, site, and health signal queries."""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
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
        api_url: str | None,
        api_key: str | None,
        *,
        verify_ssl: bool = True,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self._api_url = (api_url or "").strip().rstrip("/")
        self._api_key = (api_key or "").strip()
        self._verify_ssl = verify_ssl
        self._request_timeout_seconds = max(1.0, float(request_timeout_seconds))

    async def check_readiness(self) -> dict[str, Any]:
        """Check SD-WAN API availability via one bounded auth probe."""
        if not self._api_url or not self._api_key:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "SD-WAN API URL or API key not configured",
                "latency_ms": None,
            }

        started = time.monotonic()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                verify=self._verify_ssl,
                timeout=self._request_timeout_seconds,
            ) as client:
                response = await client.get(self._api_url, headers=headers)
        except httpx.TimeoutException:
            return {
                "available": False,
                "status": "timeout",
                "reason": "SD-WAN readiness probe timed out",
                "latency_ms": None,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status": "unreachable",
                "reason": "SD-WAN endpoint unreachable",
                "latency_ms": None,
            }
        except httpx.RequestError as exc:
            return {
                "available": False,
                "status": "unreachable",
                "reason": f"SD-WAN request failed: {exc}",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "status": "internal_error",
                "reason": f"SD-WAN readiness internal error: {exc}",
                "latency_ms": None,
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "auth_failed",
                "reason": "SD-WAN auth failed (401)",
                "latency_ms": latency_ms,
            }
        if response.status_code == 403:
            return {
                "available": False,
                "status": "unauthorized",
                "reason": "SD-WAN auth unauthorized (403)",
                "latency_ms": latency_ms,
            }
        if response.status_code < 200 or response.status_code >= 300:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": f"SD-WAN readiness probe returned HTTP {response.status_code}",
                "latency_ms": latency_ms,
            }

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, (dict, list)):
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "SD-WAN readiness probe returned non-JSON response",
                "latency_ms": latency_ms,
            }

        return {
            "available": True,
            "status": "ready",
            "reason": "SD-WAN readiness probe succeeded",
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
