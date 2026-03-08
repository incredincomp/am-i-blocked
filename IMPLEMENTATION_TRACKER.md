# IMPLEMENTATION_TRACKER.md

This ledger summarizes current implementation state and next MVP work. It should align with direct user instructions, `AGENTS.md`, and current code/tests.

## Project

**Am I Blocked?** - internal network self-diagnosis and routing assistant.

## Current Objective

Deliver the MVP single-destination flow that returns `allowed | denied | unknown` with path context, confidence, and evidence-backed routing recommendations.

## Current Phase

MVP single-flow execution with persistence/queue lifecycle complete, PAN-OS adapter XML log retrieval implemented, and authoritative-correlation now consuming PAN-OS deny evidence conservatively.

- API -> Redis -> worker -> Postgres lifecycle is implemented and tested.
- API remains thin and worker-only vendor access is preserved.
- PAN-OS adapter supports XML traffic-log job submission + polling with conservative deny/reset normalization.
- Authoritative-correlation now enforces PAN-OS deny-authoritative gating (`source=panos`, `authoritative=true`, `action=deny`) before evidence enters classification.

## Architecture Snapshot

- Monorepo packages under `packages/` and services under `services/`.
- FastAPI API validates input, persists request records, enqueues jobs, and exposes result/evidence endpoints.
- Worker dequeues Redis jobs and runs deterministic steps:
  `validate -> readiness -> context -> bounded probes -> authoritative correlation -> classify -> persist/report`.
- Postgres is operational source of truth for request/result/audit lifecycle.
- Adapters are worker-only and remain required boundaries for PAN-OS, SCM, SD-WAN, LogScale, and Torq.
- Classifier authority is constrained: only authoritative sources may drive `denied`; enrichment-only evidence cannot.

## Status Summary

- Completed:
  - Thin API + async worker model is in place.
  - DB-backed request/result persistence is operational and fail-closed.
  - Redis enqueue/dequeue/dispatch lifecycle is operational.
  - Failure taxonomy (`reason/stage/category`) is persisted and surfaced in API/UI.
  - Evidence bundle download endpoint is implemented.
  - LogScale is explicitly enforced as enrichment-only/non-authoritative in classification.
  - PAN-OS adapter now performs XML traffic-log job submission + polling and emits authoritative evidence only for deny/reset actions.
  - Authoritative-correlation now consumes PAN-OS adapter output with deny-only authoritative filtering and step-level test coverage for deny, non-deny, malformed, timeout, and no-match behavior.
  - Integration-style lifecycle test now proves submit -> queue -> worker -> persist -> API result retrieval for both PAN-OS authoritative deny and no-authoritative-evidence paths.
- Remaining MVP-critical work:
  - PAN-OS rule metadata lookup for deny explainability is not implemented.

## Prioritized Task Queue

1. **Implement PAN-OS XML traffic-log retrieval in adapter**
   - Status: completed (2026-03-08)
   - Priority: P0
   - Why now: first real authoritative deny evidence path for MVP.
   - Acceptance:
     - submit XML traffic-log query job and poll job completion - done
     - normalize matched log rows into evidence records used by pipeline/classifier - done (deny/reset only)
     - explicit handling for timeout, no-match, and malformed response paths - done
     - unit tests cover success/timeout/no-match/malformed paths - done

2. **Wire authoritative correlation to consume PAN-OS deny evidence**
   - Status: completed (2026-03-08)
   - Priority: P0
   - Depends on: task 1
   - Acceptance:
     - correlation step calls PAN-OS adapter path (worker-only boundary) - done
     - deny/reset matches become authoritative evidence in report bundle - done (deny-authoritative gate)
     - classifier can resolve `denied` from this evidence - done (existing classifier deny rule + step tests)
     - persisted evidence includes source plane/timestamp/rule identifier when available - partially done (adapter provides when available; richer mapping remains unverified)

3. **Add PAN-OS rule metadata lookup for explainability**
   - Status: not started
   - Priority: P1
   - Depends on: tasks 1-2
   - Acceptance:
     - adapter exposes `lookup_rule_metadata(...)`
     - metadata inclusion does not alter deny authority rules
     - result bundle can include rule name and selected metadata fields

4. **Add one realistic integrated lifecycle test**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Acceptance:
     - test exercises submit -> queue -> worker -> persist -> result fetch - done
     - no real vendor calls (controlled fake adapter/server fixture) - done

5. **Docs alignment updates after authoritative PAN-OS path lands**
   - Status: deferred until tasks 1-2 complete
   - Priority: P2

## ROI-Ranked TODO Backlog

1. PAN-OS rule metadata enrichment for deny explainability.
2. Confidence/readiness quality improvements (`unknown` clarity and evidence completeness signals).
3. Documentation refresh after authoritative path is implemented.
4. Later enrichment work (SCM deepening, SD-WAN deepening, LogScale deepening, Torq).

## Active Blockers / Open Questions

- PAN-OS environment-specific XML details are still unverified in-repo:
  - exact filter shape for destination/port/time-window mapping
  - expected response variants across target PAN-OS versions
  - Panorama involvement in query flow (if any)
