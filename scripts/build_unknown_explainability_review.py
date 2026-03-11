"""Build a compact operator review pack for unknown explainability wording.

This script extracts persisted unknown-result row samples from route tests and
generates review artifacts for structured operator feedback collection.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from am_i_blocked_api.routes.api import _coerce_confidence, _derive_unknown_reason_signals

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = ROOT / "tests" / "routes" / "test_api_routes.py"
OUTPUT_JSON = ROOT / "docs" / "review" / "UNKNOWN_EXPLAINABILITY_SAMPLES.json"
OUTPUT_MD = ROOT / "docs" / "review" / "UNKNOWN_EXPLAINABILITY_REVIEW.md"


def _literal_eval(node: ast.AST) -> Any | None:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _classify_dominant_cause(reasons: list[str]) -> str:
    categories: set[str] = set()
    lowered_reasons = [reason.lower() for reason in reasons]

    if any("authoritative deny evidence" in reason for reason in lowered_reasons):
        categories.add("authoritative-evidence gap")
    if any("data sources were degraded or unavailable" in reason for reason in lowered_reasons):
        categories.add("degraded source readiness")
    if any("path context confidence is low" in reason for reason in lowered_reasons):
        categories.add("low path confidence")
    if any("bounded checks were inconclusive" in reason for reason in lowered_reasons):
        categories.add("inconclusive bounded checks")

    if len(categories) == 1:
        return next(iter(categories))
    if len(categories) > 1:
        return "mixed causes"
    return "mixed causes"


def _render_operator_explanation(
    path_confidence: float,
    evidence_completeness: float,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "section_title": "Why this is unknown",
        "safety_note": "Unknown is not the same as allowed. A missing deny signal is not proof of allow.",
        "confidence_line": (
            f"Path confidence: {int(path_confidence * 100)}% | "
            f"Evidence completeness: {int(evidence_completeness * 100)}%"
        ),
        "reason_bullets": reasons
        or ["No additional confidence-reducing signals were recorded for this unknown result."],
    }


def _scenario_label(function_name: str) -> str:
    labels = {
        "test_load_result_record_unknown_derives_reasons_from_confidence_and_readiness": (
            "Unknown with low confidence and explicit readiness degradation"
        ),
        "test_load_result_record_unknown_handles_missing_or_malformed_confidence_values": (
            "Unknown with malformed persisted confidence values and explicit custom reason"
        ),
        "test_load_result_record_handles_partial_or_malformed_readiness_entries": (
            "Unknown with mixed readiness entry quality and incomplete evidence context"
        ),
    }
    return labels.get(function_name, function_name.replace("_", " "))


def _extract_unknown_result_rows() -> list[dict[str, Any]]:
    tree = ast.parse(SOURCE_FILE.read_text(encoding="utf-8"))
    samples: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            func = call.func
            if not (isinstance(func, ast.Attribute) and func.attr == "ResultRow"):
                continue

            kwargs: dict[str, Any] = {}
            for keyword in call.keywords:
                if keyword.arg is None:
                    continue
                kwargs[keyword.arg] = _literal_eval(keyword.value)

            if kwargs.get("verdict") != "unknown":
                continue
            report = kwargs.get("report_json")
            if not isinstance(report, dict):
                continue

            path_confidence = _coerce_confidence(report.get("path_confidence"))
            evidence_completeness = _coerce_confidence(kwargs.get("evidence_completeness"))
            persisted_signals = report.get("unknown_reason_signals")
            reason_signals: list[str]
            if isinstance(persisted_signals, list) and all(
                isinstance(item, str) for item in persisted_signals
            ):
                reason_signals = [item for item in persisted_signals if item.strip()]
            else:
                reason_signals = _derive_unknown_reason_signals(
                    report=report,
                    path_confidence=path_confidence,
                    evidence_completeness=evidence_completeness,
                )

            samples.append(
                {
                    "sample_id": f"sample_{len(samples) + 1}",
                    "source_reference": f"{SOURCE_FILE.relative_to(ROOT)}:{call.lineno}",
                    "source_test": node.name,
                    "scenario_label": _scenario_label(node.name),
                    "verdict": "unknown",
                    "summary": kwargs.get("summary"),
                    "path_confidence": path_confidence,
                    "evidence_completeness": evidence_completeness,
                    "result_confidence": _coerce_confidence(kwargs.get("result_confidence")),
                    "source_readiness": report.get("source_readiness"),
                    "unknown_reason_signals": reason_signals,
                    "operator_explanation": _render_operator_explanation(
                        path_confidence=path_confidence,
                        evidence_completeness=evidence_completeness,
                        reasons=reason_signals,
                    ),
                    "dominant_cause": _classify_dominant_cause(reason_signals),
                    "sample_provenance": "real persisted unknown-result row fixture from tests",
                }
            )

    return samples


def _render_markdown(samples: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Unknown Explainability Review Pack")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "Use this pack to collect operator feedback on unknown-confidence wording with concrete persisted unknown-result examples."
    )
    lines.append("")
    lines.append("Scope guardrails for this review:")
    lines.append("- Explainability wording interpretation only.")
    lines.append("- No verdict/classifier/readiness authority changes.")
    lines.append("- Unknown is not equivalent to allowed.")
    lines.append("")
    lines.append("## Sample Sources")
    lines.append(
        f"- Source file scanned: `{SOURCE_FILE.relative_to(ROOT)}` (`api_routes.ResultRow` fixtures with `verdict=\"unknown\"`)."
    )
    lines.append("- Sample type: persisted `result.report_json` row fixtures in route tests.")
    lines.append("- Synthetic fallback samples: none.")
    lines.append("")
    lines.append("## Review Rubric")
    lines.append("For each sample, score each item 1-5 and add notes:")
    lines.append("- Is the dominant cause understandable?")
    lines.append("- Is the wording actionable for first-hop triage?")
    lines.append("- Does wording avoid implying `allowed`?")
    lines.append("- Is wording too technical or too vague?")
    lines.append("")
    lines.append("## Samples")
    for sample in samples:
        lines.append("")
        lines.append(f"### {sample['sample_id']}: {sample['scenario_label']}")
        lines.append(f"- Source: `{sample['source_reference']}` ({sample['source_test']})")
        lines.append(f"- Verdict: `{sample['verdict']}`")
        lines.append(f"- Summary: {sample.get('summary')}")
        lines.append(
            "- Confidence context:"
            f" path={int(sample['path_confidence'] * 100)}%,"
            f" evidence={int(sample['evidence_completeness'] * 100)}%,"
            f" result={int(sample['result_confidence'] * 100)}%"
        )
        lines.append(f"- Dominant cause classification: `{sample['dominant_cause']}`")
        lines.append("- Unknown reason signals:")
        for reason in sample["unknown_reason_signals"]:
            lines.append(f"  - {reason}")
        lines.append("- Operator-facing explanation text:")
        lines.append(f"  - Title: {sample['operator_explanation']['section_title']}")
        lines.append(f"  - Safety note: {sample['operator_explanation']['safety_note']}")
        lines.append(f"  - Confidence line: {sample['operator_explanation']['confidence_line']}")
    lines.append("")
    lines.append("## Per-Sample Feedback Template")
    lines.append(
        "| sample_id | dominant_cause_clear (1-5) | actionable (1-5) | avoids_implying_allowed (1-5) | too_technical_or_vague (1-5) | operator_notes |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---|"
    )
    for sample in samples:
        lines.append(
            f"| {sample['sample_id']} |  |  |  |  |  |"
        )
    lines.append("")
    lines.append("## Generation")
    lines.append(
        "- Generated by `scripts/build_unknown_explainability_review.py` from repo-owned persisted unknown-result fixtures."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    samples = _extract_unknown_result_rows()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({"samples": samples}, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(_render_markdown(samples), encoding="utf-8")
    print(f"Wrote {len(samples)} samples to {OUTPUT_JSON.relative_to(ROOT)}")
    print(f"Wrote review pack to {OUTPUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
