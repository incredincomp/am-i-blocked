# IMPLEMENTATION_TRACKER.md

This ledger summarizes current implementation state and next MVP work. It should align with direct user instructions, `AGENTS.md`, and current code/tests.

## Project

**Am I Blocked?** - internal network self-diagnosis and routing assistant.

## Current Objective

Deliver the MVP single-destination flow that returns `allowed | denied | unknown` with path context, confidence, and evidence-backed routing recommendations.

## Current Phase

MVP single-flow execution with persistence/queue lifecycle complete, PAN-OS deny path operational, PAN-OS metadata visible in operator output, minimal unknown-confidence explainability in place, and fixture-based PAN-OS parser-shape verification completed without adapter behavior changes.

- API -> Redis -> worker -> Postgres lifecycle is implemented and tested.
- API remains thin and worker-only vendor access is preserved.
- PAN-OS adapter supports XML traffic-log job submission + polling with conservative deny/reset normalization.
- Authoritative-correlation now enforces PAN-OS deny-authoritative gating (`source=panos`, `authoritative=true`, `action=deny`) before evidence enters classification.
- PAN-OS adapter now performs conservative optional rule metadata lookup and attaches metadata to deny evidence when available.
- API/UI result rendering now surfaces persisted PAN-OS rule metadata (when present on authoritative PAN-OS deny observed facts) without changing verdict authority semantics.
- Integration-style lifecycle coverage now proves PAN-OS metadata survives submit -> queue -> worker -> persist -> API result retrieval -> UI rendering via normal persisted retrieval paths.
- API/UI now surfaces compact unknown-confidence explainability (`path_confidence`, `evidence_completeness`, and `unknown_reason_signals`) for `unknown` verdicts.
- PAN-OS verification fixture pack scaffolding now exists (`docs/fixtures/panos_verification`) with required sample file templates and sanitization rules.
- PAN-OS fixture validation now confirms current parser marker assumptions against fixture XML shapes (`.//job`, `.//status`, `.//logs/entry`, `.//entry[@name]`).
- PAN-OS traffic-log filter fields and metadata XPath remain explicitly `UNVERIFIED` placeholders pending target-environment evidence capture.

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
  - PAN-OS `lookup_rule_metadata(...)` is now implemented with conservative XML config lookup, graceful failure handling, and optional attachment to deny evidence.
  - Minimal operator-facing API/UI output now renders PAN-OS rule metadata from persisted observed-fact detail when present (`rule_name`, optional `action`, `description`, `disabled`, `tags`) and degrades gracefully when absent or malformed.
  - Integration-style lifecycle tests now prove persisted PAN-OS deny metadata is retrievable via `GET /api/v1/requests/{id}/result` and rendered via `/requests/{id}` without route-loader patching, while malformed metadata still degrades gracefully.
  - PAN-OS validation pass confirmed async XML job flow assumptions are supported by repo-level vendor grounding, but found no target-version XML evidence to promote current filter-field or XPath placeholders from `UNVERIFIED`.
  - Unknown-result confidence surfacing is now implemented: API returns `unknown_reason_signals`, and UI renders compact "Why unknown" signals tied to `path_confidence` and `evidence_completeness`.
  - PAN-OS fixture/documentation scaffolding now defines exact XML sample files required for verification and includes parser/structure checks in tests.
  - Fixture-based verification run completed: parser shape assumptions align with fixture XML; adapter runtime behavior remains unchanged because fixtures are still placeholder-level and not version-pinned production captures.
- Remaining MVP-critical work:
  - Capture sanitized target PAN-OS XML samples/version data into the fixture pack and then verify or correct `addr.dst`/`port.dst` and metadata XPath placeholders.

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
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 1-2
   - Acceptance:
     - adapter exposes `lookup_rule_metadata(...)` - done
     - metadata inclusion does not alter deny authority rules - done
     - result bundle can include rule name and selected metadata fields - done (attached to PAN-OS deny evidence records when available)

4. **Add one realistic integrated lifecycle test**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Acceptance:
     - test exercises submit -> queue -> worker -> persist -> result fetch - done
     - no real vendor calls (controlled fake adapter/server fixture) - done