- PAN-OS authoritative gating currently depends on normalized fields (`action=deny`, `authoritative=true`); richer field mappings and variants remain intentionally unverified.

## Decision Log

- 2026-03-07: API remains thin; vendor access is worker-only.
- 2026-03-07: `unknown` is preferred over weak certainty.
- 2026-03-08: Runtime lifecycle is DB/Redis operational path; in-memory request/result runtime fallback removed.
- 2026-03-08: Failure metadata is bounded (`reason`, `stage`, `category`) and surfaced in API/UI for triage.
- 2026-03-08: LogScale is treated as `UNVERIFIED` enrichment-only and cannot independently drive `denied`.
- 2026-03-08: First authoritative MVP vendor path priority is PAN-OS XML traffic-log retrieval.
- 2026-03-08: PAN-OS adapter deny authority remains conservative; only deny/reset actions are normalized to authoritative traffic-log evidence, and non-deny/malformed data yields no authoritative match.
- 2026-03-08: Authoritative-correlation now drops PAN-OS records that are non-deny, non-authoritative, or malformed so absent authoritative evidence continues to bias toward `unknown`.
- 2026-03-08: Integration-style lifecycle coverage now proves persisted deny and non-deny outcomes through API submit, queue handoff, worker dispatch, persistence, and API result retrieval using controlled PAN-OS adapter behavior.

## Test Log

- Latest full-suite state recorded in tracker history: `uv run pytest -q` pass (118 tests).
- Latest lint slices in tracker history for touched runtime files: `uv run ruff check ...` pass.
- `ruff format --check` previously failed due to pre-existing repo-wide formatting drift (not part of this task scope).
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py tests/adapters/test_adapter_contracts.py` (pass, 22 tests).
- 2026-03-08: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/panos/__init__.py tests/adapters/test_panos_adapter.py tests/adapters/test_adapter_contracts.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/unit/test_authoritative_correlation.py tests/unit/test_pipeline.py` (pass, 14 tests).
- 2026-03-08: Ran `uv run pytest -q tests/unit/test_authoritative_correlation.py` (pass, 8 tests).
- 2026-03-08: Ran `uv run ruff check services/worker/am_i_blocked_worker/steps/authoritative_correlation.py tests/unit/test_authoritative_correlation.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 4 tests).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/test_lifecycle_integration.py` (pass).

## Iteration Journal

- 2026-03-07: Repository scaffolding and control-file grounding completed.
- 2026-03-08: Added bounded-probe failure hardening tests; probe failures degrade to `unknown` instead of crashing.
- 2026-03-08: Added DB/Redis readiness checks and wired API `/readyz` plus worker startup readiness reporting.
- 2026-03-08: Implemented API Postgres-first request/result handling, Redis enqueue, and worker dequeue/dispatch.
- 2026-03-08: Implemented worker persistence to Postgres for completion/result lifecycle; removed in-memory request/result runtime path.
- 2026-03-08: Added persisted failed-state metadata (`failure_reason`, `failure_stage`, `failure_category`) and UI triage hints.
- 2026-03-08: Hardened classifier authority so enrichment-only evidence (LogScale) cannot produce `denied`.
- 2026-03-08: Added observed-fact labeling/badges separating authoritative vs enrichment-only evidence.
- 2026-03-08: Added evidence-bundle download endpoint and result page integration.
- 2026-03-08: Re-prioritized queue to first authoritative PAN-OS deny path as the next MVP implementation target.
- 2026-03-08: Implemented PAN-OS adapter XML traffic-log job submission and polling with tests for success, timeout, no-match, and malformed XML; normalization remains conservative (deny/reset-only authoritative output).
- 2026-03-08: Wired authoritative-correlation PAN-OS consumption with deny-authoritative filtering and added step-level tests proving non-deny/malformed/timeout/no-match paths do not emit authoritative evidence.
- 2026-03-08: Added integration-style lifecycle tests covering submit/enqueue, worker dequeue/dispatch, persistence, and API result retrieval for both authoritative PAN-OS deny and no-authoritative-evidence paths.

## Historical / Superseded Checkpoints

The previous checkpoint sequence B-R (2026-03-08) was compressed into the consolidated journal and decisions above. Their transitional blockers are resolved and should not be treated as active:

- Superseded blockers:
  - "worker does not dequeue Redis jobs" -> resolved
  - "worker outputs not written to DB" -> resolved
  - "API/worker still keep in-memory fallback stores" -> resolved
  - "failed-job reason persistence is minimal" -> resolved
  - "failure stage tagging not step-specific" -> resolved
  - "UI lacks triage hint mapping" -> resolved

## Next Recommended Task

Implement PAN-OS `lookup_rule_metadata(...)` in the adapter with conservative, test-backed metadata retrieval that enriches deny explainability without changing deny authority semantics.

## Deferred / Later

- SCM/Prisma deepening after first authoritative PAN-OS path is complete.
- SD-WAN deeper path-health enrichment after core deny authority path is live.
- LogScale query-job implementation only after explicit verification and intentional scope expansion.
- Torq outbound enrichment after core verdict path is stable.
- Multi-destination flows, broad UI work, and platform expansion (out of MVP scope).
