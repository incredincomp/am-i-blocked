"""Step 2: Check source readiness for all configured adapters."""

from __future__ import annotations

from typing import Any

from am_i_blocked_core.config import Settings
from am_i_blocked_core.logging_helpers import get_logger

logger = get_logger(__name__)


class ReadinessReport:
    def __init__(self) -> None:
        self.sources: dict[str, dict[str, Any]] = {}

    def record(self, source: str, result: dict[str, Any]) -> None:
        self.sources[source] = result
        logger.info("source readiness", source=source, **result)

    @property
    def any_available(self) -> bool:
        return any(v.get("available") for v in self.sources.values())

    @property
    def available_sources(self) -> list[str]:
        return [k for k, v in self.sources.items() if v.get("available")]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.sources)


async def run(settings: Settings) -> ReadinessReport:
    """Check availability of all configured adapter sources.

    Returns a ReadinessReport describing which sources are available.
    """
    report = ReadinessReport()

    # PAN-OS
    if settings.panos_fw_hosts and settings.panos_api_key:
        from am_i_blocked_adapters.panos import PANOSAdapter
        adapter = PANOSAdapter(
            fw_hosts=settings.panos_fw_hosts,
            api_key=settings.panos_api_key,
            verify_ssl=settings.panos_verify_ssl,
        )
        result = await adapter.check_readiness()
        report.record("panos", result)
    else:
        report.record("panos", {"available": False, "reason": "not configured", "latency_ms": None})

    # SCM
    from am_i_blocked_adapters.scm import SCMAdapter
    scm_adapter = SCMAdapter(
        client_id=settings.scm_client_id,
        client_secret=settings.scm_client_secret,
        tsg_id=settings.scm_tsg_id,
        auth_url=settings.scm_auth_url,
        api_base_url=settings.scm_api_base_url,
    )
    report.record("scm", await scm_adapter.check_readiness())

    # LogScale
    if settings.logscale_url and settings.logscale_token and settings.logscale_repo:
        from am_i_blocked_adapters.logscale import LogScaleAdapter
        adapter = LogScaleAdapter(
            base_url=settings.logscale_url,
            repo=settings.logscale_repo,
            token=settings.logscale_token,
        )
        result = await adapter.check_readiness()
        report.record("logscale", result)
    else:
        report.record("logscale", {"available": False, "reason": "not configured", "latency_ms": None})

    # SD-WAN
    from am_i_blocked_adapters.sdwan import SDWANAdapter
    sdwan_adapter = SDWANAdapter(
        api_url=settings.sdwan_api_url,
        api_key=settings.sdwan_api_key,
        verify_ssl=settings.sdwan_verify_ssl,
    )
    report.record("sdwan", await sdwan_adapter.check_readiness())

    # Torq
    from am_i_blocked_adapters.torq import TorqAdapter
    torq_adapter = TorqAdapter(
        client_id=settings.torq_client_id,
        client_secret=settings.torq_client_secret,
        api_base_url=settings.torq_api_base_url,
    )
    report.record("torq", await torq_adapter.check_readiness())

    return report
