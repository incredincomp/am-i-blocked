"""Record and summarize structured operator feedback for unknown explainability."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "docs" / "review" / "UNKNOWN_EXPLAINABILITY_SAMPLES.json"
FEEDBACK_JSON_PATH = ROOT / "docs" / "review" / "UNKNOWN_EXPLAINABILITY_FEEDBACK.json"
FEEDBACK_MD_PATH = ROOT / "docs" / "review" / "UNKNOWN_EXPLAINABILITY_FEEDBACK.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_samples(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ValueError("Samples file is malformed: expected top-level 'samples' list.")
    output: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        sample_id = sample.get("sample_id")
        if isinstance(sample_id, str) and sample_id.strip():
            output.append(sample)
    if not output:
        raise ValueError("Samples file contains no usable sample IDs.")
    return output


def _load_feedback(path: Path, samples: list[dict[str, Any]]) -> dict[str, Any]:
    sample_index = [
        {
            "sample_id": sample["sample_id"],
            "scenario_label": sample.get("scenario_label"),
            "source_reference": sample.get("source_reference"),
        }
        for sample in samples
    ]
    if not path.exists():
        return {
            "schema_version": 1,
            "source_samples_file": "docs/review/UNKNOWN_EXPLAINABILITY_SAMPLES.json",
            "sample_index": sample_index,
            "feedback_entries": [],
        }

    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Feedback file is malformed: expected JSON object.")
    entries = payload.get("feedback_entries")
    if not isinstance(entries, list):
        raise ValueError("Feedback file is malformed: expected 'feedback_entries' list.")
    payload["schema_version"] = 1
    payload["source_samples_file"] = "docs/review/UNKNOWN_EXPLAINABILITY_SAMPLES.json"
    payload["sample_index"] = sample_index
    return payload


def _coerce_score(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Score fields must be integers from 1 to 5.")
    score = int(value)
    if score < 1 or score > 5:
        raise ValueError("Score fields must be between 1 and 5.")
    return score


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    raise ValueError("Boolean fields must be true/false.")


def _normalize_entry(raw: dict[str, Any], valid_sample_ids: set[str]) -> dict[str, Any]:
    sample_id = raw.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise ValueError("Each feedback entry must include non-empty sample_id.")
    if sample_id not in valid_sample_ids:
        raise ValueError(f"Unknown sample_id '{sample_id}'.")

    reviewer = raw.get("reviewer")
    if reviewer is None:
        reviewer = "unknown"
    if not isinstance(reviewer, str):
        raise ValueError("reviewer must be a string.")
    reviewer = reviewer.strip() or "unknown"

    reviewed_at = raw.get("reviewed_at")
    if reviewed_at is None:
        reviewed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        raise ValueError("reviewed_at must be a non-empty string.")

    followup_priority = raw.get("followup_priority")
    if followup_priority is not None:
        if not isinstance(followup_priority, str):
            raise ValueError("followup_priority must be a string when provided.")
        followup_priority = followup_priority.strip().lower()
        if followup_priority not in {"low", "medium", "high"}:
            raise ValueError("followup_priority must be one of: low, medium, high.")

    def _norm_text(key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string when provided.")
        value = value.strip()
        return value or None

    return {
        "sample_id": sample_id,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "understandable_score": _coerce_score(raw.get("understandable_score")),
        "actionable_score": _coerce_score(raw.get("actionable_score")),
        "too_technical_score": _coerce_score(raw.get("too_technical_score")),
        "too_vague_score": _coerce_score(raw.get("too_vague_score")),
        "incorrectly_sounds_like_allowed": _coerce_bool(raw.get("incorrectly_sounds_like_allowed")),
        "dominant_issue": _norm_text("dominant_issue"),
        "freeform_note": _norm_text("freeform_note"),
        "copy_followup_candidate": _norm_text("copy_followup_candidate"),
        "followup_priority": followup_priority,
        "ready_for_copy_change": _coerce_bool(raw.get("ready_for_copy_change")),
    }


def _entries_from_input_file(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        entries = payload.get("feedback_entries")
        if isinstance(entries, list):
            return [item for item in entries if isinstance(item, dict)]
        if "sample_id" in payload:
            return [payload]
    raise ValueError("Input file must be a feedback entry object, a list of entries, or {feedback_entries:[...]}.")


def _build_entry_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.sample_id is None:
        return None
    return {
        "sample_id": args.sample_id,
        "reviewer": args.reviewer,
        "reviewed_at": args.reviewed_at,
        "understandable_score": args.understandable_score,
        "actionable_score": args.actionable_score,
        "too_technical_score": args.too_technical_score,
        "too_vague_score": args.too_vague_score,
        "incorrectly_sounds_like_allowed": args.incorrectly_sounds_like_allowed,
        "dominant_issue": args.dominant_issue,
        "freeform_note": args.freeform_note,
        "copy_followup_candidate": args.copy_followup_candidate,
        "followup_priority": args.followup_priority,
        "ready_for_copy_change": args.ready_for_copy_change,
    }


def _average(values: list[int | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _classify_sample_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "insufficient feedback"
    if any(entry.get("ready_for_copy_change") is True for entry in entries):
        return "copy-only follow-up likely needed"
    if any(entry.get("incorrectly_sounds_like_allowed") is True for entry in entries):
        return "copy-only follow-up likely needed"
    if any(entry.get("followup_priority") in {"high", "medium"} for entry in entries):
        return "copy-only follow-up likely needed"
    if any(entry.get("copy_followup_candidate") for entry in entries):
        return "copy-only follow-up likely needed"
    return "no change needed yet"


def _render_summary_markdown(samples: list[dict[str, Any]], entries: list[dict[str, Any]]) -> str:
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        sample_id = entry.get("sample_id")
        if isinstance(sample_id, str):
            by_sample.setdefault(sample_id, []).append(entry)

    copy_needed: list[str] = []
    no_change: list[str] = []
    insufficient: list[str] = []
    lines: list[str] = []
    lines.append("# Unknown Explainability Feedback Summary")
    lines.append("")
    lines.append("## Purpose")
    lines.append("Structured operator feedback ledger for unknown-result explainability copy follow-up prioritization.")
    lines.append("")
    lines.append("## Recording Feedback")
    lines.append("- Single entry example:")
    lines.append(
        "  - `uv run python scripts/record_unknown_explainability_feedback.py --sample-id sample_1 --reviewer alice --understandable-score 4 --actionable-score 3 --too-technical-score 2 --too-vague-score 2 --incorrectly-sounds-like-allowed false --copy-followup-candidate \"Clarify source-readiness wording\" --followup-priority medium --ready-for-copy-change true --write-summary`"
    )
    lines.append("- Batch file example:")
    lines.append(
        "  - `uv run python scripts/record_unknown_explainability_feedback.py --input-json /path/to/feedback.json --write-summary`"
    )
    lines.append("- Partial entries are allowed; unknown sample IDs fail closed.")
    lines.append("")
    lines.append("## Totals")
    lines.append(f"- Total feedback entries: {len(entries)}")
    lines.append(f"- Samples tracked: {len(samples)}")
    lines.append("")
    lines.append("## Per-Sample Summary")

    for sample in samples:
        sample_id = sample["sample_id"]
        sample_entries = by_sample.get(sample_id, [])
        status = _classify_sample_status(sample_entries)
        if status == "copy-only follow-up likely needed":
            copy_needed.append(sample_id)
        elif status == "no change needed yet":
            no_change.append(sample_id)
        else:
            insufficient.append(sample_id)

        lines.append("")
        lines.append(f"### {sample_id}: {sample.get('scenario_label', '')}")
        lines.append(f"- Source: `{sample.get('source_reference', '')}`")
        lines.append(f"- Status: **{status}**")
        lines.append(f"- Feedback count: {len(sample_entries)}")

        understandable_avg = _average([entry.get("understandable_score") for entry in sample_entries])
        actionable_avg = _average([entry.get("actionable_score") for entry in sample_entries])
        technical_avg = _average([entry.get("too_technical_score") for entry in sample_entries])
        vague_avg = _average([entry.get("too_vague_score") for entry in sample_entries])

        if understandable_avg is not None:
            lines.append(f"- Avg understandable score: {understandable_avg:.2f}")
        if actionable_avg is not None:
            lines.append(f"- Avg actionable score: {actionable_avg:.2f}")
        if technical_avg is not None:
            lines.append(f"- Avg too-technical score: {technical_avg:.2f}")
        if vague_avg is not None:
            lines.append(f"- Avg too-vague score: {vague_avg:.2f}")

        sounds_allowed_true = sum(
            1 for entry in sample_entries if entry.get("incorrectly_sounds_like_allowed") is True
        )
        if sample_entries:
            lines.append(
                f"- incorrectly_sounds_like_allowed: {sounds_allowed_true}/{len(sample_entries)} marked true"
            )

        candidates = [
            entry.get("copy_followup_candidate")
            for entry in sample_entries
            if isinstance(entry.get("copy_followup_candidate"), str) and entry.get("copy_followup_candidate")
        ]
        if candidates:
            lines.append("- Copy follow-up candidates:")
            for candidate in candidates:
                lines.append(f"  - {candidate}")

    lines.append("")
    lines.append("## Priority Buckets")
    lines.append("- Copy-only follow-up likely needed:")
    for sample_id in copy_needed:
        lines.append(f"  - {sample_id}")
    lines.append("- No change needed yet:")
    for sample_id in no_change:
        lines.append(f"  - {sample_id}")
    lines.append("- Insufficient feedback:")
    for sample_id in insufficient:
        lines.append(f"  - {sample_id}")
    lines.append("")
    lines.append("## Artifact Notes")
    lines.append("- This summary is generated from `UNKNOWN_EXPLAINABILITY_FEEDBACK.json` and `UNKNOWN_EXPLAINABILITY_SAMPLES.json`.")
    lines.append("- Workflow scope is copy-follow-up triage only; no runtime verdict/classifier/readiness semantics are changed.")
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record and summarize unknown explainability feedback."
    )
    parser.add_argument("--samples-file", default=str(SAMPLES_PATH))
    parser.add_argument("--feedback-file", default=str(FEEDBACK_JSON_PATH))
    parser.add_argument("--summary-file", default=str(FEEDBACK_MD_PATH))
    parser.add_argument("--input-json", help="Path to JSON feedback entry/entries to merge.")
    parser.add_argument("--sample-id")
    parser.add_argument("--reviewer")
    parser.add_argument("--reviewed-at")
    parser.add_argument("--understandable-score", type=int)
    parser.add_argument("--actionable-score", type=int)
    parser.add_argument("--too-technical-score", type=int)
    parser.add_argument("--too-vague-score", type=int)
    parser.add_argument("--incorrectly-sounds-like-allowed")
    parser.add_argument("--dominant-issue")
    parser.add_argument("--freeform-note")
    parser.add_argument("--copy-followup-candidate")
    parser.add_argument("--followup-priority")
    parser.add_argument("--ready-for-copy-change")
    parser.add_argument("--write-summary", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    samples_path = Path(args.samples_file)
    feedback_path = Path(args.feedback_file)
    summary_path = Path(args.summary_file)

    samples = _load_samples(samples_path)
    valid_sample_ids = {sample["sample_id"] for sample in samples}
    feedback_payload = _load_feedback(feedback_path, samples)
    existing_entries = feedback_payload.get("feedback_entries", [])
    if not isinstance(existing_entries, list):
        raise ValueError("Feedback payload contains non-list feedback_entries.")

    pending_entries: list[dict[str, Any]] = []
    if args.input_json:
        pending_entries.extend(_entries_from_input_file(Path(args.input_json)))

    arg_entry = _build_entry_from_args(args)
    if arg_entry is not None:
        pending_entries.append(arg_entry)

    for pending in pending_entries:
        normalized = _normalize_entry(pending, valid_sample_ids)
        existing_entries.append(normalized)

    feedback_payload["feedback_entries"] = existing_entries
    feedback_payload["sample_index"] = [
        {
            "sample_id": sample["sample_id"],
            "scenario_label": sample.get("scenario_label"),
            "source_reference": sample.get("source_reference"),
        }
        for sample in samples
    ]

    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(json.dumps(feedback_payload, indent=2) + "\n", encoding="utf-8")

    if args.write_summary:
        summary_text = _render_summary_markdown(samples, existing_entries)
        summary_path.write_text(summary_text, encoding="utf-8")

    print(f"Wrote feedback JSON: {feedback_path.relative_to(ROOT)}")
    if args.write_summary:
        print(f"Wrote feedback summary: {summary_path.relative_to(ROOT)}")
    if pending_entries:
        print(f"Merged {len(pending_entries)} feedback entr{'y' if len(pending_entries) == 1 else 'ies'}.")
    else:
        print("No new feedback entries provided; refreshed artifacts only.")


if __name__ == "__main__":
    main()
