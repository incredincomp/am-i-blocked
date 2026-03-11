"""Tests for OBSERVABILITY_INPUT preparation helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "prepare_panos_observability_input.py"
    spec = importlib.util.spec_from_file_location("prepare_panos_observability_input", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prepare_observability_input_ready_from_strong_row_json(tmp_path: Path) -> None:
    m = _load_module()
    row_json = tmp_path / "row.json"
    row_json.write_text(
        json.dumps(
            {
                "panos_version": "11.0.6-h1",
                "sessionid": "78",
                "query": "!( action eq 'allow' )",
                "src": "10.1.99.3",
                "dst": "10.1.20.21",
                "dport": "30053",
                "app": "not-applicable",
                "action": "deny",
                "rule": "interzone-default",
                "session_end_reason": "policy-deny",
                "from": "management",
                "to": "servers",
                "type": "drop",
                "receive_time": "2026/03/10 23:36:42",
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "OBSERVABILITY_INPUT.json"
    code = m.main(
        [
            "--row-json",
            str(row_json),
            "--out",
            str(out),
            "--evidence-origin",
            "ui_json_export",
            "--freshness-note",
            "fresh deny row matched reproduction window",
        ]
    )

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ready_for_orchestrator"] is True
    assert payload["correlation_confidence"] == "high"
    assert payload["session_id"] == "78"
    assert payload["ui_filter_string"] == "!( action eq 'allow' )"
    assert payload["destination_port"] == 30053
    assert payload["why_not_ready"] is None


def test_prepare_observability_input_marks_not_ready_for_weak_inputs(tmp_path: Path) -> None:
    m = _load_module()
    out = tmp_path / "OBSERVABILITY_INPUT.json"

    code = m.main(
        [
            "--out",
            str(out),
            "--source-ip",
            "10.1.99.3",
            "--destination-ip",
            "10.1.20.21",
            "--destination-port",
            "30053",
            "--action",
            "deny",
            "--rule",
            "interzone-default",
            "--session-end-reason",
            "policy-deny",
            "--row-timestamp",
            "2026/03/10 23:36:42",
            "--evidence-origin",
            "manual",
        ]
    )

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ready_for_orchestrator"] is False
    assert payload["correlation_confidence"] == "low"
    why = payload["why_not_ready"]
    assert isinstance(why, list)
    assert "correlation_signals_too_weak" in why
    assert "session_id_missing" in why
    assert "ui_filter_string_missing" in why
