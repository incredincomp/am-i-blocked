"""Helpers to select PAN-OS verification fixtures by version and scenario."""

from __future__ import annotations

import re
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification"
TIMESTAMP_SUFFIX_RE = re.compile(r"_(\d{8}T\d{6}Z)$")

REQUIRED_XML_FILES = (
    "traffic_log_submit_response.xml",
    "traffic_log_poll_response.xml",
    "rule_metadata_config_response.xml",
)

ALLOWED_CAPTURE_PROVENANCE = {
    "real_capture",
    "template_seeded",
    "synthetic",
}
ALLOWED_VERIFICATION_SCOPE = {
    "parser_shape_only",
    "query_shape_partial",
    "xpath_shape_partial",
    "real_env_partial",
    "real_env_high_confidence",
}
ALLOWED_PANOS_VERSION_SOURCE = {
    "auto_detected",
    "override",
    "unknown",
}
VERIFICATION_SCOPE_ORDER = (
    "parser_shape_only",
    "query_shape_partial",
    "xpath_shape_partial",
    "real_env_partial",
    "real_env_high_confidence",
)
REQUIRED_MANIFEST_FIELDS = (
    "capture_provenance",
    "verification_scope",
    "panos_version_reported",
    "panos_version_source",
    "scenario",
    "captured_at_utc",
    "capture_label",
    "notes",
)


def _slugify(value: str) -> str:
    lowered = value.lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9._-]+", "-", lowered)).strip("-")


def _scenario_from_capture_dir(capture_dir: Path) -> str:
    match = TIMESTAMP_SUFFIX_RE.search(capture_dir.name)
    if not match:
        return capture_dir.name
    return capture_dir.name[: match.start()]


def _scope_rank(scope: str) -> int:
    return VERIFICATION_SCOPE_ORDER.index(scope)


def list_versioned_captures(version: str, fixture_root: Path = FIXTURE_ROOT) -> list[Path]:
    """Return capture directories for a PAN-OS version, newest first."""
    version_dir = fixture_root / "versions" / _slugify(version)
    if not version_dir.exists():
        return []

    captures = [path for path in version_dir.iterdir() if path.is_dir()]
    # Timestamp format is lexicographically sortable.
    return sorted(captures, key=lambda path: path.name, reverse=True)


def select_versioned_capture(
    version: str,
    scenario: str,
    require_provenance: str | None = None,
    minimum_verification_scope: str | None = None,
    fixture_root: Path = FIXTURE_ROOT,
) -> Path:
    """Select the newest versioned fixture capture for a version/scenario."""
    if require_provenance is not None and require_provenance not in ALLOWED_CAPTURE_PROVENANCE:
        raise ValueError(
            f"Invalid require_provenance={require_provenance!r}; "
            f"allowed={sorted(ALLOWED_CAPTURE_PROVENANCE)}"
        )
    if (
        minimum_verification_scope is not None
        and minimum_verification_scope not in ALLOWED_VERIFICATION_SCOPE
    ):
        raise ValueError(
            f"Invalid minimum_verification_scope={minimum_verification_scope!r}; "
            f"allowed={list(VERIFICATION_SCOPE_ORDER)}"
        )

    scenario_slug = _slugify(scenario)
    all_scenario_captures = [
        capture
        for capture in list_versioned_captures(version=version, fixture_root=fixture_root)
        if _scenario_from_capture_dir(capture) == scenario_slug
    ]
    if not all_scenario_captures:
        raise FileNotFoundError(
            f"No PAN-OS fixture capture found for version={version!r}, scenario={scenario!r}"
        )

    parsed_scenario_captures: list[tuple[Path, dict[str, str]]] = [
        (capture_dir, load_capture_manifest(capture_dir)) for capture_dir in all_scenario_captures
    ]
    matching: list[tuple[Path, dict[str, str]]] = []
    for capture_dir, manifest in parsed_scenario_captures:
        provenance = manifest["capture_provenance"]
        scope = manifest["verification_scope"]
        if require_provenance is not None and provenance != require_provenance:
            continue
        if minimum_verification_scope is not None and _scope_rank(scope) < _scope_rank(
            minimum_verification_scope
        ):
            continue
        matching.append((capture_dir, manifest))

    if not matching:
        available = ", ".join(
            f"{path.name}(provenance={manifest['capture_provenance']},"
            f" scope={manifest['verification_scope']})"
            for path, manifest in parsed_scenario_captures
        )
        raise FileNotFoundError(
            "No PAN-OS fixture capture matched requested trust filters for "
            f"version={version!r}, scenario={scenario!r}, "
            f"require_provenance={require_provenance!r}, "
            f"minimum_verification_scope={minimum_verification_scope!r}. "
            f"Available: {available or 'none'}"
        )

    capture_dir = matching[0][0]
    missing = [name for name in REQUIRED_XML_FILES if not (capture_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Capture {capture_dir} missing required files: {', '.join(sorted(missing))}"
        )
    return capture_dir


def load_capture_manifest(capture_dir: Path) -> dict[str, str]:
    """Load and validate key=value metadata entries from CAPTURE_METADATA.txt."""
    manifest = capture_dir / "CAPTURE_METADATA.txt"
    if not manifest.exists():
        raise FileNotFoundError(f"Capture metadata file missing: {manifest}")

    data: dict[str, str] = {}
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()

    missing_fields = [field for field in REQUIRED_MANIFEST_FIELDS if not data.get(field)]
    if missing_fields:
        raise ValueError(
            f"Invalid capture metadata in {manifest}: missing required fields "
            f"{', '.join(sorted(missing_fields))}"
        )
    if data["capture_provenance"] not in ALLOWED_CAPTURE_PROVENANCE:
        raise ValueError(
            f"Invalid capture_provenance={data['capture_provenance']!r} in {manifest}; "
            f"allowed={sorted(ALLOWED_CAPTURE_PROVENANCE)}"
        )
    if data["verification_scope"] not in ALLOWED_VERIFICATION_SCOPE:
        raise ValueError(
            f"Invalid verification_scope={data['verification_scope']!r} in {manifest}; "
            f"allowed={list(VERIFICATION_SCOPE_ORDER)}"
        )
    if data["panos_version_source"] not in ALLOWED_PANOS_VERSION_SOURCE:
        raise ValueError(
            f"Invalid panos_version_source={data['panos_version_source']!r} in {manifest}; "
            f"allowed={sorted(ALLOWED_PANOS_VERSION_SOURCE)}"
        )
    return data
