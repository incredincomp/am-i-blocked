"""Validation scaffolding for PAN-OS verification fixture pack files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests.fixtures.panos_fixture_selector import (
    ALLOWED_CAPTURE_PROVENANCE,
    ALLOWED_PANOS_VERSION_SOURCE,
    ALLOWED_VERIFICATION_SCOPE,
    load_capture_manifest,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification"

REQUIRED_XML_FILES = (
    "traffic_log_submit_response.xml",
    "traffic_log_poll_response.xml",
    "rule_metadata_config_response.xml",
)


def _load_xml_fixture(filename: str) -> ET.Element:
    fixture_path = FIXTURE_ROOT / filename
    return ET.fromstring(fixture_path.read_text(encoding="utf-8"))


def test_panos_verification_fixture_pack_required_files_exist() -> None:
    assert FIXTURE_ROOT.exists()
    assert (FIXTURE_ROOT / "README.md").exists()
    for filename in REQUIRED_XML_FILES:
        assert (FIXTURE_ROOT / filename).exists()


def test_panos_verification_fixture_pack_xml_is_parseable() -> None:
    for filename in REQUIRED_XML_FILES:
        root = _load_xml_fixture(filename)
        assert root.tag == "response"


def test_panos_verification_fixture_pack_contains_minimum_expected_markers() -> None:
    submit_root = _load_xml_fixture("traffic_log_submit_response.xml")
    assert submit_root.find(".//job") is not None

    poll_root = _load_xml_fixture("traffic_log_poll_response.xml")
    assert poll_root.find(".//status") is not None
    # Real captures may represent a valid finished no-match poll with zero log entries.
    assert poll_root.find(".//logs") is not None

    metadata_root = _load_xml_fixture("rule_metadata_config_response.xml")
    assert metadata_root.find(".//entry") is not None


def test_panos_verification_fixture_pack_readme_contains_required_sanitization_contract() -> None:
    readme = (FIXTURE_ROOT / "README.md").read_text(encoding="utf-8").lower()
    required_terms = (
        "versions/<panos_version>",
        "capture_metadata.txt",
        "capture_provenance",
        "verification_scope",
        "panos_version_source",
        "versioned does not automatically mean verified",
        "real_capture",
        "template_seeded",
        "synthetic",
        "ips",
        "usernames",
        "hostnames",
        "serial numbers",
        "device names",
        "rule names",
        "ticket ids",
        "tokens",
        "cookies",
        "api keys",
        "preserve xml",
        "consistent placeholders",
        "never treat redacted sample values as authoritative",
    )
    for term in required_terms:
        assert term in readme


def test_panos_verification_versioned_captures_have_valid_required_manifest_fields() -> None:
    version_root = FIXTURE_ROOT / "versions"
    if not version_root.exists():
        return

    for capture_dir in sorted(path for path in version_root.glob("*/*") if path.is_dir()):
        manifest = load_capture_manifest(capture_dir)
        assert manifest["capture_provenance"] in ALLOWED_CAPTURE_PROVENANCE
        assert manifest["verification_scope"] in ALLOWED_VERIFICATION_SCOPE
        assert manifest["panos_version_source"] in ALLOWED_PANOS_VERSION_SOURCE
