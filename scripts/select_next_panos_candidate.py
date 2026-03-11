#!/usr/bin/env python3
"""Select the next PAN-OS candidate family from existing evidence.

This is an offline decision helper. It does not perform live calls.
Inputs:
- OBSERVABILITY_COVERAGE.json
- existing OBSERVABILITY_RECORD.json / VALIDATION_RESULT.json artifacts
Outputs:
- NEXT_CANDIDATE_DECISION.json
- NEXT_CANDIDATE_DECISION.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "OBSERVABILITY_COVERAGE.json"
DEFAULT_VERSIONS_ROOT = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "versions"
DEFAULT_OUT_JSON = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "NEXT_CANDIDATE_DECISION.json"
DEFAULT_OUT_MD = REPO_ROOT / "docs" / "fixtures" / "panos_verification" / "NEXT_CANDIDATE_DECISION.md"


@dataclass
class FamilyDecision:
    family_id: str
    status: str
    reasons: list[str]
    traits: dict[str, Any]
    metrics: dict[str, Any]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_known(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "null"}


def _build_run_to_family(coverage: dict[str, Any]) -> dict[str, str]:
    run_to_family: dict[str, str] = {}
    for fam in coverage.get("signature_families", []):
        family_id = fam.get("family_id")
        for run_id in fam.get("runs", []):
            run_to_family[str(run_id)] = str(family_id)
    return run_to_family


def _load_record_maps(versions_root: Path, run_to_family: dict[str, str]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    obs_by_family: dict[str, list[dict[str, Any]]] = {}
    val_by_family: dict[str, list[dict[str, Any]]] = {}

    for path in versions_root.glob("**/OBSERVABILITY_RECORD.json"):
        data = _load_json(path)
        run_id = path.parent.name
        family_id = run_to_family.get(run_id)
        if family_id is None:
            continue
        obs_by_family.setdefault(family_id, []).append(data)

    for path in versions_root.glob("**/VALIDATION_RESULT.json"):
        data = _load_json(path)
        run_id = path.parent.name
        family_id = run_to_family.get(run_id)
        if family_id is None:
            continue
        val_by_family.setdefault(family_id, []).append(data)

    return obs_by_family, val_by_family


def _has_high_conf_no_hit(obs_records: list[dict[str, Any]]) -> bool:
    for row in obs_records:
        if row.get("observability_hit") is not False:
            continue
        obs_input = row.get("observability_input") or {}
        ready = bool(obs_input.get("ready_for_orchestrator"))
        conf = str(obs_input.get("correlation_confidence") or row.get("correlation_confidence") or "").lower()
        score = int((row.get("loop_breaker_state") or {}).get("current_correlation_score") or 0)
        if (ready and conf in {"high", "medium"}) or conf == "high" or score >= 8:
            return True
    return False


def _has_loop_breaker_block(obs_records: list[dict[str, Any]], family_metrics: dict[str, Any]) -> bool:
    if int(family_metrics.get("loop_breaker_blocked_runs") or 0) > 0:
        return True
    return any(bool((row.get("loop_breaker_state") or {}).get("blocked")) for row in obs_records)


def classify_families(coverage: dict[str, Any], obs_by_family: dict[str, list[dict[str, Any]]]) -> list[FamilyDecision]:
    decisions: list[FamilyDecision] = []

    for fam in coverage.get("signature_families", []):
        family_id = str(fam.get("family_id"))
        traits = dict(fam.get("traits") or {})
        metrics = dict(fam.get("classification") or {})

        validated_tokens = metrics.get("validated_tokens") or []
        no_hit_runs = int(metrics.get("no_observability_hit_runs") or 0)
        obs_records = obs_by_family.get(family_id, [])

        reasons: list[str] = []
        status = "candidate"

        if validated_tokens:
            status = "proven"
            reasons.append("scenario_scoped_token_validation_exists")
        else:
            high_conf_no_hit = _has_high_conf_no_hit(obs_records)
            if no_hit_runs >= 2 and high_conf_no_hit:
                status = "exhausted_pending_new_evidence"
                reasons.append("repeated_no_hit_with_high_confidence_attempt")
            elif no_hit_runs >= 3:
                status = "exhausted_pending_new_evidence"
                reasons.append("repeated_no_hit_pattern")
            elif _has_loop_breaker_block(obs_records, metrics):
                status = "blocked_by_loop_breaker"
                reasons.append("loop_breaker_block_recorded")
            else:
                reasons.append("not_proven_and_not_exhausted")

        if status == "exhausted_pending_new_evidence" and _has_loop_breaker_block(obs_records, metrics):
            reasons.append("loop_breaker_block_recorded")

        if not _is_known(traits.get("destination_ip")):
            reasons.append("destination_ip_not_specific")
        if not _is_known(traits.get("destination_port")):
            reasons.append("destination_port_not_specific")
        if not _is_known(traits.get("source_ip")):
            reasons.append("source_ip_not_specific")

        decisions.append(
            FamilyDecision(
                family_id=family_id,
                status=status,
                reasons=reasons,
                traits=traits,
                metrics=metrics,
            )
        )

    return decisions


def _candidate_score(decision: FamilyDecision, proven_family_ids: set[str], exhausted_family_ids: set[str]) -> int:
    score = 0
    if _is_known(decision.traits.get("destination_ip")):
        score += 3
    if _is_known(decision.traits.get("destination_port")):
        score += 3
    if _is_known(decision.traits.get("source_ip")):
        score += 2
    if _is_known(decision.traits.get("app")):
        score += 1

    no_hits = int(decision.metrics.get("no_observability_hit_runs") or 0)
    if no_hits == 1:
        score -= 2

    # De-prioritize family variants that are too close to known proven/exhausted sets.
    if decision.family_id in proven_family_ids:
        score -= 100
    if decision.family_id in exhausted_family_ids:
        score -= 100

    return score


def choose_primary_recommendation(decisions: list[FamilyDecision]) -> dict[str, Any]:
    proven_ids = {d.family_id for d in decisions if d.status == "proven"}
    exhausted_ids = {d.family_id for d in decisions if d.status == "exhausted_pending_new_evidence"}

    viable: list[tuple[int, FamilyDecision]] = []
    for decision in decisions:
        if decision.status != "candidate":
            continue
        score = _candidate_score(decision, proven_ids, exhausted_ids)
        # Must be useful for addr.dst/dport-style validation targeting and
        # practical to correlate with OBSERVABILITY_INPUT in the next run.
        if not _is_known(decision.traits.get("source_ip")):
            continue
        if not _is_known(decision.traits.get("destination_ip")) or not _is_known(decision.traits.get("destination_port")):
            continue
        viable.append((score, decision))

    viable.sort(key=lambda item: item[0], reverse=True)

    if viable and viable[0][0] >= 5:
        top_score, top = viable[0]
        return {
            "action": "run_next_candidate_family",
            "family_id": top.family_id,
            "score": top_score,
            "why": "Highest-ranked non-exhausted family with specific destination+port token potential.",
        }

    return {
        "action": "pause_panos_token_expansion",
        "family_id": None,
        "score": None,
        "why": "No worthwhile non-exhausted candidate family with sufficient destination-token potential; avoid further no-hit loop retries.",
    }


def build_decision_payload(coverage: dict[str, Any], decisions: list[FamilyDecision], recommendation: dict[str, Any]) -> dict[str, Any]:
    exhausted = [d for d in decisions if d.status == "exhausted_pending_new_evidence"]
    return {
        "generated_at": _iso_now(),
        "inputs": {
            "coverage_generated_from": coverage.get("generated_from"),
            "total_runs_analyzed": coverage.get("counts", {}).get("total_runs_analyzed"),
        },
        "family_classifications": [
            {
                "family_id": d.family_id,
                "status": d.status,
                "reasons": d.reasons,
                "traits": d.traits,
                "metrics": d.metrics,
            }
            for d in decisions
        ],
        "exhausted_families": [
            {
                "family_id": d.family_id,
                "reasons": d.reasons,
                "metrics": d.metrics,
            }
            for d in exhausted
        ],
        "primary_recommendation": recommendation,
        "policy_notes": [
            "Future PAN-OS live attempts must come from selector output artifacts, not ad hoc signature retries.",
            "Families classified exhausted_pending_new_evidence require materially stronger/newer evidence before rerun.",
            "OBSERVABILITY_RECORD.json remains primary run-state source of truth.",
        ],
    }


def _markdown(decision: dict[str, Any], out_json: Path) -> str:
    lines: list[str] = []
    lines.append("# Next PAN-OS Candidate Decision")
    lines.append("")
    lines.append(f"Generated from `{out_json.name}` inputs.")
    lines.append("")
    lines.append("## Primary Recommendation")
    lines.append("")
    rec = decision["primary_recommendation"]
    lines.append(f"- Action: **{rec['action']}**")
    if rec.get("family_id"):
        lines.append(f"- Family: `{rec['family_id']}`")
    lines.append(f"- Why: {rec['why']}")
    lines.append("")
    lines.append("## Family Classifications")
    lines.append("")
    for row in decision["family_classifications"]:
        lines.append(f"- `{row['family_id']}` -> `{row['status']}`")
    lines.append("")
    lines.append("## Exhausted Families")
    lines.append("")
    exhausted = decision.get("exhausted_families") or []
    if not exhausted:
        lines.append("- None")
    else:
        for row in exhausted:
            lines.append(f"- `{row['family_id']}`: {', '.join(row['reasons'])}")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select next PAN-OS candidate family from existing evidence")
    parser.add_argument("--coverage", default=str(DEFAULT_COVERAGE))
    parser.add_argument("--versions-root", default=str(DEFAULT_VERSIONS_ROOT))
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    coverage_path = Path(args.coverage)
    versions_root = Path(args.versions_root)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)

    coverage = _load_json(coverage_path)
    run_to_family = _build_run_to_family(coverage)
    obs_by_family, _ = _load_record_maps(versions_root, run_to_family)

    decisions = classify_families(coverage, obs_by_family)
    recommendation = choose_primary_recommendation(decisions)
    payload = build_decision_payload(coverage, decisions, recommendation)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(_markdown(payload, out_json), encoding="utf-8")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
