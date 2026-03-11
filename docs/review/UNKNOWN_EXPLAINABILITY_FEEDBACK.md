# Unknown Explainability Feedback Summary

## Purpose
Structured operator feedback ledger for unknown-result explainability copy follow-up prioritization.

## Recording Feedback
- Single entry example:
  - `uv run python scripts/record_unknown_explainability_feedback.py --sample-id sample_1 --reviewer alice --understandable-score 4 --actionable-score 3 --too-technical-score 2 --too-vague-score 2 --incorrectly-sounds-like-allowed false --copy-followup-candidate "Clarify source-readiness wording" --followup-priority medium --ready-for-copy-change true --write-summary`
- Batch file example:
  - `uv run python scripts/record_unknown_explainability_feedback.py --input-json /path/to/feedback.json --write-summary`
- Partial entries are allowed; unknown sample IDs fail closed.

## Totals
- Total feedback entries: 0
- Samples tracked: 3

## Per-Sample Summary

### sample_1: Unknown with low confidence and explicit readiness degradation
- Source: `tests/routes/test_api_routes.py:1262`
- Status: **insufficient feedback**
- Feedback count: 0

### sample_2: Unknown with malformed persisted confidence values and explicit custom reason
- Source: `tests/routes/test_api_routes.py:1312`
- Status: **insufficient feedback**
- Feedback count: 0

### sample_3: Unknown with mixed readiness entry quality and incomplete evidence context
- Source: `tests/routes/test_api_routes.py:1357`
- Status: **insufficient feedback**
- Feedback count: 0

## Priority Buckets
- Copy-only follow-up likely needed:
- No change needed yet:
- Insufficient feedback:
  - sample_1
  - sample_2
  - sample_3

## Artifact Notes
- This summary is generated from `UNKNOWN_EXPLAINABILITY_FEEDBACK.json` and `UNKNOWN_EXPLAINABILITY_SAMPLES.json`.
- Workflow scope is copy-follow-up triage only; no runtime verdict/classifier/readiness semantics are changed.
