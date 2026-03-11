#!/usr/bin/env python3
"""Bounded PAN-OS observe-and-validate orchestration.

Workflow:
1. Generate bounded source traffic over SSH (single target/port).
2. Run broad deny observability sweep (no destination token validation).
3. Select freshest matching deny row from returned entries.
4. If row exists, run token subqueries for addr.dst and dport independently.
5. Persist machine-readable validation summary in the Stage 1 capture directory.

This tool intentionally delegates PAN-OS API calls to gather_panos_fixtures.sh,
which enforces the repo read-only guardrails.
"""

from __future__ import annotations

import argparse
import json
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
    destination_ip: str
    destination_port: int | None
    signature: Signature
    api_key: str | None
    username: str | None
    password: str | None


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
    cutoff = (datetime.now(UTC) - timedelta(minutes=lookback_minutes)).strftime("%Y/%m/%d %H:%M:%S")
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


def write_result_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def orchestrate(cfg: RunConfig, backend: LocalBackend) -> tuple[dict[str, Any], int]:
    ssh_ok, ssh_error = backend.check_ssh()
    if not ssh_ok:
        result = {
            "scenario_name": slugify(cfg.capture_label),
            "capture_provenance": "real_capture",
            "panos_version": "unknown",
            "observability_hit": False,
            "matched_entry_count": 0,
            "best_match_timestamp": None,
            "validated_tokens": [],
            "addr_dst_validated": False,
            "dport_validated": False,
            "reason_if_not_validated": "source_host_ssh_unavailable",
            "operator_traffic_command": operator_traffic_command(cfg),
            "ssh_error": ssh_error,
        }
        fallback = cfg.out_root / "versions" / "unknown" / f"{slugify(cfg.capture_label)}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        write_result_json(fallback / "VALIDATION_RESULT.json", result)
        return result, 10

    traffic_proc = backend.start_traffic()
    time.sleep(max(cfg.traffic_warmup_seconds, 0))

    stage1_query = build_stage1_query(cfg.signature, cfg.lookback_minutes)
    stage1_label = f"{cfg.capture_label}-stage1"
    stage1 = backend.collect_capture(stage1_label, stage1_query)

    try:
        traffic_proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        traffic_proc.terminate()
        traffic_proc.wait(timeout=10)

    best, match_count = pick_freshest_match(stage1.entries, cfg.signature)
    result: dict[str, Any] = {
        "scenario_name": slugify(cfg.capture_label),
        "capture_provenance": stage1.manifest.get("capture_provenance", "unknown"),
        "panos_version": stage1.manifest.get("panos_version_reported", "unknown"),
        "observability_hit": best is not None,
        "matched_entry_count": match_count,
        "best_match_timestamp": (best or {}).get("receive_time") or (best or {}).get("time_generated"),
        "validated_tokens": [],
        "addr_dst_validated": False,
        "dport_validated": False,
        "reason_if_not_validated": None,
        "queries": {"stage1": stage1.query},
        "capture_dirs": {"stage1": str(stage1.capture_dir)},
        "best_match_summary": best or {},
    }

    if best is None:
        result["reason_if_not_validated"] = "no_qualifying_deny_row"
        write_result_json(stage1.capture_dir / "VALIDATION_RESULT.json", result)
        return result, 11

    dst_value = best.get("dst") or cfg.destination_ip
    addr_query = extend_query_addr_dst(stage1_query, dst_value)
    stage2_addr = backend.collect_capture(f"{cfg.capture_label}-stage2-addrdst", addr_query)
    result["queries"]["stage2_addr_dst"] = addr_query
    result["capture_dirs"]["stage2_addr_dst"] = str(stage2_addr.capture_dir)

    addr_match, _ = pick_freshest_match(stage2_addr.entries, cfg.signature)
    if addr_match and _matches(addr_match.get("dst"), dst_value):
        result["addr_dst_validated"] = True
        result["validated_tokens"].append("addr.dst")

    dport_value_str = best.get("dport") or (str(cfg.destination_port) if cfg.destination_port is not None else "")
    if dport_value_str.isdigit():
        dport_value = int(dport_value_str)
        dport_query = extend_query_dport(stage1_query, dport_value)
        stage2_dport = backend.collect_capture(f"{cfg.capture_label}-stage2-dport", dport_query)
        result["queries"]["stage2_dport"] = dport_query
        result["capture_dirs"]["stage2_dport"] = str(stage2_dport.capture_dir)
        dport_match, _ = pick_freshest_match(stage2_dport.entries, cfg.signature)
        if dport_match and _matches(dport_match.get("dport"), str(dport_value)):
            result["dport_validated"] = True
            result["validated_tokens"].append("dport")

    if not result["validated_tokens"]:
        result["reason_if_not_validated"] = "token_subqueries_did_not_match"

    write_result_json(stage1.capture_dir / "VALIDATION_RESULT.json", result)
    return result, 0


def parse_args(argv: list[str]) -> RunConfig:
    parser = argparse.ArgumentParser(description="Bounded PAN-OS observe-and-validate orchestrator")
    parser.add_argument("--host", required=True)
    parser.add_argument("--rule-xpath", required=True)
    parser.add_argument("--capture-label", required=True)
    parser.add_argument("--out-root", default="docs/fixtures/panos_verification")
    parser.add_argument("--max-polls", type=int, default=10)
    parser.add_argument("--poll-interval", type=int, default=1)
    parser.add_argument("--lookback-minutes", type=int, default=15)

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

    parser.add_argument("--api-key")
    parser.add_argument("--username")
    parser.add_argument("--password")

    args = parser.parse_args(argv)

    if not args.api_key and (not args.username or not args.password):
        parser.error("Provide --api-key, or both --username and --password")

    traffic_command = args.traffic_command
    if not traffic_command:
        if args.destination_port is None:
            parser.error("--destination-port is required when --traffic-command is not provided")
        traffic_command = build_udp_traffic_command(
            dst=args.destination_ip,
            dport=args.destination_port,
            duration_seconds=args.traffic_duration,
            interval_seconds=args.traffic_interval,
        )

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
        destination_ip=args.destination_ip,
        destination_port=args.destination_port,
        signature=signature,
        api_key=args.api_key,
        username=args.username,
        password=args.password,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv or sys.argv[1:])
    backend = LocalBackend(cfg)
    result, code = orchestrate(cfg, backend)
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
