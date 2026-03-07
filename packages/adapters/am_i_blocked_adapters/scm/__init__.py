"""Strata Cloud Manager (SCM) / Prisma Access adapter."""

from __future__ import annotations

import uuid
from typing import Any

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
        client_id: str,
        client_secret: str,
        tsg_id: str,
        *,
        auth_url: str = "https://auth.apps.paloaltonetworks.com/oauth2/access_token",
        api_base_url: str = "https://api.sase.paloaltonetworks.com",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._tsg_id = tsg_id
        self._auth_url = auth_url
        self._api_base_url = api_base_url
        self._access_token: str | None = None

    async def _get_token(self) -> str:
        """Obtain an OAuth2 access token.

        TODO: Implement token refresh and caching with expiry.
        """
        raise NotImplementedError(
            "TODO: Implement SCM OAuth2 client credentials token acquisition"
        )

    async def check_readiness(self) -> dict[str, Any]:
        """Check SCM API availability.

        TODO: Replace stub with a lightweight ping to the SCM health endpoint.
        """
        if not self._client_id or not self._client_secret or not self._tsg_id:
            return {"available": False, "reason": "SCM credentials not configured", "latency_ms": None}

        return {
            "available": False,
            "reason": "TODO: SCM readiness check not yet implemented",
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
