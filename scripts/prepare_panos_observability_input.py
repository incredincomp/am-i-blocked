#!/usr/bin/env python3
"""Prepare normalized PAN-OS observability correlation input.

This helper ingests manual fields and/or a single-row CSV/JSON export and writes
one machine-readable `OBSERVABILITY_INPUT.json` artifact for orchestrator use.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def iso_utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_present(mapping: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        if key in mapping:
            value = _clean(mapping.get(key))
            if value is not None:
                return value
    return None


def _load_row_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        if not data:
            return {}
        if not isinstance(data[0], dict):
            return {}
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def _load_row_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            return dict(row)
    return {}


def _signature_family(payload: dict[str, Any]) -> str:
    return "|".join(
        [
            payload.get("source_ip") or "unknown",
            payload.get("destination_ip") or "unknown",
            str(payload.get("destination_port")) if payload.get("destination_port") is not None else "unknown",
            payload.get("app") or "unknown",
            payload.get("rule") or "unknown",
            payload.get("session_end_reason") or "unknown",
            payload.get("zone_src") or "unknown",
            payload.get("zone_dst") or "unknown",
        ]
    )


def _parse_destination_port(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value) if value.isdigit() else None


def _confidence(payload: dict[str, Any]) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []

    if payload.get("session_id"):
        score += 2
    else:
        reasons.append("session_id_missing")

    if payload.get("ui_filter_string"):
        score += 2
    else:
        reasons.append("ui_filter_string_missing")

    if payload.get("evidence_origin") in {"ui_csv_export", "ui_json_export", "structured_row"}:
        score += 2
    else:
        reasons.append("evidence_origin_not_structured")

    if payload.get("freshness_note"):
        score += 1
    else:
        reasons.append("freshness_note_missing")

    if score >= 5:
        return "high", score, reasons
    if score >= 3:
        return "medium", score, reasons
    return "low", score, reasons


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    row: dict[str, Any] = {}
    source = "manual_fields"

    if args.row_json:
        row = _load_row_json(Path(args.row_json))
        source = f"row_json:{args.row_json}"
    elif args.row_csv:
        row = _load_row_csv(Path(args.row_csv))
        source = f"row_csv:{args.row_csv}"

    payload: dict[str, Any] = {
        "panos_version": _clean(args.panos_version) or _first_present(row, ["panos_version", "sw-version", "version"]),
        "source": source,
        "created_at": iso_utc_now(),
        "correlation_confidence": "low",
        "session_id": _clean(args.session_id) or _first_present(row, ["session_id", "sessionid", "session-id"]),
        "ui_filter_string": _clean(args.ui_filter_string) or _first_present(row, ["ui_filter_string", "filter", "query"]),
        "source_ip": _clean(args.source_ip) or _first_present(row, ["source_ip", "src"]),
        "destination_ip": _clean(args.destination_ip) or _first_present(row, ["destination_ip", "dst"]),
        "destination_port": None,
        "app": _clean(args.app) or _first_present(row, ["app"]),
        "action": _clean(args.action) or _first_present(row, ["action"]),
        "rule": _clean(args.rule) or _first_present(row, ["rule"]),
        "session_end_reason": _clean(args.session_end_reason)
        or _first_present(row, ["session_end_reason", "session-end-reason"]),
        "zone_src": _clean(args.zone_src) or _first_present(row, ["zone_src", "from"]),
        "zone_dst": _clean(args.zone_dst) or _first_present(row, ["zone_dst", "to"]),
        "type_detail": _clean(args.type_detail) or _first_present(row, ["type_detail", "type"]),
        "row_timestamp": _clean(args.row_timestamp)
        or _first_present(row, ["row_timestamp", "receive_time", "time_generated", "time"]),
        "freshness_note": _clean(args.freshness_note),
        "evidence_origin": _clean(args.evidence_origin) or "manual",
    }

    dst_port = _clean(args.destination_port) or _first_present(row, ["destination_port", "dport", "port", "port.dst"])
    payload["destination_port"] = _parse_destination_port(dst_port)

    payload["distinct_signature_family"] = _signature_family(payload)

    required = [
        "source_ip",
        "destination_ip",
        "destination_port",
        "action",
        "rule",
        "session_end_reason",
        "row_timestamp",
    ]
    missing = [f"{field}_missing" for field in required if payload.get(field) in (None, "")]
    confidence, score, confidence_reasons = _confidence(payload)
    payload["correlation_confidence"] = confidence

    why_not_ready = [*missing]
    if score < 3:
        why_not_ready.append("correlation_signals_too_weak")
    if confidence == "low":
        why_not_ready.extend(
            reason
            for reason in confidence_reasons
            if reason in {"session_id_missing", "ui_filter_string_missing"}
        )

    payload["ready_for_orchestrator"] = len(why_not_ready) == 0
    payload["why_not_ready"] = why_not_ready if why_not_ready else None
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare OBSERVABILITY_INPUT.json from stronger correlation evidence")
    parser.add_argument("--out", default="docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json")

    parser.add_argument("--row-json")
    parser.add_argument("--row-csv")

    parser.add_argument("--panos-version")
    parser.add_argument("--session-id")
    parser.add_argument("--ui-filter-string")
    parser.add_argument("--source-ip")
    parser.add_argument("--destination-ip")
    parser.add_argument("--destination-port")
    parser.add_argument("--app")
    parser.add_argument("--action")
    parser.add_argument("--rule")
    parser.add_argument("--session-end-reason")
    parser.add_argument("--zone-src")
    parser.add_argument("--zone-dst")
    parser.add_argument("--type-detail")
    parser.add_argument("--row-timestamp")
    parser.add_argument("--freshness-note")
    parser.add_argument("--evidence-origin", default="manual")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_payload(args)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
