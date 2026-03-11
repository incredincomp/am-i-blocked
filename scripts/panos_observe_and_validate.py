#!/usr/bin/env python3
"""Bounded PAN-OS observe-and-validate orchestration.

Workflow:
1. Optionally ingest manual observability supplement (not required).
2. Enforce loop-breaker guard for repeated no-hit identical attempts.
3. Generate bounded source traffic over SSH (single target/port).
4. Run broad deny observability sweep (no destination token validation).
5. Select freshest matching deny row from returned entries.
6. If row exists, run token subqueries for addr.dst and dport independently.
7. Persist machine-readable state artifacts:
   - OBSERVABILITY_RECORD.json (always)
   - VALIDATION_RESULT.json (always)

This tool intentionally delegates PAN-OS API calls to gather_panos_fixtures.sh,
which enforces the repo read-only guardrails.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GATHER_SCRIPT = REPO_ROOT / "scripts" / "gather_panos_fixtures.sh"
OBSERVABILITY_RECORD_FILENAME = "OBSERVABILITY_RECORD.json"
VALIDATION_RESULT_FILENAME = "VALIDATION_RESULT.json"


@dataclass(frozen=True)
class Signature:
    source_ip: str
    app: str | None
    rule: str
    action: str
    session_end_reason: str
    zone_src: str | None
    zone_dst: str | None


@dataclass(frozen=True)
class RunConfig:
    host: str
    rule_xpath: str
    capture_label: str
    out_root: Path
    max_polls: int
    poll_interval: int
    lookback_minutes: int
    source_ssh_target: str
    traffic_command: str
    traffic_warmup_seconds: int
    traffic_generation_mode: str
    destination_ip: str
    destination_port: int | None
    signature: Signature
    api_key: str | None
    username: str | None
    password: str | None
    session_id: str | None
    ui_filter_string: str | None
    manual_observability_template: Path | None
    no_hit_loop_threshold: int


@dataclass
class CaptureArtifact:
    capture_dir: Path
    manifest: dict[str, str]
    entries: list[dict[str, str]]
    query: str


class LocalBackend:
    """Subprocess-backed backend for SSH traffic + gather script execution."""

    def __init__(self, cfg: RunConfig) -> None:
        self.cfg = cfg

    def check_ssh(self) -> tuple[bool, str]:
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            self.cfg.source_ssh_target,
            "echo",
            "PANOS_OBSERVE_OK",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout).strip()
        return True, ""

    def start_traffic(self) -> subprocess.Popen[str]:
        remote = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            self.cfg.source_ssh_target,
            "bash",
            "-lc",
            self.cfg.traffic_command,
        ]
        return subprocess.Popen(
            remote,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def collect_capture(self, label: str, query: str) -> CaptureArtifact:
        cmd = [
            str(GATHER_SCRIPT),
            "--host",
            self.cfg.host,
            "--rule-xpath",
            self.cfg.rule_xpath,
            "--capture-label",
            label,
            "--verification-scope",
            "real_env_partial",
            "--query",
            query,
            "--max-polls",
            str(self.cfg.max_polls),
            "--poll-interval",
            str(self.cfg.poll_interval),
            "--out-root",
            str(self.cfg.out_root),
        ]
        if self.cfg.api_key:
            cmd.extend(["--api-key", self.cfg.api_key])
        else:
            if not self.cfg.username or not self.cfg.password:
                raise RuntimeError("Missing API auth: provide --api-key or --username/--password")
            cmd.extend(["--username", self.cfg.username, "--password", self.cfg.password])

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"gather script failed for label={label}: rc={proc.returncode}\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )

        capture_dir = newest_capture_for_label(self.cfg.out_root, label)
        manifest = load_manifest(capture_dir / "CAPTURE_METADATA.txt")
        entries = parse_log_entries(capture_dir / "traffic_log_poll_response.xml")
        return CaptureArtifact(capture_dir=capture_dir, manifest=manifest, entries=entries, query=query)


def slugify(raw: str) -> str:
    out = []
    previous_dash = False
    for ch in raw.lower():
        if ch.isalnum() or ch in {".", "_", "-"}:
            out.append(ch)
            previous_dash = False
            continue
        if not previous_dash:
            out.append("-")
            previous_dash = True
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso_utc(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def newest_capture_for_label(out_root: Path, label: str) -> Path:
    version_root = out_root / "versions"
    if not version_root.exists():
        raise FileNotFoundError(f"No versioned capture root exists: {version_root}")
    prefix = f"{slugify(label)}_"
    candidates = [
        path
        for version_dir in version_root.iterdir()
        if version_dir.is_dir()
        for path in version_dir.iterdir()
        if path.is_dir() and path.name.startswith(prefix)
    ]
    if not candidates:
        raise FileNotFoundError(f"No capture directory found for label={label!r}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def default_output_dir(cfg: RunConfig, version: str = "unknown") -> Path:
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    return cfg.out_root / "versions" / version / f"{slugify(cfg.capture_label)}_{stamp}"


def load_manifest(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def parse_log_entries(path: Path) -> list[dict[str, str]]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    entries: list[dict[str, str]] = []
    for entry in root.findall(".//logs/entry"):
        row: dict[str, str] = {}
        for child in list(entry):
            if child.tag and child.text is not None:
                row[child.tag] = child.text.strip()
        if row:
            entries.append(row)
    return entries


def panos_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    parsed = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    return parsed.replace(tzinfo=UTC)


def _matches(entry_val: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    if entry_val is None:
        return False
    return entry_val.strip().lower() == expected.strip().lower()


def matches_signature(entry: dict[str, str], signature: Signature) -> bool:
    return all(
        [
            _matches(entry.get("src"), signature.source_ip),
            _matches(entry.get("rule"), signature.rule),
            _matches(entry.get("action"), signature.action),
            _matches(entry.get("session_end_reason"), signature.session_end_reason),
            _matches(entry.get("app"), signature.app),
            _matches(entry.get("from"), signature.zone_src),
            _matches(entry.get("to"), signature.zone_dst),
        ]
    )


def pick_freshest_match(entries: list[dict[str, str]], signature: Signature) -> tuple[dict[str, str] | None, int]:
    matches = [entry for entry in entries if matches_signature(entry, signature)]
    if not matches:
        return None, 0

    def sort_key(entry: dict[str, str]) -> datetime:
        return panos_ts(entry.get("receive_time") or entry.get("time_generated"))

    return max(matches, key=sort_key), len(matches)


def build_stage1_query(signature: Signature, lookback_minutes: int) -> str:
    cutoff = (now_utc() - timedelta(minutes=lookback_minutes)).strftime("%Y/%m/%d %H:%M:%S")
    clauses = [f"(addr.src eq {signature.source_ip})"]
    if signature.zone_src:
        clauses.append(f"(from eq {signature.zone_src})")
    if signature.zone_dst:
        clauses.append(f"(to eq {signature.zone_dst})")
    if signature.app:
        clauses.append(f"(app eq {signature.app})")
    clauses.extend(
        [
            f"(rule eq {signature.rule})",
            f"(action eq {signature.action})",
            f"(session_end_reason eq {signature.session_end_reason})",
            f"(receive_time geq '{cutoff}')",
        ]
    )
    return " and ".join(clauses)


def extend_query_addr_dst(base_query: str, dst: str) -> str:
    return f"{base_query} and (addr.dst eq {dst})"


def extend_query_dport(base_query: str, dport: int) -> str:
    return f"{base_query} and (dport eq {dport})"


def build_udp_traffic_command(dst: str, dport: int, duration_seconds: int, interval_seconds: float) -> str:
    return (
        "python3 - <<'PY'\n"
        "import socket, time\n"
        f"dst=({dst!r}, {dport})\n"
        "sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
        f"end=time.time()+{duration_seconds}\n"
        "i=0\n"
        "while time.time() < end:\n"
        "    sock.sendto(f'fixture-test-{i}'.encode(), dst)\n"
        "    i += 1\n"
        f"    time.sleep({interval_seconds})\n"
        "sock.close()\n"
        "PY"
    )


def operator_traffic_command(cfg: RunConfig) -> str:
    return (
        f"ssh {shlex.quote(cfg.source_ssh_target)} "
        f"{shlex.quote('bash -lc ' + shlex.quote(cfg.traffic_command))}"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manual_observability(template_path: Path | None) -> dict[str, Any]:
    if template_path is None:
        return {"present": False, "session_id": None, "ui_filter_string": None, "path": None}
    if not template_path.exists():
        return {
            "present": False,
            "session_id": None,
            "ui_filter_string": None,
            "path": str(template_path),
            "parse_error": "template_missing",
        }

    text = template_path.read_text(encoding="utf-8")

    def extract(pattern: str) -> str | None:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if not matches:
            return None
        value = matches[-1].strip().strip("`")
        if not value or value.lower().startswith("<leave blank"):
            return None
        return value

    session_id = extract(r"Session ID[^:]*:\s*([^\n]+)")
    ui_filter = extract(r"Exact Monitor filter string[^:]*:\s*([^\n]+)")
    freshness_note = extract(r"Freshness note[^:]*:\s*([^\n]+)")

    return {
        "present": True,
        "path": str(template_path),
        "session_id": session_id,
        "ui_filter_string": ui_filter,
        "freshness_note": freshness_note,
    }


def lookback_window_class(minutes: int) -> str:
    if minutes <= 5:
        return "short"
    if minutes <= 15:
        return "medium"
    return "long"


def build_attempt_signature(cfg: RunConfig) -> dict[str, Any]:
    payload = {
        "panos_version": "unknown",
        "source_ip": cfg.signature.source_ip,
        "destination_ip": cfg.destination_ip,
        "destination_port": cfg.destination_port,
        "app": cfg.signature.app,
        "action": cfg.signature.action,
        "rule": cfg.signature.rule,
        "session_end_reason": cfg.signature.session_end_reason,
        "zone_src": cfg.signature.zone_src,
        "zone_dst": cfg.signature.zone_dst,
        "scenario_name": slugify(cfg.capture_label),
        "traffic_generation_mode": cfg.traffic_generation_mode,
        "lookback_window_class": lookback_window_class(cfg.lookback_minutes),
    }
    return {"key": json.dumps(payload, sort_keys=True), "components": payload}


def iter_observability_records(out_root: Path) -> list[dict[str, Any]]:
    version_root = out_root / "versions"
    if not version_root.exists():
        return []

    records: list[dict[str, Any]] = []
    for obs_file in version_root.glob(f"**/{OBSERVABILITY_RECORD_FILENAME}"):
        try:
            data = json.loads(obs_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data["_path"] = str(obs_file)
        records.append(data)
    return records


def correlation_input_score(session_id: str | None, ui_filter_string: str | None, manual_present: bool) -> int:
    score = 0
    if session_id:
        score += 2
    if ui_filter_string:
        score += 2
    if manual_present:
        score += 1
    return score


def evaluate_loop_breaker(
    cfg: RunConfig,
    attempt_signature: dict[str, Any],
    manual_observability: dict[str, Any],
) -> dict[str, Any]:
    previous = iter_observability_records(cfg.out_root)
    matching = [
        row
        for row in previous
        if (row.get("attempt_signature") or {}).get("key") == attempt_signature["key"]
    ]
    previous_no_hits = [row for row in matching if row.get("observability_hit") is False]
    current_score = correlation_input_score(
        cfg.session_id or manual_observability.get("session_id"),
        cfg.ui_filter_string or manual_observability.get("ui_filter_string"),
        bool(manual_observability.get("present")),
    )
    max_prior_score = max(
        [
            int(
                (row.get("loop_breaker_state") or {}).get(
                    "current_correlation_score",
                    correlation_input_score(
                        row.get("session_id"),
                        row.get("ui_filter_string"),
                        bool((row.get("manual_observability") or {}).get("present")),
                    ),
                )
            )
            for row in previous_no_hits
        ],
        default=0,
    )
    improved = current_score > max_prior_score
    blocked = len(previous_no_hits) >= cfg.no_hit_loop_threshold and not improved

    return {
        "blocked": blocked,
        "reason": "loop_breaker_blocked_repeated_no_hit" if blocked else "not_triggered",
        "threshold": cfg.no_hit_loop_threshold,
        "prior_matching_attempt_count": len(matching),
        "prior_no_hit_count": len(previous_no_hits),
        "current_correlation_score": current_score,
        "max_prior_correlation_score": max_prior_score,
        "improved_correlation_input": improved,
        "matching_record_paths": [row.get("_path") for row in previous_no_hits][-5:],
    }


def make_base_record(
    cfg: RunConfig,
    run_started_at: datetime,
    manual_observability: dict[str, Any],
    attempt_signature: dict[str, Any],
    loop_breaker_state: dict[str, Any],
) -> dict[str, Any]:
    session_id = cfg.session_id or manual_observability.get("session_id")
    ui_filter = cfg.ui_filter_string or manual_observability.get("ui_filter_string")
    return {
        "panos_version": "unknown",
        "capture_provenance": "real_capture",
        "scenario_name": slugify(cfg.capture_label),
        "run_started_at": iso_utc(run_started_at),
        "run_finished_at": None,
        "source_ip": cfg.signature.source_ip,
        "destination_ip": cfg.destination_ip,
        "destination_port": cfg.destination_port,
        "app": cfg.signature.app,
        "action": cfg.signature.action,
        "rule": cfg.signature.rule,
        "session_end_reason": cfg.signature.session_end_reason,
        "zone_src": cfg.signature.zone_src,
        "zone_dst": cfg.signature.zone_dst,
        "lookback_minutes": cfg.lookback_minutes,
        "traffic_generation_mode": cfg.traffic_generation_mode,
        "traffic_generation_executed": False,
        "observability_hit": False,
        "matched_entry_count": 0,
        "best_match_timestamp": None,
        "best_match_entry_summary": {},
        "session_id": session_id,
        "ui_filter_string": ui_filter,
        "correlation_confidence": "low",
        "reason_if_not_validated": None,
        "validated_tokens": [],
        "addr_dst_validated": False,
        "dport_validated": False,
        "attempt_signature": attempt_signature,
        "loop_breaker_state": loop_breaker_state,
        "manual_observability": manual_observability,
        "queries": {},
        "capture_dirs": {},
        "operator_traffic_command": operator_traffic_command(cfg),
        "run_decision": "stop",
    }


def finalize_and_write(record: dict[str, Any], out_dir: Path) -> None:
    finished = now_utc()
    record["run_finished_at"] = iso_utc(finished)
    write_json(out_dir / OBSERVABILITY_RECORD_FILENAME, record)

    validation_result = {
        "scenario_name": record["scenario_name"],
        "capture_provenance": record["capture_provenance"],
        "panos_version": record["panos_version"],
        "observability_hit": record["observability_hit"],
        "matched_entry_count": record["matched_entry_count"],
        "best_match_timestamp": record["best_match_timestamp"],
        "validated_tokens": record["validated_tokens"],
        "addr_dst_validated": record["addr_dst_validated"],
        "dport_validated": record["dport_validated"],
        "reason_if_not_validated": record["reason_if_not_validated"],
        "queries": record["queries"],
        "capture_dirs": record["capture_dirs"],
        "best_match_summary": record["best_match_entry_summary"],
        "attempt_signature": record["attempt_signature"],
        "loop_breaker_state": record["loop_breaker_state"],
    }
    write_json(out_dir / VALIDATION_RESULT_FILENAME, validation_result)


def orchestrate(cfg: RunConfig, backend: LocalBackend) -> tuple[dict[str, Any], int]:
    run_started = now_utc()
    manual_observability = load_manual_observability(cfg.manual_observability_template)
    attempt_signature = build_attempt_signature(cfg)
    loop_breaker_state = evaluate_loop_breaker(cfg, attempt_signature, manual_observability)
    record = make_base_record(cfg, run_started, manual_observability, attempt_signature, loop_breaker_state)

    out_dir = default_output_dir(cfg)

    if loop_breaker_state["blocked"]:
        record["reason_if_not_validated"] = "loop_breaker_blocked"
        record["run_decision"] = "stop_loop_breaker"
        finalize_and_write(record, out_dir)
        print("Loop-breaker blocked run: repeated no-hit attempts with no materially improved correlation input.", file=sys.stderr)
        return record, 12

    ssh_ok, ssh_error = backend.check_ssh()
    if not ssh_ok:
        record["reason_if_not_validated"] = "source_host_ssh_unavailable"
        record["run_decision"] = "stop_source_host_failure"
        record["ssh_error"] = ssh_error
        finalize_and_write(record, out_dir)
        return record, 10

    traffic_proc: subprocess.Popen[str] | None = None
    stage1: CaptureArtifact | None = None
    stage1_query = build_stage1_query(cfg.signature, cfg.lookback_minutes)
    record["queries"]["stage1"] = stage1_query

    try:
        traffic_proc = backend.start_traffic()
        record["traffic_generation_executed"] = True
        time.sleep(max(cfg.traffic_warmup_seconds, 0))

        stage1_label = f"{cfg.capture_label}-stage1"
        stage1 = backend.collect_capture(stage1_label, stage1_query)
        out_dir = stage1.capture_dir

        record["capture_provenance"] = stage1.manifest.get("capture_provenance", "unknown")
        record["panos_version"] = stage1.manifest.get("panos_version_reported", "unknown")
        record["attempt_signature"]["components"]["panos_version"] = record["panos_version"]
        record["capture_dirs"]["stage1"] = str(stage1.capture_dir)

    except Exception as exc:
        record["reason_if_not_validated"] = "panos_capture_failed"
        record["run_decision"] = "stop_panos_access_failure"
        record["error_summary"] = str(exc)
        finalize_and_write(record, out_dir)
        return record, 13
    finally:
        if traffic_proc is not None:
            try:
                traffic_proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                traffic_proc.terminate()
                traffic_proc.wait(timeout=10)

    assert stage1 is not None
    best, match_count = pick_freshest_match(stage1.entries, cfg.signature)
    record["observability_hit"] = best is not None
    record["matched_entry_count"] = match_count
    record["best_match_entry_summary"] = best or {}
    record["best_match_timestamp"] = (best or {}).get("receive_time") or (best or {}).get("time_generated")

    if best is None:
        record["correlation_confidence"] = "low"
        record["reason_if_not_validated"] = "no_qualifying_deny_row"
        record["run_decision"] = "stop_observability_failed"
        finalize_and_write(record, out_dir)
        return record, 11

    record["correlation_confidence"] = "high"
    record["session_id"] = record["session_id"] or best.get("sessionid") or best.get("session_id")

    dst_value = best.get("dst") or cfg.destination_ip
    addr_query = extend_query_addr_dst(stage1_query, dst_value)
    try:
        stage2_addr = backend.collect_capture(f"{cfg.capture_label}-stage2-addrdst", addr_query)
    except Exception as exc:
        record["reason_if_not_validated"] = "token_validation_capture_failed"
        record["run_decision"] = "stop_token_validation_failure"
        record["error_summary"] = str(exc)
        finalize_and_write(record, out_dir)
        return record, 14

    record["queries"]["stage2_addr_dst"] = addr_query
    record["capture_dirs"]["stage2_addr_dst"] = str(stage2_addr.capture_dir)

    addr_match, _ = pick_freshest_match(stage2_addr.entries, cfg.signature)
    if addr_match and _matches(addr_match.get("dst"), dst_value):
        record["addr_dst_validated"] = True
        record["validated_tokens"].append("addr.dst")

    dport_value_str = best.get("dport") or (str(cfg.destination_port) if cfg.destination_port is not None else "")
    if dport_value_str.isdigit():
        dport_value = int(dport_value_str)
        dport_query = extend_query_dport(stage1_query, dport_value)
        try:
            stage2_dport = backend.collect_capture(f"{cfg.capture_label}-stage2-dport", dport_query)
        except Exception as exc:
            record["reason_if_not_validated"] = "token_validation_capture_failed"
            record["run_decision"] = "stop_token_validation_failure"
            record["error_summary"] = str(exc)
            finalize_and_write(record, out_dir)
            return record, 14

        record["queries"]["stage2_dport"] = dport_query
        record["capture_dirs"]["stage2_dport"] = str(stage2_dport.capture_dir)
        dport_match, _ = pick_freshest_match(stage2_dport.entries, cfg.signature)
        if dport_match and _matches(dport_match.get("dport"), str(dport_value)):
            record["dport_validated"] = True
            record["validated_tokens"].append("dport")

    if record["validated_tokens"]:
        record["run_decision"] = "proceed_token_validation_succeeded"
        record["reason_if_not_validated"] = None
        finalize_and_write(record, out_dir)
        return record, 0

    record["reason_if_not_validated"] = "token_subqueries_did_not_match"
    record["run_decision"] = "stop_token_validation_failed"
    finalize_and_write(record, out_dir)
    return record, 0


def parse_args(argv: list[str]) -> RunConfig:
    parser = argparse.ArgumentParser(description="Bounded PAN-OS observe-and-validate orchestrator")
    parser.add_argument("--host", required=True)
    parser.add_argument("--rule-xpath", required=True)
    parser.add_argument("--capture-label", required=True)
    parser.add_argument("--out-root", default="docs/fixtures/panos_verification")
    parser.add_argument("--max-polls", type=int, default=10)
    parser.add_argument("--poll-interval", type=int, default=1)
    parser.add_argument("--lookback-minutes", type=int, default=15)
    parser.add_argument("--no-hit-loop-threshold", type=int, default=2)

    parser.add_argument("--source-ssh-target", required=True)
    parser.add_argument("--traffic-command")
    parser.add_argument("--traffic-duration", type=int, default=60)
    parser.add_argument("--traffic-interval", type=float, default=0.2)
    parser.add_argument("--traffic-warmup-seconds", type=int, default=3)

    parser.add_argument("--source-ip", required=True)
    parser.add_argument("--destination-ip", required=True)
    parser.add_argument("--destination-port", type=int)
    parser.add_argument("--app")
    parser.add_argument("--rule", required=True)
    parser.add_argument("--action", default="deny")
    parser.add_argument("--session-end-reason", default="policy-deny")
    parser.add_argument("--zone-src")
    parser.add_argument("--zone-dst")

    parser.add_argument("--session-id")
    parser.add_argument("--ui-filter-string")
    parser.add_argument("--manual-observability-template")

    parser.add_argument("--api-key")
    parser.add_argument("--username")
    parser.add_argument("--password")

    args = parser.parse_args(argv)

    if not args.api_key and (not args.username or not args.password):
        parser.error("Provide --api-key, or both --username and --password")

    traffic_command = args.traffic_command
    traffic_generation_mode = "ssh_custom_command"
    if not traffic_command:
        if args.destination_port is None:
            parser.error("--destination-port is required when --traffic-command is not provided")
        traffic_command = build_udp_traffic_command(
            dst=args.destination_ip,
            dport=args.destination_port,
            duration_seconds=args.traffic_duration,
            interval_seconds=args.traffic_interval,
        )
        traffic_generation_mode = "ssh_builtin_udp"

    manual_template: Path | None = None
    if args.manual_observability_template:
        manual_template = Path(args.manual_observability_template)

    signature = Signature(
        source_ip=args.source_ip,
        app=args.app,
        rule=args.rule,
        action=args.action,
        session_end_reason=args.session_end_reason,
        zone_src=args.zone_src,
        zone_dst=args.zone_dst,
    )

    return RunConfig(
        host=args.host,
        rule_xpath=args.rule_xpath,
        capture_label=args.capture_label,
        out_root=Path(args.out_root),
        max_polls=args.max_polls,
        poll_interval=args.poll_interval,
        lookback_minutes=args.lookback_minutes,
        source_ssh_target=args.source_ssh_target,
        traffic_command=traffic_command,
        traffic_warmup_seconds=args.traffic_warmup_seconds,
        traffic_generation_mode=traffic_generation_mode,
        destination_ip=args.destination_ip,
        destination_port=args.destination_port,
        signature=signature,
        api_key=args.api_key,
        username=args.username,
        password=args.password,
        session_id=args.session_id,
        ui_filter_string=args.ui_filter_string,
        manual_observability_template=manual_template,
        no_hit_loop_threshold=args.no_hit_loop_threshold,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv or sys.argv[1:])
    backend = LocalBackend(cfg)
    result, code = orchestrate(cfg, backend)
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
