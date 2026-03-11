"""Torq adapter - outbound trigger and execution polling only."""

from __future__ import annotations

import time
from typing import Any

import httpx
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
        client_id: str | None,
        client_secret: str | None,
        *,
        api_base_url: str = "https://api.torq.io",
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self._client_id = (client_id or "").strip()
        self._client_secret = (client_secret or "").strip()
        self._api_base_url = api_base_url.rstrip("/")
        self._request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self._access_token: str | None = None

    async def _get_token(self) -> str:
        """Obtain Torq OAuth2 access token.

        TODO: Implement token caching with expiry.
        """
        raise NotImplementedError("TODO: Implement Torq OAuth2 token acquisition")

    async def check_readiness(self) -> dict[str, Any]:
        """Check Torq API availability with one bounded request."""
        if not self._client_id or not self._client_secret:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "Torq credentials not configured",
                "latency_ms": None,
            }
        if not self._api_base_url:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "Torq API base URL not configured",
                "latency_ms": None,
            }

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.get(
                    self._api_base_url,
                    headers={
                        "X-Client-Id": self._client_id,
                        "X-Client-Secret": self._client_secret,
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException:
            return {
                "available": False,
                "status": "timeout",
                "reason": "Torq readiness probe timed out",
                "latency_ms": None,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status": "unreachable",
                "reason": "Torq endpoint unreachable",
                "latency_ms": None,
            }
        except httpx.RequestError as exc:
            return {
                "available": False,
                "status": "unreachable",
                "reason": f"Torq request failed: {exc}",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "status": "internal_error",
                "reason": f"Torq readiness internal error: {exc}",
                "latency_ms": None,
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "auth_failed",
                "reason": "Torq auth failed (401)",
                "latency_ms": latency_ms,
            }
        if response.status_code == 403:
            return {
                "available": False,
                "status": "unauthorized",
                "reason": "Torq auth unauthorized (403)",
                "latency_ms": latency_ms,
            }
        if response.status_code < 200 or response.status_code >= 300:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": f"Torq readiness probe returned HTTP {response.status_code}",
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
                "reason": "Torq readiness probe returned non-JSON response",
                "latency_ms": latency_ms,
            }

        return {
            "available": True,
            "status": "ready",
            "reason": "Torq readiness probe succeeded",
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
