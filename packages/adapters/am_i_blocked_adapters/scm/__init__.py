"""Strata Cloud Manager (SCM) / Prisma Access adapter."""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from am_i_blocked_core.enums import EvidenceKind, EvidenceSource
from am_i_blocked_core.models import EvidenceRecord

from ..base import BaseAdapter


class SCMAdapter(BaseAdapter):
    """Adapter for Strata Cloud Manager / Prisma Access.

    NOTE: Cloud logs may be available via SCM APIs or via forwarded logs in
    LogScale. Treat source availability as part of readiness checks.

    TODO: Implement OAuth2 client credentials flow.
    TODO: Implement security policy rule lookup.
    TODO: Implement decryption rule lookup.
    TODO: Handle paginated log query responses.
    """

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        tsg_id: str | None,
        *,
        auth_url: str = "https://auth.apps.paloaltonetworks.com/oauth2/access_token",
        api_base_url: str = "https://api.sase.paloaltonetworks.com",
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        self._tsg_id = (tsg_id or "").strip()
        self._auth_url = auth_url
        self._api_base_url = api_base_url
        self._request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self._access_token: str | None = None

    async def _get_token(self) -> str:
        """Obtain an OAuth2 access token.

        TODO: Implement token refresh and caching with expiry.
        """
        raise NotImplementedError(
            "TODO: Implement SCM OAuth2 client credentials token acquisition"
        )

    async def check_readiness(self) -> dict[str, Any]:
        """Check SCM API availability via a bounded token probe."""
        if not self._client_id or not self._client_secret or not self._tsg_id:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "SCM credentials not configured",
                "latency_ms": None,
            }

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.post(
                    self._auth_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.TimeoutException:
            return {
                "available": False,
                "status": "timeout",
                "reason": "SCM auth probe timed out",
                "latency_ms": None,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status": "unreachable",
                "reason": "SCM auth endpoint unreachable",
                "latency_ms": None,
            }
        except httpx.RequestError as exc:
            return {
                "available": False,
                "status": "unreachable",
                "reason": f"SCM auth request failed: {exc}",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "status": "internal_error",
                "reason": f"SCM readiness internal error: {exc}",
                "latency_ms": None,
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "auth_failed",
                "reason": "SCM auth failed (401)",
                "latency_ms": latency_ms,
            }
        if response.status_code == 403:
            return {
                "available": False,
                "status": "unauthorized",
                "reason": "SCM auth unauthorized (403)",
                "latency_ms": latency_ms,
            }
        if response.status_code < 200 or response.status_code >= 300:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": f"SCM auth probe returned HTTP {response.status_code}",
                "latency_ms": latency_ms,
            }

        try:
            payload = response.json()
        except ValueError:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "SCM auth probe returned non-JSON response",
                "latency_ms": latency_ms,
            }

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token.strip():
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "SCM auth probe response missing access token",
                "latency_ms": latency_ms,
            }

        self._access_token = access_token.strip()
        return {
            "available": True,
            "status": "ready",
            "reason": "SCM auth probe succeeded",
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
        """Query Prisma/SCM for traffic and security policy evidence.

        TODO: Submit log query to SCM query API.
        TODO: Poll for results.
        TODO: Normalize log entries to EvidenceRecord.
        """
        return [
            EvidenceRecord(
                evidence_id=uuid.uuid4(),
                request_id=uuid.UUID(request_id),
                source=EvidenceSource.SCM,
                kind=EvidenceKind.TRAFFIC_LOG,
                normalized={
                    "stub": True,
                    "message": "SCM adapter not yet wired - TODO: implement SCM API queries",
                    "destination": destination,
                    "port": port,
                },
                raw_ref=None,
                redacted={},
            )
        ]

    async def lookup_security_rule(self, rule_name: str, folder: str) -> dict[str, Any]:
        """Retrieve security rule metadata from SCM.

        TODO: Implement SCM REST API security policy rule GET.
        """
        return {
            "stub": True,
            "message": "TODO: implement SCM security rule metadata lookup",
            "rule_name": rule_name,
            "folder": folder,
        }

    async def lookup_decryption_rule(self, rule_name: str, folder: str) -> dict[str, Any]:
        """Retrieve decryption rule metadata from SCM.

        TODO: Implement SCM REST API decryption policy rule GET.
        Note: Decryption evidence may be incomplete depending on logging settings.
        """
        return {
            "stub": True,
            "message": "TODO: implement SCM decryption rule metadata lookup",
            "rule_name": rule_name,
            "folder": folder,
        }