5. **Surface persisted PAN-OS rule metadata in minimal operator output**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 1-4
   - Acceptance:
     - API result output continues exposing observed-fact detail metadata without verdict logic changes - done
     - result UI displays PAN-OS rule metadata only when present on authoritative PAN-OS deny observed facts - done
     - absent or malformed metadata does not break API/UI rendering and does not affect verdict authority - done

6. **Docs alignment updates after PAN-OS metadata output surfacing**
   - Status: completed (2026-03-08)
   - Priority: P2

7. **Prove persisted PAN-OS metadata lifecycle retrieval/render path**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 1-6
   - Acceptance:
     - integration test persists deny evidence containing PAN-OS metadata and retrieves it via normal API result endpoint - done
     - integration test verifies metadata is rendered on result page via persisted path without route-loader patching - done
     - malformed metadata still preserves deny path and does not break API/UI rendering - done

8. **Validate PAN-OS XML filter/XPath assumptions against target-environment evidence**
   - Status: completed (2026-03-08, evidence review only)
   - Priority: P1
   - Depends on: tasks 1-7
   - Acceptance:
     - inspect repo for target PAN-OS version/environment evidence - done
     - promote placeholders only when evidence proves them - done (no promotions made; evidence absent)
     - record verified vs unverified assumptions and exact evidence needed next - done

9. **Add minimal unknown-confidence explainability surfacing**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 1-8
   - Acceptance:
     - expose `path_confidence` + `evidence_completeness` in compact operator-facing unknown explanation - done
     - add short unknown rationale signals without influencing verdict logic - done (`unknown_reason_signals`)
     - malformed/missing confidence values degrade gracefully in persisted-result load path and UI rendering - done

10. **Create PAN-OS verification fixture pack and validation scaffolding**
   - Status: completed (2026-03-08)
   - Note: added `scripts/gather_panos_fixtures.sh` helper and corresponding Makefile target/test to simplify real‑world sample collection.
   - Priority: P1
   - Depends on: tasks 1-9
   - Acceptance:
     - add docs fixture location and exact required PAN-OS XML sample files - done
     - document sanitization rules and expected structural fields - done
     - add small validation test/helper that loads/parses required samples - done
     - no adapter behavior changes - done

11. **Fixture-based PAN-OS placeholder verification and contract hardening**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 1-10
   - Acceptance:
     - validate adapter submit/poll/metadata parser assumptions against fixture pack - done
     - strengthen fixture sanitization contract wording with explicit redaction/tokenization rules - done
     - change adapter behavior only if fixture evidence disproves current assumptions - done (no runtime changes required)

## ROI-Ranked TODO Backlog

1. Populate PAN-OS fixture pack with sanitized real-environment XML captures and use them to validate/correct adapter query-field/XPath placeholders.  (helper script now available to automate extraction)
2. Validate unknown-confidence explainability wording with operators and tighten thresholds/messages if needed (explainability only).
3. Later enrichment work (SCM deepening, SD-WAN deepening, LogScale deepening, Torq).

## Active Blockers / Open Questions

- PAN-OS environment-specific XML details are still unverified in-repo:
  - target PAN-OS version/build for queried devices is not captured in repo config/docs
  - exact filter shape for destination/port/time-window mapping
  - expected response variants across target PAN-OS versions
  - Panorama involvement in query flow (if any)
