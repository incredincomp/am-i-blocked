"""Step 1: Validate and normalize the diagnostic request."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from am_i_blocked_core.enums import DestinationType
from am_i_blocked_core.logging_helpers import get_logger

logger = get_logger(__name__)

_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
)


class ValidationError(Exception):
    pass


def classify_destination(destination: str) -> tuple[DestinationType, str]:
    """Classify and normalize a destination string."""
    dest = destination.strip()
    if not dest:
        raise ValidationError("Destination must not be empty")

    if "/" in dest:
        parsed = urlparse(dest)
        if parsed.scheme not in ("http", "https"):
            raise ValidationError("CIDR ranges and IP subnets are not permitted")

    try:
        addr = ipaddress.ip_address(dest)
        if addr.is_loopback:
            raise ValidationError("Loopback addresses are not permitted")
        return DestinationType.IP, str(addr)
    except ValueError:
        pass

    if dest.startswith("http://") or dest.startswith("https://"):
        parsed = urlparse(dest)
        if not parsed.hostname:
            raise ValidationError(f"Could not parse hostname from URL: {dest!r}")
        return DestinationType.URL, dest

    if _HOSTNAME_RE.match(dest):
        return DestinationType.FQDN, dest.lower()

    raise ValidationError(f"Unrecognisable destination: {dest!r}")


def validate_port(port: int | None) -> int | None:
    if port is None:
        return None
    if not (1 <= port <= 65535):
        raise ValidationError(f"Port {port} is out of range")
    return port


def run(destination: str, port: int | None) -> tuple[DestinationType, str, int | None]:
    dest_type, normalized = classify_destination(destination)
    validated_port = validate_port(port)
    logger.debug("destination validated", dest_type=dest_type, normalized=normalized, port=validated_port)
    return dest_type, normalized, validated_port
