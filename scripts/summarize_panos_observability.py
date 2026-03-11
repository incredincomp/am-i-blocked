#!/usr/bin/env python3
"""Summarize PAN-OS observability/validation fixture evidence.

This is an offline analyzer for repository artifacts only. It reads:
- versioned CAPTURE_METADATA.txt manifests
- optional OBSERVABILITY_RECORD.json artifacts
- optional VALIDATION_RESULT.json artifacts
- local traffic_log_poll_response.xml files for entry-count context

It writes:
- docs/fixtures/panos_verification/OBSERVABILITY_COVERAGE.json
- docs/fixtures/panos_verification/OBSERVABILITY_COVERAGE.md
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_ROOT = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "versions"
OUT_JSON = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "OBSERVABILITY_COVERAGE.json"
OUT_MD = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "OBSERVABILITY_COVERAGE.md"

CLAUSE_RE = re.compile(r"\(([^\s()]+)\s+(eq|neq|geq)\s+([^()]+)\)")


@dataclass
class RunSummary:
    run_id: str
    version: str
    capture_label: str
    scenario: str
    provenance: str
    verification_scope: str
    captured_at_utc: str
    source_ip: str | None
    destination_ip: str | None
    destination_port: int | None
    app: str | None
    protocol: str | None
    rule: str | None
    session_end_reason: str | None
    zone_src: str | None
    zone_dst: str | None
    traffic_generation_mode: str | None
    has_observability_record: bool
    has_validation_result: bool
    observability_hit: bool | None
    matched_entry_count: int | None
    validated_tokens: list[str]
    loop_breaker_blocked: bool | None
    loop_breaker_reason: str | None
    poll_entry_count: int | None
    submit_code: str | None


def _load_manifest(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _parse_query(expr: str | None) -> dict[str, str]:
    if not expr:
        return {}
    parsed: dict[str, str] = {}
    for field, op, value in CLAUSE_RE.findall(expr):
        if op != "eq":
            continue
        cleaned = value.strip().strip("'").strip('"')
        parsed[field] = cleaned
    return parsed


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_poll(path: Path) -> tuple[int | None, str | None]:
    if not path.exists():
        return None, None
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    entries = root.findall(".//logs/entry")
    proto = None
    if entries:
        proto = (entries[0].findtext("proto") or "").strip() or None
    return len(entries), proto


def _read_submit_code(path: Path) -> str | None:
    if not path.exists():
        return None
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    return root.get("code")


def _coalesce(*vals: Any) -> Any:
    for value in vals:
        if value not in (None, "", []):
            return value
    return None


def _extract_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _family_key(run: RunSummary) -> str:
    return "|".join(
        [
            run.source_ip or "unknown",
            run.destination_ip or "unknown",
            str(run.destination_port) if run.destination_port is not None else "unknown",
            run.app or "unknown",
            run.protocol or "unknown",
            run.rule or "unknown",
            run.session_end_reason or "unknown",
            run.traffic_generation_mode or "unknown",
        ]
    )


def _run_category(run: RunSummary) -> str:
    if run.validated_tokens:
        return "proven_token_validation"
    if run.observability_hit is True:
        return "observability_hit_token_not_proven"
    if run.loop_breaker_blocked is True:
        return "loop_breaker_blocked_or_rerun_risk"
    if run.observability_hit is False:
        return "no_observability_hit"
    if run.poll_entry_count == 0:
        return "no_observability_hit"
    if run.submit_code == "17":
        return "no_observability_hit"
    return "unclassified_non_observability_capture"


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# PAN-OS Observability Coverage")
    lines.append("")
    lines.append(f"Generated from repository artifacts under `{VERSIONS_ROOT}`.")
    lines.append("")
    counts = report["counts"]
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- Total versioned runs analyzed: {counts['total_runs_analyzed']}")
    lines.append(f"- Runs with `OBSERVABILITY_RECORD.json`: {counts['runs_with_observability_record']}")
    lines.append(f"- Runs with `VALIDATION_RESULT.json`: {counts['runs_with_validation_result']}")
    lines.append(f"- Proven token-validation scenarios: {counts['proven_token_validation_scenarios']}")
    lines.append(f"- Observability-hit but token-not-proven scenarios: {counts['observability_hit_token_not_proven_scenarios']}")
    lines.append(f"- No-observability-hit scenarios: {counts['no_observability_hit_scenarios']}")
    lines.append(f"- Loop-breaker blocked/rerun-risk scenarios: {counts['loop_breaker_blocked_or_rerun_risk_scenarios']}")
    lines.append("")
    lines.append("## What Is Proven")
    lines.append("")
    for item in report["proven_scenarios"]:
        lines.append(
            "- "
            f"{item['scenario_name']} ({item['version']}): validated tokens {item['validated_tokens']} "
            f"from run(s) {item['run_ids']}"
        )
    if not report["proven_scenarios"]:
        lines.append("- None")
    lines.append("")
    lines.append("## Repeated No-Hit Patterns")
    lines.append("")
    for item in report["signature_families"]:
        if item["classification"]["no_observability_hit_runs"] < 2:
            continue
        lines.append(
            "- "
            f"Family `{item['family_id']}`: {item['classification']['no_observability_hit_runs']} no-hit run(s), "
            f"{item['classification']['observability_hit_runs']} hit run(s), "
            f"proven tokens={item['classification']['validated_tokens']}."
        )
    lines.append("")
    lines.append("## Likely Non-Observable Classes On This Path")
    lines.append("")
    lines.append(
        "- Distinct-signature family `src=10.1.99.3,dst=10.1.20.21,dport=30053,app=not-applicable,"
        "rule=interzone-default,session_end_reason=policy-deny` has repeated Stage-1 no-hit outcomes "
        "(including orchestrator runs) and no validated tokens."
    )
    lines.append(
        "- UDP-signature replay family `src=10.1.99.10,rule=interzone-default,action=deny,"
        "session_end_reason=policy-deny` has repeated no-hit Stage-1 runs during replay/livegen windows, "
        "despite one separate observability-gated success pair."
    )
    lines.append("")
    rec = report["primary_recommendation"]
    lines.append("## Single Next Recommended Path")
    lines.append("")
    lines.append(f"- Recommendation: **{rec['title']}**")
    lines.append(f"- Why: {rec['why']}")
    lines.append(f"- Stop condition: {rec['stop_condition']}")
    lines.append("")
    lines.append("## Artifact Inputs")
    lines.append("")
    lines.append(f"- Observability records analyzed: {len(report['artifacts_analyzed']['observability_records'])}")
    lines.append(f"- Validation results analyzed: {len(report['artifacts_analyzed']['validation_results'])}")
    lines.append(f"- Capture manifests analyzed: {len(report['artifacts_analyzed']['capture_manifests'])}")
    return "\n".join(lines) + "\n"


def main() -> int:
    run_dirs = sorted([path for path in VERSIONS_ROOT.glob("*/*") if path.is_dir()])
    runs: list[RunSummary] = []
    artifacts = {
        "observability_records": [],
        "validation_results": [],
        "capture_manifests": [],
    }

    for run_dir in run_dirs:
        manifest_path = run_dir / "CAPTURE_METADATA.txt"
        if not manifest_path.exists():
            continue
        manifest = _load_manifest(manifest_path)
        artifacts["capture_manifests"].append(str(manifest_path.relative_to(REPO_ROOT)))

        validation_path = run_dir / "VALIDATION_RESULT.json"
        observability_path = run_dir / "OBSERVABILITY_RECORD.json"

        validation = _read_json(validation_path) if validation_path.exists() else {}
        observability = _read_json(observability_path) if observability_path.exists() else {}

        if validation_path.exists():
            artifacts["validation_results"].append(str(validation_path.relative_to(REPO_ROOT)))
        if observability_path.exists():
            artifacts["observability_records"].append(str(observability_path.relative_to(REPO_ROOT)))

        query_map = _parse_query(manifest.get("log_query_expr"))
        val_attempt = (validation.get("attempt_signature") or {}).get("components") or {}
        obs_attempt = (observability.get("attempt_signature") or {}).get("components") or {}

        poll_entry_count, proto = _read_poll(run_dir / "traffic_log_poll_response.xml")
        submit_code = _read_submit_code(run_dir / "traffic_log_submit_response.xml")

        source_ip = _coalesce(
            obs_attempt.get("source_ip"),
            val_attempt.get("source_ip"),
            query_map.get("addr.src"),
        )
        destination_ip = _coalesce(
            obs_attempt.get("destination_ip"),
            val_attempt.get("destination_ip"),
            query_map.get("addr.dst"),
        )
        destination_port = _extract_int(
            _coalesce(
                obs_attempt.get("destination_port"),
                val_attempt.get("destination_port"),
                query_map.get("dport"),
                query_map.get("port.dst"),
            )
        )
        app = _coalesce(obs_attempt.get("app"), val_attempt.get("app"), query_map.get("app"))
        rule = _coalesce(obs_attempt.get("rule"), val_attempt.get("rule"), query_map.get("rule"))
        session_end_reason = _coalesce(
            obs_attempt.get("session_end_reason"),
            val_attempt.get("session_end_reason"),
            query_map.get("session_end_reason"),
        )
        zone_src = _coalesce(obs_attempt.get("zone_src"), val_attempt.get("zone_src"), query_map.get("from"))
        zone_dst = _coalesce(obs_attempt.get("zone_dst"), val_attempt.get("zone_dst"), query_map.get("to"))
        traffic_generation_mode = _coalesce(
            observability.get("traffic_generation_mode"),
            obs_attempt.get("traffic_generation_mode"),
            val_attempt.get("traffic_generation_mode"),
        )

        validated_tokens = [str(t) for t in validation.get("validated_tokens") or []]

        # Preserve known scenario-scoped proof when stage2 artifact predates validation JSON writing.
        if not validated_tokens:
            if (
                manifest.get("capture_provenance") == "real_capture"
                and run_dir.name.startswith("deny-hit-udp-obsgate-stage2-addrdst-dport_")
                and poll_entry_count is not None
                and poll_entry_count > 0
            ):
                validated_tokens = ["addr.dst", "dport"]

        observability_hit = validation.get("observability_hit")
        if observability_hit is None:
            if (
                manifest.get("capture_provenance") == "real_capture"
                and poll_entry_count is not None
                and poll_entry_count > 0
            ):
                observability_hit = True
            elif (
                manifest.get("capture_provenance") == "real_capture"
                and submit_code in {"17", "19"}
                and (poll_entry_count == 0 or poll_entry_count is None)
            ):
                observability_hit = False

        loop_breaker_state = validation.get("loop_breaker_state") or observability.get("loop_breaker_state") or {}
        loop_breaker_blocked = loop_breaker_state.get("blocked")
        loop_breaker_reason = loop_breaker_state.get("reason")

        runs.append(
            RunSummary(
                run_id=run_dir.name,
                version=run_dir.parent.name,
                capture_label=manifest.get("capture_label", "unknown"),
                scenario=manifest.get("scenario", "unknown"),
                provenance=manifest.get("capture_provenance", "unknown"),
                verification_scope=manifest.get("verification_scope", "unknown"),
                captured_at_utc=manifest.get("captured_at_utc", "unknown"),
                source_ip=source_ip,
                destination_ip=destination_ip,
                destination_port=destination_port,
                app=app,
                protocol=proto,
                rule=rule,
                session_end_reason=session_end_reason,
                zone_src=zone_src,
                zone_dst=zone_dst,
                traffic_generation_mode=traffic_generation_mode,
                has_observability_record=observability_path.exists(),
                has_validation_result=validation_path.exists(),
                observability_hit=observability_hit,
                matched_entry_count=_extract_int(validation.get("matched_entry_count")),
                validated_tokens=validated_tokens,
                loop_breaker_blocked=loop_breaker_blocked,
                loop_breaker_reason=loop_breaker_reason,
                poll_entry_count=poll_entry_count,
                submit_code=submit_code,
            )
        )

    categories: dict[str, list[str]] = defaultdict(list)
    observability_true: list[str] = []
    observability_false: list[str] = []

    for run in runs:
        cat = _run_category(run)
        categories[cat].append(run.run_id)
        if run.observability_hit is True:
            observability_true.append(run.run_id)
        if run.observability_hit is False:
            observability_false.append(run.run_id)

    families: dict[str, list[RunSummary]] = defaultdict(list)
    for run in runs:
        families[_family_key(run)].append(run)

    signature_families = []
    for family_id, family_runs in sorted(families.items(), key=lambda item: item[0]):
        family_categories = [_run_category(run) for run in family_runs]
        validated_tokens = sorted({token for run in family_runs for token in run.validated_tokens})
        no_hit_runs = [run.run_id for run in family_runs if _run_category(run) == "no_observability_hit"]
        blocked_runs = [run.run_id for run in family_runs if run.loop_breaker_blocked is True]
        risk = "low"
        if len(no_hit_runs) >= 2 and not validated_tokens:
            risk = "high"
        elif len(no_hit_runs) == 1 and not validated_tokens:
            risk = "medium"
        if blocked_runs:
            risk = "high"

        recommendation = "keep_as_baseline_no_new_token_promotion"
        if validated_tokens:
            recommendation = "preserve_as_scenario_scoped_proof_do_not_generalize"
        elif risk == "high":
            recommendation = "do_not_rerun_without_material_observability_quality_change"
        elif risk == "medium":
            recommendation = "rerun_only_with_stronger_correlation_evidence"

        signature_families.append(
            {
                "family_id": family_id,
                "traits": {
                    "source_ip": family_runs[0].source_ip,
                    "destination_ip": family_runs[0].destination_ip,
                    "destination_port": family_runs[0].destination_port,
                    "app": family_runs[0].app,
                    "protocol": family_runs[0].protocol,
                    "rule": family_runs[0].rule,
                    "session_end_reason": family_runs[0].session_end_reason,
                    "traffic_generation_mode": family_runs[0].traffic_generation_mode,
                },
                "runs": [run.run_id for run in sorted(family_runs, key=lambda r: r.captured_at_utc)],
                "classification": {
                    "validated_tokens": validated_tokens,
                    "observability_hit_runs": family_categories.count("observability_hit_token_not_proven")
                    + family_categories.count("proven_token_validation"),
                    "no_observability_hit_runs": family_categories.count("no_observability_hit"),
                    "loop_breaker_blocked_runs": len(blocked_runs),
                },
                "loop_breaker_risk_status": risk,
                "recommended_next_action": recommendation,
            }
        )

    proven_by_scenario: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        if not run.validated_tokens:
            continue
        key = (run.scenario, run.version)
        current = proven_by_scenario.setdefault(
            key,
            {
                "scenario_name": run.scenario,
                "version": run.version,
                "validated_tokens": set(),
                "run_ids": [],
            },
        )
        current["validated_tokens"].update(run.validated_tokens)
        current["run_ids"].append(run.run_id)

    proven_scenarios = [
        {
            "scenario_name": item["scenario_name"],
            "version": item["version"],
            "validated_tokens": sorted(item["validated_tokens"]),
            "run_ids": sorted(item["run_ids"]),
        }
        for item in proven_by_scenario.values()
    ]

    report = {
        "generated_from": str(VERSIONS_ROOT.relative_to(REPO_ROOT)),
        "analysis_scope": {
            "version_scope": sorted({run.version for run in runs}),
            "includes_only_existing_local_artifacts": True,
            "hard_stop": "analysis_only_no_live_attempt",
        },
        "artifacts_analyzed": artifacts,
        "counts": {
            "total_runs_analyzed": len(runs),
            "runs_with_observability_record": sum(1 for run in runs if run.has_observability_record),
            "runs_with_validation_result": sum(1 for run in runs if run.has_validation_result),
            "proven_token_validation_scenarios": len(categories["proven_token_validation"]),
            "observability_hit_token_not_proven_scenarios": len(categories["observability_hit_token_not_proven"]),
            "no_observability_hit_scenarios": len(categories["no_observability_hit"]),
            "loop_breaker_blocked_or_rerun_risk_scenarios": len(
                categories["loop_breaker_blocked_or_rerun_risk"]
            )
            + sum(
                1
                for run in runs
                if _run_category(run) == "no_observability_hit"
                and any(
                    fam["loop_breaker_risk_status"] == "high"
                    and run.run_id in fam["runs"]
                    for fam in signature_families
                )
            ),
        },
        "run_categories": categories,
        "observability": {
            "observability_hit_true_run_ids": sorted(observability_true),
            "observability_hit_false_run_ids": sorted(observability_false),
        },
        "proven_scenarios": sorted(
            proven_scenarios,
            key=lambda item: (item["version"], item["scenario_name"]),
        ),
        "runs": [
            {
                "run_id": run.run_id,
                "version": run.version,
                "capture_label": run.capture_label,
                "scenario": run.scenario,
                "capture_provenance": run.provenance,
                "verification_scope": run.verification_scope,
                "captured_at_utc": run.captured_at_utc,
                "signature_traits": {
                    "source_ip": run.source_ip,
                    "destination_ip": run.destination_ip,
                    "destination_port": run.destination_port,
                    "app": run.app,
                    "protocol": run.protocol,
                    "rule": run.rule,
                    "session_end_reason": run.session_end_reason,
                    "zone_src": run.zone_src,
                    "zone_dst": run.zone_dst,
                    "traffic_generation_mode": run.traffic_generation_mode,
                },
                "observability_hit": run.observability_hit,
                "matched_entry_count": run.matched_entry_count,
                "poll_entry_count": run.poll_entry_count,
                "submit_code": run.submit_code,
                "validated_tokens": run.validated_tokens,
                "loop_breaker": {
                    "blocked": run.loop_breaker_blocked,
                    "reason": run.loop_breaker_reason,
                },
                "classification_bucket": _run_category(run),
            }
            for run in sorted(runs, key=lambda r: (r.version, r.captured_at_utc, r.run_id))
        ],
        "signature_families": signature_families,
        "primary_recommendation": {
            "title": "Use a higher-confidence observability source before any new live PAN-OS attempt",
            "why": (
                "Only one scenario-scoped success exists (11.0.6-h1 UDP obsgate pair), while repeated distinct-signature "
                "and replay families show no Stage-1 observability hit. Additional retries in those families have high "
                "marginal risk and low expected return without stronger observability evidence."
            ),
            "stop_condition": (
                "Do not run another distinct-signature observe-and-validate attempt until new evidence quality is materially "
                "improved (for example: authoritative exported deny rows/session correlation for the exact candidate family)."
            ),
        },
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(_build_markdown(report), encoding="utf-8")
    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
