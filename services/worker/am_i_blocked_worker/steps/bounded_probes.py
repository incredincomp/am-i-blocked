"""Step 4: Bounded lightweight probes (DNS, TCP, TLS, HTTP)."""

from __future__ import annotations

import asyncio
import ssl
from typing import Any

from am_i_blocked_core.config import Settings
from am_i_blocked_core.logging_helpers import get_logger

logger = get_logger(__name__)


class ProbeResults:
    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}

    def record(self, probe: str, result: dict[str, Any]) -> None:
        self.results[probe] = result
        logger.info("probe result", probe=probe, **result)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.results)


async def _dns_probe(hostname: str, timeout: float) -> dict[str, Any]:
    try:
        loop = asyncio.get_event_loop()
        addrs = await asyncio.wait_for(
            loop.getaddrinfo(hostname, None),
            timeout=timeout,
        )
        resolved = list({addr[4][0] for addr in addrs})
        return {"success": True, "resolved_ips": resolved}
    except TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _tcp_probe(host: str, port: int, timeout: float) -> dict[str, Any]:
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return {"success": True, "connected": True}
    except TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _tls_probe(host: str, port: int, timeout: float) -> dict[str, Any]:
    try:
        ctx = ssl.create_default_context()
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx),
            timeout=timeout,
        )
        cert = writer.get_extra_info("ssl_object")
        subject = cert.getpeercert().get("subject", []) if cert else []
        writer.close()
        await writer.wait_closed()
        return {"success": True, "tls_subject": str(subject)}
    except TimeoutError:
        return {"success": False, "error": "timeout"}
    except ssl.SSLCertVerificationError as exc:
        return {"success": False, "error": f"cert_verification: {exc}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _http_probe(url: str, timeout: float) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.head(url)
            return {"success": True, "status_code": resp.status_code, "headers": dict(resp.headers)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def run(
    destination: str,
    port: int | None,
    dest_type: str,
    settings: Settings,
) -> ProbeResults:
    """Execute bounded probes as configured.

    All probes are individually timeout-bounded. Probes can be globally
    disabled via settings.enable_bounded_probes.
    """
    report = ProbeResults()

    if not settings.enable_bounded_probes:
        logger.info("bounded probes disabled by configuration")
        return report

    # Resolve the hostname to probe
    hostname = destination
    if dest_type == "url":
        from urllib.parse import urlparse
        parsed = urlparse(destination)
        hostname = parsed.hostname or destination
        if port is None:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # DNS probe
    result = await _dns_probe(hostname, settings.probe_dns_timeout_s)
    report.record("dns", result)

    # TCP probe (only if port is known)
    if port:
        result = await _tcp_probe(hostname, port, settings.probe_tcp_timeout_s)
        report.record("tcp", result)

        # TLS probe only on common TLS ports
        if port in (443, 8443, 465, 993, 995):
            result = await _tls_probe(hostname, port, settings.probe_tls_timeout_s)
            report.record("tls", result)

    # HTTP probe (only for URL destinations)
    if dest_type == "url":
        result = await _http_probe(destination, settings.probe_http_timeout_s)
        report.record("http", result)

    return report
