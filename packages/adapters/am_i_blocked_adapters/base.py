"""Abstract base class for all vendor adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from am_i_blocked_core.models import EvidenceRecord


class AdapterError(Exception):
    """Raised when an adapter encounters an unrecoverable error."""


class AdapterUnavailableError(AdapterError):
    """Raised when the upstream system fails readiness checks."""


class BaseAdapter(ABC):
    """Every vendor adapter must implement this interface."""

    @abstractmethod
    async def check_readiness(self) -> dict[str, Any]:
        """Return a dict describing readiness status.

        Returns:
            {"available": bool, "reason": str, "latency_ms": float | None}
        """

    @abstractmethod
    async def query_evidence(
        self,
        destination: str,
        port: int | None,
        time_window_start: str,
        time_window_end: str,
        request_id: str,
    ) -> list[EvidenceRecord]:
        """Query the upstream system and return normalized evidence records."""
