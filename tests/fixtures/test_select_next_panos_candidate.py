"""Tests for PAN-OS next-candidate family selection helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "select_next_panos_candidate.py"
    spec = importlib.util.spec_from_file_location("select_next_panos_candidate", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_real_coverage() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification" / "OBSERVABILITY_COVERAGE.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_classifies_proven_udp_family_from_validated_tokens() -> None:
    m = _load_module()
    coverage = _load_real_coverage()
    run_to_family = m._build_run_to_family(coverage)
    versions_root = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification" / "versions"
    obs_by_family, _ = m._load_record_maps(versions_root, run_to_family)

    decisions = m.classify_families(coverage, obs_by_family)
    by_id = {d.family_id: d for d in decisions}
    family_id = "10.1.99.10|10.1.20.20|30053|not-applicable|tcp|interzone-default|policy-deny|unknown"
    assert by_id[family_id].status == "proven"
    assert "scenario_scoped_token_validation_exists" in by_id[family_id].reasons


def test_classifies_repeated_no_hit_tcp_family_as_exhausted() -> None:
    m = _load_module()
    coverage = _load_real_coverage()
    run_to_family = m._build_run_to_family(coverage)
    versions_root = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification" / "versions"
    obs_by_family, _ = m._load_record_maps(versions_root, run_to_family)

    decisions = m.classify_families(coverage, obs_by_family)
    by_id = {d.family_id: d for d in decisions}
    family_id = "10.1.99.3|10.1.20.21|30053|not-applicable|unknown|interzone-default|policy-deny|ssh_custom_command"
    assert by_id[family_id].status == "exhausted_pending_new_evidence"
    assert "repeated_no_hit_with_high_confidence_attempt" in by_id[family_id].reasons


def test_choose_primary_recommendation_returns_exactly_one_action() -> None:
    m = _load_module()
    coverage = _load_real_coverage()
    run_to_family = m._build_run_to_family(coverage)
    versions_root = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification" / "versions"
    obs_by_family, _ = m._load_record_maps(versions_root, run_to_family)
    decisions = m.classify_families(coverage, obs_by_family)

    recommendation = m.choose_primary_recommendation(decisions)
    assert set(recommendation) == {"action", "family_id", "score", "why"}
    assert recommendation["action"] in {"run_next_candidate_family", "pause_panos_token_expansion"}


def test_choose_primary_recommendation_can_pause_when_no_viable_candidate() -> None:
    m = _load_module()
    decisions = [
        m.FamilyDecision(
            family_id="f1",
            status="candidate",
            reasons=["not_proven_and_not_exhausted"],
            traits={"destination_ip": "unknown", "destination_port": "unknown"},
            metrics={"no_observability_hit_runs": 0},
        ),
        m.FamilyDecision(
            family_id="f2",
            status="exhausted_pending_new_evidence",
            reasons=["repeated_no_hit_pattern"],
            traits={"destination_ip": "10.1.20.21", "destination_port": 30053},
            metrics={"no_observability_hit_runs": 3},
        ),
    ]

    recommendation = m.choose_primary_recommendation(decisions)
    assert recommendation["action"] == "pause_panos_token_expansion"
    assert recommendation["family_id"] is None
