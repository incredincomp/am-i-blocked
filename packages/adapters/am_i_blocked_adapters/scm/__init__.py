"""Strata Cloud Manager (SCM) / Prisma Access adapter."""

from __future__ import annotations

import time
import urllib.parse
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

    TODO: Implement security policy rule lookup.
    TODO: Implement decryption rule lookup.
    TODO: Broader SCM query orchestration/pagination remains out of scope.
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

    async def _probe_access_token(self) -> dict[str, Any]:
        """Obtain an OAuth2 access token via one bounded request."""
        if not self._client_id or not self._client_secret or not self._tsg_id:
            return {
                "available": False,
                "status": "not_configured",
                "reason": "SCM credentials not configured",
                "latency_ms": None,
                "access_token": None,
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
                "access_token": None,
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status": "unreachable",
                "reason": "SCM auth endpoint unreachable",
                "latency_ms": None,
                "access_token": None,
            }
        except httpx.RequestError as exc:
            return {
                "available": False,
                "status": "unreachable",
                "reason": f"SCM auth request failed: {exc}",
                "latency_ms": None,
                "access_token": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "status": "internal_error",
                "reason": f"SCM readiness internal error: {exc}",
                "latency_ms": None,
                "access_token": None,
            }

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code == 401:
            return {
                "available": False,
                "status": "auth_failed",
                "reason": "SCM auth failed (401)",
                "latency_ms": latency_ms,
                "access_token": None,
            }
        if response.status_code == 403:
            return {
                "available": False,
                "status": "unauthorized",
                "reason": "SCM auth unauthorized (403)",
                "latency_ms": latency_ms,
                "access_token": None,
            }
        if response.status_code < 200 or response.status_code >= 300:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": f"SCM auth probe returned HTTP {response.status_code}",
                "latency_ms": latency_ms,
                "access_token": None,
            }

        try:
            payload = response.json()
        except ValueError:
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "SCM auth probe returned non-JSON response",
                "latency_ms": latency_ms,
                "access_token": None,
            }

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token.strip():
            return {
                "available": False,
                "status": "unexpected_response",
                "reason": "SCM auth probe response missing access token",
                "latency_ms": latency_ms,
                "access_token": None,
            }

        self._access_token = access_token.strip()
        return {
            "available": True,
            "status": "ready",
            "reason": "SCM auth probe succeeded",
            "latency_ms": latency_ms,
            "access_token": self._access_token,
        }

    async def check_readiness(self) -> dict[str, Any]:
        """Check SCM API availability via a bounded token probe."""
        result = await self._probe_access_token()
        return {
            "available": bool(result.get("available")),
            "status": result.get("status", "internal_error"),
            "reason": result.get("reason", "SCM auth probe failed"),
            "latency_ms": result.get("latency_ms"),
        }

    @staticmethod
    def _extract_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        for key in ("records", "items", "data", "results", "logs"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("records")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        return []

    @staticmethod
    def _first_string(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _first_int(record: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = record.get(key)
            try:
                return int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _canonical_destination(value: str) -> str:
        stripped = value.strip().lower()
        parsed = urllib.parse.urlparse(stripped)
        if parsed.scheme and parsed.netloc:
            return parsed.netloc.lower()
        return stripped

    @classmethod
    def _normalize_action(cls, record: dict[str, Any]) -> str | None:
        decision = cls._first_string(record, ("decision", "action", "disposition", "outcome"))
        if decision is None:
            return None
        lowered = decision.lower()
        if lowered in {"deny", "blocked", "block", "policy_deny"}:
            return "deny"
        if lowered in {"decrypt_deny", "decrypt-deny", "decryption_deny", "decrypt_blocked"}:
            return "decrypt_deny"
        return None

    @classmethod
    def _normalize_record(
        cls,
        record: dict[str, Any],
        *,
        request_uuid: uuid.UUID,
        destination: str,
        port: int | None,
    ) -> EvidenceRecord | None:
        source_system = cls._first_string(
            record,
            ("source_system", "system_of_record", "source", "source_type"),
        )
        if source_system is None:
            return None
        source_lower = source_system.lower()
        if not any(token in source_lower for token in ("scm", "strata", "prisma")):
            return None

        if record.get("authoritative") is not True:
            return None

        action = cls._normalize_action(record)
        if action is None:
            return None

        record_destination = cls._first_string(
            record,
            ("destination", "destination_value", "dst", "host", "fqdn", "url"),
        )
        if record_destination is None:
            return None
        if cls._canonical_destination(record_destination) != cls._canonical_destination(destination):
            return None

        if port is not None:
            record_port = cls._first_int(record, ("port", "dport", "destination_port"))
            if record_port != port:
                return None

        event_ts = cls._first_string(record, ("timestamp", "event_ts", "time", "generated_at"))
        if event_ts is None:
            return None

        reason = cls._first_string(record, ("reason", "policy_reason", "message", "description"))
        decision = cls._first_string(record, ("decision", "action", "disposition", "outcome"))
        rule_name = cls._first_string(record, ("rule_name", "policy_name", "rule"))
        rule_id = cls._first_string(record, ("rule_id", "policy_id"))
        event_id = cls._first_string(record, ("id", "event_id", "log_id"))
        kind = EvidenceKind.DECRYPT_LOG if action == "decrypt_deny" else EvidenceKind.TRAFFIC_LOG

        normalized: dict[str, Any] = {
            "authoritative": True,
            "action": action,
            "decision": decision or action,
            "source_system": source_system,
            "event_ts": event_ts,
            "destination": destination,
        }
        if action == "decrypt_deny":
            normalized["decrypt_error"] = reason or "decrypt_deny"
        if reason:
            normalized["reason"] = reason
        if rule_name:
            normalized["rule_name"] = rule_name
        if rule_id:
            normalized["rule_id"] = rule_id
        if port is not None:
            normalized["port"] = port
        if event_id:
            normalized["event_id"] = event_id

        return EvidenceRecord(
            evidence_id=uuid.uuid4(),
            request_id=request_uuid,
            source=EvidenceSource.SCM,
            kind=kind,
            normalized=normalized,
            raw_ref=None,
            redacted={"event_id": event_id} if event_id else {},
        )

    async def query_evidence(
        self,
        destination: str,
        port: int | None,
        time_window_start: str,
        time_window_end: str,
        request_id: str,
    ) -> list[EvidenceRecord]:
        """Perform one bounded SCM evidence retrieval and normalize authoritative records.

        This method intentionally fail-closes:
        malformed/ambiguous/non-authoritative records are dropped.
        """
        token_probe = await self._probe_access_token()
        access_token = token_probe.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return []

        request_uuid = uuid.UUID(request_id)
        request_body: dict[str, Any] = {
            "destination": destination,
            "time_window_start": time_window_start,
            "time_window_end": time_window_end,
            "limit": 25,
        }
        if port is not None:
            request_body["port"] = port

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if self._tsg_id:
            headers["X-PAN-TSG-ID"] = self._tsg_id

        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.post(self._api_base_url, json=request_body, headers=headers)
        except (httpx.RequestError, httpx.TimeoutException):
            return []
        except Exception:
            return []

        if response.status_code in (401, 403):
            return []
        if response.status_code < 200 or response.status_code >= 300:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []

        records = self._extract_records(payload)
        normalized_records: list[EvidenceRecord] = []
        for record in records:
            normalized = self._normalize_record(
                record,
                request_uuid=request_uuid,
                destination=destination,
                port=port,
            )
            if normalized is not None:
                normalized_records.append(normalized)
        return normalized_records

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