- PAN-OS authoritative gating currently depends on normalized fields (`action=deny`, `authoritative=true`); richer field mappings and variants remain intentionally unverified.
- PAN-OS rule metadata XPath shape and field completeness are environment/version dependent (`UNVERIFIED`); current implementation intentionally parses a minimal metadata subset.

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
- 2026-03-08: PAN-OS rule metadata lookup is optional explainability enrichment only; metadata lookup failures never create or remove deny authority.
- 2026-03-08: Operator-facing PAN-OS metadata output is sourced only from persisted observed-fact detail on authoritative PAN-OS deny facts and remains optional explainability data (not authority input).
- 2026-03-08: Persisted lifecycle coverage now explicitly includes PAN-OS metadata retrieval/render assertions using normal API/UI DB-backed paths (no route-level loader patching shortcuts).
- 2026-03-08: PAN-OS validation policy remains conservative: no query-field/XPath mapping changes without target-environment versioned XML evidence.
- 2026-03-08: Unknown-confidence surfacing is explainability-only (`unknown_reason_signals`), and confidence values do not influence verdict authority semantics.
- 2026-03-08: PAN-OS verification fixture templates + parser checks are the required staging path before promoting any PAN-OS XML mapping assumption from `UNVERIFIED`.
- 2026-03-08: Fixture-based parser-shape verification is distinct from environment/version verification; query-field and XPath placeholders remain `UNVERIFIED` until real sanitized captures validate them.

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
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py tests/adapters/test_adapter_contracts.py` (pass, 32 tests).
- 2026-03-08: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/panos/__init__.py tests/adapters/test_panos_adapter.py tests/adapters/test_adapter_contracts.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "panos_rule_metadata or labels_enrichment_and_authoritative_facts or evidence_bundle_download_returns_attachment or result_returns_persisted_result_when_available"` (pass, 7 selected).
- 2026-03-08: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 34 tests).
- 2026-03-08: Ran `uv run ruff check tests/routes/test_api_routes.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 6 tests).
- 2026-03-08: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "panos_rule_metadata"` (pass, 4 selected).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/test_lifecycle_integration.py tests/routes/test_api_routes.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py tests/fixtures/test_lifecycle_integration.py` (pass, 24 tests).
- 2026-03-08: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/panos/__init__.py tests/adapters/test_panos_adapter.py tests/fixtures/test_lifecycle_integration.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "unknown_includes_confidence_reason_signals or unknown_renders_confidence_signals or unknown_without_reason_signals_uses_fallback_message or load_result_record_unknown"` (pass, 7 selected).
- 2026-03-08: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 41 tests).
- 2026-03-08: Ran `uv run ruff check services/api/am_i_blocked_api/routes/api.py packages/core/am_i_blocked_core/models.py tests/routes/test_api_routes.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 3 tests).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/test_panos_verification_fixture_pack.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py tests/adapters/test_panos_adapter.py -k "FixtureAlignment or verification_fixture_pack"` (pass, 7 selected).
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py` (pass, 21 tests).
- 2026-03-08: Ran `uv run ruff check tests/adapters/test_panos_adapter.py tests/fixtures/test_panos_verification_fixture_pack.py docs/fixtures/panos_verification/README.md` (pass).

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
- 2026-03-08: Implemented PAN-OS adapter rule metadata lookup with tests for success/no-match/malformed/timeout and optional attachment to deny evidence without changing deny authority semantics.
- 2026-03-08: Added minimal result-page PAN-OS metadata rendering from observed-fact detail (`rule_name` + optional action/description/disabled/tags) with route tests for present, absent, and malformed metadata behavior.
- 2026-03-08: Extended lifecycle integration coverage so persisted PAN-OS deny metadata is asserted through worker execution, API result retrieval, and UI rendering; also confirmed malformed metadata preserves deny and skips metadata panel rendering.
- 2026-03-08: Ran PAN-OS validation review against repo docs/config/tests; no target-environment XML/version artifacts were found, so `addr.dst`/`port.dst` filter fields and metadata XPath remain documented as `UNVERIFIED` placeholders.
- 2026-03-08: Added minimal unknown-result confidence explainability in API/UI with derived `unknown_reason_signals` and loader-level confidence coercion for malformed/missing persisted values.
- 2026-03-08: Added PAN-OS verification fixture-pack scaffolding (required XML sample templates, sanitization guidance, and parser/shape validation test) without changing adapter behavior.
- 2026-03-08: Hardened PAN-OS fixture sanitization contract and added fixture-alignment tests; validation confirmed parser shape compatibility but did not justify query-field/XPath runtime changes.

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

Populate `docs/fixtures/panos_verification/` with sanitized target-environment PAN-OS XML captures (submit, poll, metadata config) and run mapping validation to confirm or correct current `UNVERIFIED` filter-field and XPath placeholders.

## Deferred / Later

- SCM/Prisma deepening after first authoritative PAN-OS path is complete.
- SD-WAN deeper path-health enrichment after core deny authority path is live.
- LogScale query-job implementation only after explicit verification and intentional scope expansion.
- Torq outbound enrichment after core verdict path is stable.
- Multi-destination flows, broad UI work, and platform expansion (out of MVP scope).
