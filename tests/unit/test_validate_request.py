"""Unit tests for request validation."""

from __future__ import annotations

import pytest
from am_i_blocked_core.enums import DestinationType
from am_i_blocked_worker.steps.validate_request import (
    ValidationError,
    classify_destination,
    run,
    validate_port,
)


class TestClassifyDestination:
    def test_ip_address(self):
        dt, normalized = classify_destination("10.20.30.40")
        assert dt == DestinationType.IP
        assert normalized == "10.20.30.40"

    def test_ipv6(self):
        dt, _normalized = classify_destination("2001:db8::1")
        assert dt == DestinationType.IP

    def test_fqdn(self):
        dt, normalized = classify_destination("api.example.com")
        assert dt == DestinationType.FQDN
        assert normalized == "api.example.com"

    def test_url_https(self):
        dt, normalized = classify_destination("https://api.example.com/path")
        assert dt == DestinationType.URL
        assert normalized == "https://api.example.com/path"

    def test_url_http(self):
        dt, _normalized = classify_destination("http://internal.corp/healthz")
        assert dt == DestinationType.URL

    def test_cidr_rejected(self):
        with pytest.raises(ValidationError, match="CIDR"):
            classify_destination("10.0.0.0/8")

    def test_loopback_rejected(self):
        with pytest.raises(ValidationError, match=r"[Ll]oopback"):
            classify_destination("127.0.0.1")

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            classify_destination("")

    def test_leading_trailing_whitespace_stripped(self):
        _dt, normalized = classify_destination("  api.example.com  ")
        assert normalized == "api.example.com"


class TestValidatePort:
    def test_valid_port(self):
        assert validate_port(443) == 443

    def test_none_allowed(self):
        assert validate_port(None) is None

    def test_port_too_low(self):
        with pytest.raises(ValidationError):
            validate_port(0)

    def test_port_too_high(self):
        with pytest.raises(ValidationError):
            validate_port(65536)

    def test_boundary_port_1(self):
        assert validate_port(1) == 1

    def test_boundary_port_65535(self):
        assert validate_port(65535) == 65535


class TestRun:
    def test_full_validation(self):
        dt, dest, port = run("api.example.com", 443)
        assert dt == DestinationType.FQDN
        assert dest == "api.example.com"
        assert port == 443

    def test_url_with_no_port(self):
        dt, _dest, port = run("https://api.example.com", None)
        assert dt == DestinationType.URL
        assert port is None
