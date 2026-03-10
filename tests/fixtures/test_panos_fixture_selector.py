"""Tests for selecting versioned PAN-OS fixture captures by scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.panos_fixture_selector import (
    load_capture_manifest,
    select_versioned_capture,
)


def _write_required_files(capture_dir: Path) -> None:
    capture_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "traffic_log_submit_response.xml",
        "traffic_log_poll_response.xml",
        "rule_metadata_config_response.xml",
    ):
        (capture_dir / name).write_text("<response/>", encoding="utf-8")


def _write_manifest(
    capture_dir: Path,
    *,
    capture_provenance: str = "template_seeded",
    verification_scope: str = "parser_shape_only",
    panos_version_reported: str = "11.0.2",
    panos_version_source: str = "unknown",
    scenario: str = "deny-hit",
    captured_at_utc: str = "2026-03-08T21:00:00Z",
    capture_label: str = "deny-hit",
    notes: str = "fixture",
) -> None:
    (capture_dir / "CAPTURE_METADATA.txt").write_text(
        "\n".join(
            (
                f"capture_provenance={capture_provenance}",
                f"verification_scope={verification_scope}",
                f"panos_version_reported={panos_version_reported}",
                f"panos_version_source={panos_version_source}",
                f"scenario={scenario}",
                f"captured_at_utc={captured_at_utc}",
                f"capture_label={capture_label}",
                f"notes={notes}",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_select_versioned_capture_returns_newest_matching_scenario(tmp_path: Path) -> None:
    root = tmp_path / "panos_verification"
    older = root / "versions" / "11.0.2" / "deny-hit_20260308T010000Z"
    newer = root / "versions" / "11.0.2" / "deny-hit_20260308T020000Z"
    _write_required_files(older)
    _write_required_files(newer)
    _write_manifest(older)
    _write_manifest(newer)

    selected = select_versioned_capture(version="11.0.2", scenario="deny-hit", fixture_root=root)

    assert selected == newer


def test_select_versioned_capture_raises_when_required_file_missing(tmp_path: Path) -> None:
    root = tmp_path / "panos_verification"
    broken = root / "versions" / "11.0.2" / "deny-hit_20260308T020000Z"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "traffic_log_submit_response.xml").write_text("<response/>", encoding="utf-8")
    _write_manifest(broken)

    with pytest.raises(FileNotFoundError):
        select_versioned_capture(version="11.0.2", scenario="deny-hit", fixture_root=root)


def test_load_capture_manifest_parses_key_value_pairs(tmp_path: Path) -> None:
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(capture_dir, notes="fixture notes")
    (capture_dir / "CAPTURE_METADATA.txt").write_text(
        (capture_dir / "CAPTURE_METADATA.txt").read_text(encoding="utf-8") + "invalid_line\n",
        encoding="utf-8",
    )

    manifest = load_capture_manifest(capture_dir)

    assert manifest["panos_version_reported"] == "11.0.2"
    assert manifest["scenario"] == "deny-hit"
    assert manifest["capture_provenance"] == "template_seeded"


def test_select_versioned_capture_applies_provenance_filter_before_newest(tmp_path: Path) -> None:
    root = tmp_path / "panos_verification"
    template_newer = root / "versions" / "11.0.2" / "deny-hit_20260308T030000Z"
    real_older = root / "versions" / "11.0.2" / "deny-hit_20260308T020000Z"
    _write_required_files(template_newer)
    _write_required_files(real_older)
    _write_manifest(template_newer, capture_provenance="template_seeded", verification_scope="parser_shape_only")
    _write_manifest(real_older, capture_provenance="real_capture", verification_scope="real_env_partial")

    selected = select_versioned_capture(
        version="11.0.2",
        scenario="deny-hit",
        require_provenance="real_capture",
        fixture_root=root,
    )

    assert selected == real_older


def test_select_versioned_capture_real_capture_required_fails_if_absent(tmp_path: Path) -> None:
    root = tmp_path / "panos_verification"
    template_only = root / "versions" / "11.0.2" / "deny-hit_20260308T020000Z"
    _write_required_files(template_only)
    _write_manifest(template_only, capture_provenance="template_seeded", verification_scope="parser_shape_only")

    with pytest.raises(FileNotFoundError, match="require_provenance='real_capture'"):
        select_versioned_capture(
            version="11.0.2",
            scenario="deny-hit",
            require_provenance="real_capture",
            fixture_root=root,
        )


def test_select_versioned_capture_applies_minimum_verification_scope_filter(tmp_path: Path) -> None:
    root = tmp_path / "panos_verification"
    lower_scope_newer = root / "versions" / "11.0.2" / "deny-hit_20260308T030000Z"
    higher_scope_older = root / "versions" / "11.0.2" / "deny-hit_20260308T020000Z"
    _write_required_files(lower_scope_newer)
    _write_required_files(higher_scope_older)
    _write_manifest(lower_scope_newer, capture_provenance="real_capture", verification_scope="real_env_partial")
    _write_manifest(
        higher_scope_older,
        capture_provenance="real_capture",
        verification_scope="real_env_high_confidence",
    )

    selected = select_versioned_capture(
        version="11.0.2",
        scenario="deny-hit",
        require_provenance="real_capture",
        minimum_verification_scope="real_env_high_confidence",
        fixture_root=root,
    )

    assert selected == higher_scope_older


def test_load_capture_manifest_rejects_invalid_capture_provenance(tmp_path: Path) -> None:
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(capture_dir, capture_provenance="guess")

    with pytest.raises(ValueError, match="Invalid capture_provenance"):
        load_capture_manifest(capture_dir)


def test_load_capture_manifest_rejects_missing_required_fields(tmp_path: Path) -> None:
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / "CAPTURE_METADATA.txt").write_text("scenario=deny-hit\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields"):
        load_capture_manifest(capture_dir)


def test_select_versioned_capture_real_capture_repo_fixture_for_no_match() -> None:
    selected = select_versioned_capture(
        version="11.0.6-h1",
        scenario="no-match",
        require_provenance="real_capture",
        minimum_verification_scope="real_env_partial",
    )
    manifest = load_capture_manifest(selected)
    assert manifest["capture_provenance"] == "real_capture"
    assert manifest["scenario"] == "no-match"
