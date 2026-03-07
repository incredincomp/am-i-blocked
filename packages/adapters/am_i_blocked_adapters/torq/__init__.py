"""Torq adapter - outbound trigger and execution polling only."""

from __future__ import annotations

from typing import Any

from am_i_blocked_core.models import EvidenceRecord

from ..base import BaseAdapter


class TorqAdapter(BaseAdapter):
    """Adapter for Torq automation platform.

    MVP scope: outbound trigger + polling only. No inbound webhooks.

    TODO: Implement OAuth2 client credentials token acquisition.
    TODO: Implement workflow trigger via POST.
    TODO: Implement execution status polling.
    TODO: Map execution output to EvidenceRecord if applicable.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        api_base_url: str = "https://api.torq.io",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_base_url = api_base_url.rstrip("/")
        self._access_token: str | None = None

    async def _get_token(self) -> str:
        """Obtain Torq OAuth2 access token.

        TODO: Implement token caching with expiry.
        """
        raise NotImplementedError("TODO: Implement Torq OAuth2 token acquisition")

    async def check_readiness(self) -> dict[str, Any]:
        """Check Torq API availability.

        TODO: Implement lightweight Torq health endpoint check.
        """
        if not self._client_id or not self._client_secret:
            return {"available": False, "reason": "Torq credentials not configured", "latency_ms": None}

        return {
            "available": False,
            "reason": "TODO: Torq readiness check not yet implemented",
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
        """Torq does not provide evidence queries in MVP scope.

        Returns an empty list - Torq is an outbound trigger, not a log source.
        """
        return []

    async def trigger_workflow(
        self,
        workflow_id: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Trigger a Torq workflow with the given parameters.

        TODO: POST to Torq API to trigger workflow.
        TODO: Return execution ID for polling.
        """
        return {
            "stub": True,
            "message": "TODO: implement Torq workflow trigger",
            "workflow_id": workflow_id,
        }

    async def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        """Poll Torq for execution status.

        TODO: GET Torq execution status endpoint.
        """
        return {
            "stub": True,
            "message": "TODO: implement Torq execution status polling",
            "execution_id": execution_id,
        }
