"""Unit tests for bounded PAN-OS observe-and-validate orchestration logic."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "panos_observe_and_validate.py"
    spec = importlib.util.spec_from_file_location("panos_observe_and_validate", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_capture(capture_dir: Path, entries_xml: str, query: str) -> None:
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / "CAPTURE_METADATA.txt").write_text(
        "\n".join(
            [
                "capture_provenance=real_capture",
                "panos_version_reported=11.0.6-h1",
                f"log_query_expr={query}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (capture_dir / "traffic_log_poll_response.xml").write_text(
        f"""
<response status=\"success\"><result><job><status>FIN</status></job><log>
<logs count=\"1\">{entries_xml}</logs>
</log></result></response>
""".strip(),
        encoding="utf-8",
    )


def _obs_files(root: Path) -> list[Path]:
    return sorted(root.glob("versions/**/OBSERVABILITY_RECORD.json"))


def _write_previous_obs(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _FakeTrafficProc:
    def wait(self, timeout: int | None = None) -> int:
        return 0


class _FakeBackend:
    def __init__(self, captures_by_label: dict[str, object], ssh_ok: bool = True) -> None:
        self.captures_by_label = captures_by_label
        self.ssh_ok = ssh_ok
        self.collected: list[tuple[str, str]] = []
        self.start_calls = 0

    def check_ssh(self):
        return (self.ssh_ok, "permission denied" if not self.ssh_ok else "")

    def start_traffic(self):
        self.start_calls += 1
        return _FakeTrafficProc()

    def collect_capture(self, label: str, query: str):
        self.collected.append((label, query))
        return self.captures_by_label[label]


def _make_cfg(m, tmp_path: Path, *, session_id: str | None = None, manual_template: Path | None = None):
    return m.RunConfig(
        host="10.1.99.1",
        rule_xpath="/config/devices/entry/vsys/entry/rulebase/security/rules",
        capture_label="distinct-deny",
        out_root=tmp_path,
        max_polls=10,
        poll_interval=1,
        lookback_minutes=15,
        source_ssh_target="root@10.1.99.3",
        traffic_command="echo test",
        traffic_warmup_seconds=0,
        traffic_generation_mode="ssh_custom_command",
        destination_ip="10.1.20.21",
        destination_port=30053,
        signature=m.Signature(
            source_ip="10.1.99.3",
            app="not-applicable",
            rule="interzone-default",
            action="deny",
            session_end_reason="policy-deny",
            zone_src="management",
            zone_dst="servers",
        ),
        api_key="k",
        username=None,
        password=None,
        session_id=session_id,
        ui_filter_string=None,
        manual_observability_template=manual_template,
        no_hit_loop_threshold=2,
    )


def test_pick_freshest_match_prefers_latest_matching_entry() -> None:
    m = _load_module()
    sig = m.Signature(
        source_ip="10.1.99.3",
        app="not-applicable",
        rule="interzone-default",
        action="deny",
        session_end_reason="policy-deny",
        zone_src="management",
        zone_dst="servers",
    )
    entries = [
        {
            "src": "10.1.99.3",
            "app": "not-applicable",
            "rule": "interzone-default",
            "action": "deny",
            "session_end_reason": "policy-deny",
            "from": "management",
            "to": "servers",
            "receive_time": "2026/03/10 23:30:00",
            "dst": "10.1.20.21",
        },
        {
            "src": "10.1.99.3",
            "app": "not-applicable",
            "rule": "interzone-default",
            "action": "deny",
            "session_end_reason": "policy-deny",
            "from": "management",
            "to": "servers",
            "receive_time": "2026/03/10 23:35:00",
            "dst": "10.1.20.22",
        },
    ]
    best, count = m.pick_freshest_match(entries, sig)
    assert count == 2
    assert best is not None
    assert best["dst"] == "10.1.20.22"


def test_orchestrate_writes_observability_record_when_ssh_unavailable(tmp_path: Path) -> None:
    m = _load_module()
    cfg = _make_cfg(m, tmp_path)

    result, code = m.orchestrate(cfg, _FakeBackend(captures_by_label={}, ssh_ok=False))
    assert code == 10
    assert result["observability_hit"] is False
    assert result["reason_if_not_validated"] == "source_host_ssh_unavailable"

    obs_files = _obs_files(tmp_path)
    assert len(obs_files) == 1
    obs = json.loads(obs_files[0].read_text(encoding="utf-8"))
    assert obs["reason_if_not_validated"] == "source_host_ssh_unavailable"
    assert obs["traffic_generation_executed"] is False


def test_orchestrate_stops_without_stage2_when_no_observability_hit_and_writes_records(tmp_path: Path) -> None:
    m = _load_module()
    stage1_dir = tmp_path / "versions" / "11.0.6-h1" / "distinct-stage1_1"
    _write_capture(
        stage1_dir,
        "<entry><action>allow</action><src>10.1.99.3</src></entry>",
        "(addr.src eq 10.1.99.3)",
    )
    stage1 = m.CaptureArtifact(
        capture_dir=stage1_dir,
        manifest=m.load_manifest(stage1_dir / "CAPTURE_METADATA.txt"),
        entries=m.parse_log_entries(stage1_dir / "traffic_log_poll_response.xml"),
        query="(addr.src eq 10.1.99.3)",
    )

    cfg = _make_cfg(m, tmp_path)
    backend = _FakeBackend(captures_by_label={"distinct-deny-stage1": stage1}, ssh_ok=True)

    result, code = m.orchestrate(cfg, backend)
    assert code == 11
    assert result["observability_hit"] is False
    assert result["reason_if_not_validated"] == "no_qualifying_deny_row"
    assert backend.collected == [("distinct-deny-stage1", backend.collected[0][1])]

    obs = json.loads((stage1_dir / "OBSERVABILITY_RECORD.json").read_text(encoding="utf-8"))
    assert obs["observability_hit"] is False
    summary = json.loads((stage1_dir / "VALIDATION_RESULT.json").read_text(encoding="utf-8"))
    assert summary["observability_hit"] is False


def test_orchestrate_writes_observability_record_on_success(tmp_path: Path) -> None:
    m = _load_module()
    stage1_dir = tmp_path / "versions" / "11.0.6-h1" / "distinct-stage1_2"
    stage2_addr_dir = tmp_path / "versions" / "11.0.6-h1" / "distinct-stage2-addr_2"
    stage2_dport_dir = tmp_path / "versions" / "11.0.6-h1" / "distinct-stage2-dport_2"

    common = (
        "<src>10.1.99.3</src><app>not-applicable</app><rule>interzone-default</rule>"
        "<action>deny</action><session_end_reason>policy-deny</session_end_reason>"
        "<from>management</from><to>servers</to><receive_time>2026/03/10 23:36:42</receive_time>"
    )
    _write_capture(stage1_dir, f"<entry>{common}<dst>10.1.20.21</dst><dport>30053</dport></entry>", "q1")
    _write_capture(stage2_addr_dir, f"<entry>{common}<dst>10.1.20.21</dst></entry>", "q2")
    _write_capture(stage2_dport_dir, f"<entry>{common}<dport>30053</dport></entry>", "q3")

    stage1 = m.CaptureArtifact(stage1_dir, m.load_manifest(stage1_dir / "CAPTURE_METADATA.txt"), m.parse_log_entries(stage1_dir / "traffic_log_poll_response.xml"), "q1")
    stage2_addr = m.CaptureArtifact(stage2_addr_dir, m.load_manifest(stage2_addr_dir / "CAPTURE_METADATA.txt"), m.parse_log_entries(stage2_addr_dir / "traffic_log_poll_response.xml"), "q2")
    stage2_dport = m.CaptureArtifact(stage2_dport_dir, m.load_manifest(stage2_dport_dir / "CAPTURE_METADATA.txt"), m.parse_log_entries(stage2_dport_dir / "traffic_log_poll_response.xml"), "q3")

    cfg = _make_cfg(m, tmp_path)
    backend = _FakeBackend(
        captures_by_label={
            "distinct-deny-stage1": stage1,
            "distinct-deny-stage2-addrdst": stage2_addr,
            "distinct-deny-stage2-dport": stage2_dport,
        },
        ssh_ok=True,
    )

    result, code = m.orchestrate(cfg, backend)
    assert code == 0
    assert result["observability_hit"] is True
    assert result["addr_dst_validated"] is True
    assert result["dport_validated"] is True

    obs = json.loads((stage1_dir / "OBSERVABILITY_RECORD.json").read_text(encoding="utf-8"))
    assert obs["run_decision"] == "proceed_token_validation_succeeded"
    assert set(obs["validated_tokens"]) == {"addr.dst", "dport"}


def test_loop_breaker_blocks_repeated_no_hit_identical_signature(tmp_path: Path) -> None:
    m = _load_module()
    cfg = _make_cfg(m, tmp_path)
    attempt_signature = m.build_attempt_signature(cfg)

    for idx in (1, 2):
        prior_path = tmp_path / "versions" / "11.0.6-h1" / f"prior-{idx}" / "OBSERVABILITY_RECORD.json"
        _write_previous_obs(
            prior_path,
            {
                "attempt_signature": attempt_signature,
                "observability_hit": False,
                "session_id": None,
                "ui_filter_string": None,
                "manual_observability": {"present": False},
                "loop_breaker_state": {"current_correlation_score": 0},
            },
        )

    backend = _FakeBackend(captures_by_label={}, ssh_ok=True)
    result, code = m.orchestrate(cfg, backend)
    assert code == 12
    assert result["reason_if_not_validated"] == "loop_breaker_blocked"
    assert backend.start_calls == 0
    assert backend.collected == []


def test_loop_breaker_allows_retry_with_improved_correlation_input(tmp_path: Path) -> None:
    m = _load_module()
    cfg = _make_cfg(m, tmp_path, session_id="78")
    attempt_signature = m.build_attempt_signature(cfg)

    for idx in (1, 2):
        prior_path = tmp_path / "versions" / "11.0.6-h1" / f"prior-{idx}" / "OBSERVABILITY_RECORD.json"
        _write_previous_obs(
            prior_path,
            {
                "attempt_signature": attempt_signature,
                "observability_hit": False,
                "session_id": None,
                "ui_filter_string": None,
                "manual_observability": {"present": False},
                "loop_breaker_state": {"current_correlation_score": 0},
            },
        )

    stage1_dir = tmp_path / "versions" / "11.0.6-h1" / "distinct-stage1-allow_1"
    _write_capture(
        stage1_dir,
        "<entry><action>allow</action><src>10.1.99.3</src></entry>",
        "(addr.src eq 10.1.99.3)",
    )
    stage1 = m.CaptureArtifact(
        capture_dir=stage1_dir,
        manifest=m.load_manifest(stage1_dir / "CAPTURE_METADATA.txt"),
        entries=m.parse_log_entries(stage1_dir / "traffic_log_poll_response.xml"),
        query="(addr.src eq 10.1.99.3)",
    )

    backend = _FakeBackend(captures_by_label={"distinct-deny-stage1": stage1}, ssh_ok=True)
    result, code = m.orchestrate(cfg, backend)
    assert code == 11
    assert result["reason_if_not_validated"] == "no_qualifying_deny_row"
    assert backend.start_calls == 1


def test_parse_args_manual_template_is_optional() -> None:
    m = _load_module()
    cfg = m.parse_args(
        [
            "--host",
            "10.1.99.1",
            "--rule-xpath",
            "/config/devices/entry/vsys/entry/rulebase/security/rules",
            "--capture-label",
            "distinct-deny",
            "--source-ssh-target",
            "root@10.1.99.3",
            "--traffic-command",
            "echo test",
            "--source-ip",
            "10.1.99.3",
            "--destination-ip",
            "10.1.20.21",
            "--destination-port",
            "30053",
            "--rule",
            "interzone-default",
            "--api-key",
            "k",
        ]
    )
    assert cfg.manual_observability_template is None
