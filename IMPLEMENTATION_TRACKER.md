# IMPLEMENTATION_TRACKER.md

This ledger summarizes current implementation state and next MVP work. It should align with direct user instructions, `AGENTS.md`, and current code/tests.

## Project

**Am I Blocked?** - internal network self-diagnosis and routing assistant.

## Current Objective

Deliver the MVP single-destination flow that returns `allowed | denied | unknown` with path context, confidence, and evidence-backed routing recommendations.

## Current Phase

MVP single-flow execution with persistence/queue lifecycle complete, PAN-OS deny path operational, PAN-OS metadata visible in operator output, and unknown-confidence explainability wording tightened for operator clarity, plus fixture-based PAN-OS parser-shape verification and version-aware fixture-capture tooling completed with minimal query-token reconciliation aligned to real-capture evidence.

Current PAN-OS evidence focus: **observability-gated token validation** for `11.0.6-h1` with one completed fresh-row-coupled Stage 1/Stage 2 success pair (`deny-hit-udp-obsgate-stage1_20260311T052621Z`, `deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`).

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
- PAN-OS fixture gather helper now writes versioned capture sets (`versions/<panos_version>/<capture_label>_<timestamp>/`), capture metadata manifests, and canonical fixture mirrors for validation tests.
- PAN-OS fixture tooling now includes a `version + scenario` selector helper for tests and optional keygen auth fallback (`--username`/`--password`) in the capture script.
- PAN-OS bounded one-shot observe-and-validate orchestration helper now exists (`scripts/panos_observe_and_validate.py`) to automate traffic generation, broad Stage 1 observability sweep, freshest-row selection, and conditional Stage 2 token subqueries with machine-readable summary output.
- PAN-OS orchestration now writes `OBSERVABILITY_RECORD.json` on every run outcome and uses attempt-signature loop-breaker gating to block repeated materially identical no-hit retries unless correlation input improves.
- Versioned fixture manifests and selectors are now provenance-aware (`real_capture` vs `template_seeded` vs `synthetic`) with explicit verification-scope gating and fail-closed selection semantics.
- Local fixture collection now enforces a repo-owned read-only PAN-OS request allowlist guard before each live call (`op/show system info`, `log submit/get`, `config get/show/complete`, keygen bootstrap only).
- Local keygen bootstrap now fails fast on explicit XML API auth rejection signatures (`403 Invalid Credential`) with explicit operator preflight guidance, no invalid-credential retry loop, and separate generic handling for non-auth XML keygen errors.
- Real-capture versioned fixture packs now exist for PAN-OS `11.0.6-h1` scenarios (`deny-hit`, `no-match`, `metadata-hit`, `query-shape`, `xpath-shape`) collected through the hardened local harness with read-only guard enforcement.
- PAN-OS verification remains observability-gated for new token-validation attempts; latest real-capture evidence now proves scenario-scoped `addr.dst` + `dport` query behavior for `11.0.6-h1` UDP deny signature, while broader/cross-scenario behavior remains `UNVERIFIED`.
- `LIVE_DENY_OBSERVABILITY_TEMPLATE.md` is now optional/manual supplemental evidence; orchestrator-generated `OBSERVABILITY_RECORD.json` is the default run-state source of truth.

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
  - PAN-OS fixture helper/README contract now supports repeatable multi-version capture workflows (versioned folders, labeled captures, capture metadata, and explicit capture matrix guidance) without changing runtime adapter logic.
  - Fixture tests can now auto-select newest versioned capture by `version + scenario` via helper, reducing hardcoded fixture-path coupling.
  - One existing PAN-OS adapter fixture-alignment test now uses the versioned selector path end-to-end (`11.0.2` + `deny-hit`) with manifest assertions.
- Selector/manifest hardening now prevents trust confusion between template/synthetic fixtures and real-capture evidence in verification workflows.
- Local-firewall collection harness is now constrained by explicit read-only request allowlist checks and test-backed fake-curl harness validation.
- Keygen/auth preflight remains fail-fast with explicit credential blocker guidance and no invalid-credential retry loops.
- Harness now URL-encodes dynamic `query`/`xpath` parameters and sanitizes additional rule/object-like values (`entry` names, `uuid`, `member`) in saved artifacts.
- Real-capture evidence now proves version-scoped partial XPath/config shape for `11.0.6-h1`; query-token correctness remains unverified.
- Remaining MVP-critical work:
  - Continue bounded PAN-OS token verification only through observability-gated, scenario-scoped real-capture runs; avoid broad token generalization and keep config/XPath validation as a separate track.

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

12. **Harden PAN-OS fixture collection for versioned evidence capture**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 10-11
   - Acceptance:
     - helper supports versioned output folders per PAN-OS version and capture label - done
     - helper records capture metadata and request logs for traceability - done
     - helper keeps canonical required fixture files updated for existing validation tests - done
     - docs describe required versioned layout and capture matrix for future evidence collection - done

13. **Add fixture selector helper + keygen auth fallback for capture script**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 10-12
   - Acceptance:
     - tests can select newest versioned capture by `version + scenario` without adapter changes - done
     - capture helper can request API key via username/password when key is not pre-provided - done
     - keygen request/response artifacts are sanitized and captured for traceability - done
     - one existing PAN-OS fixture-alignment test is refactored to use selector + manifest pattern - done

14. **Harden fixture provenance/scope trust contract**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 10-13
   - Acceptance:
     - `CAPTURE_METADATA.txt` has required provenance/scope/version-source fields with allowed-value validation - done
     - selector supports explicit trust filters and fails closed on provenance/scope mismatch - done
     - newest-match selection happens only among captures that pass trust filters - done
     - fixture validation tests enforce stricter manifest contract - done
     - no PAN-OS adapter runtime behavior changes - done

15. **Harden local-firewall read-only collection harness**
   - Status: completed (2026-03-08)
   - Priority: P1
   - Depends on: tasks 10-14
   - Acceptance:
     - repo-owned guard enforces PAN-OS read-only request allowlist and rejects disallowed classes/actions - done
     - gather script uses allowlist guard for all live request paths - done
     - local collection harness tests prove guard rejection and real-capture manifest/sanitization behavior - done
     - no classifier/API/UI/PAN-OS adapter runtime changes - done

16. **Harden PAN-OS keygen auth preflight/operator guidance**
   - Status: completed (2026-03-09)
   - Priority: P1
   - Depends on: tasks 10-15
   - Acceptance:
     - keygen `403 Invalid Credential` fails clearly as auth/authorization blocker - done
     - script avoids repeated invalid-credential retries - done
     - operator prerequisites documented for API-key mode and XML-API-role requirements - done
     - no adapter/classifier/API/UI behavior changes - done

17. **Tighten keygen auth-failure classification precision**
   - Status: completed (2026-03-09)
   - Priority: P1
   - Depends on: tasks 10-16
   - Acceptance:
     - keygen auth guidance triggers only for explicit PAN-OS auth rejection signatures (`403 Invalid Credential` class) - done
     - non-auth XML API keygen errors remain fail-fast but are reported as generic keygen/API errors - done
     - harness tests cover both invalid-credential and non-auth XML error responses - done
     - no PAN-OS adapter/classifier/API/UI behavior changes - done

18. **Collect real-capture PAN-OS fixture scenarios from reachable local firewall**
   - Status: completed (2026-03-10, blocked in auth preflight)
   - Priority: P1
   - Depends on: tasks 10-17
   - Acceptance:
     - run hardened read-only harness using current credential path (`--api-key` preferred, else keygen) - done (keygen path)
     - collect bounded scenario packs where available (`deny-hit`, `no-match`, `metadata-hit`, `query-shape`, `xpath-shape`) with `capture_provenance=real_capture` - blocked (preflight auth/keygen response)
     - stop immediately and record blocker if auth fails (`403 Invalid Credential` / auth rejection) - done (stopped after first failed preflight)
     - promote PAN-OS assumptions from `UNVERIFIED` only when real-capture evidence clearly proves them and scope claims by version/scenario - done (no promotions made; evidence absent)
     - update docs/tests/tracker/source-refresh with collected evidence and remaining gaps - done

19. **Retry real-capture collection + strict real-provenance verification wiring**
   - Status: completed (2026-03-10)
   - Priority: P1
   - Depends on: tasks 10-18
   - Acceptance:
     - rerun hardened read-only harness against current local credentials and stop immediately on auth preflight blocker - done
     - collect bounded `real_capture` scenarios only if auth succeeds - done (`11.0.6-h1` packs collected; mixed completeness)
     - verification tests that claim assumption-promotion path explicitly require `require_provenance=\"real_capture\"` - done
     - no PAN-OS assumption promotion without collected real-capture evidence - done
     - docs/tracker/source-refresh reconciled with this retry outcome - done

20. **Produce PAN-OS observability coverage postmortem + single next-path decision**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 10-19
   - Acceptance:
     - analyze all versioned `CAPTURE_METADATA.txt`, `OBSERVABILITY_RECORD.json`, and `VALIDATION_RESULT.json` artifacts - done
     - classify runs into proven / observability-hit-not-proven / no-hit / loop-breaker-risk groups - done
     - generate machine-readable and human-readable coverage summaries under `docs/fixtures/panos_verification/` - done
     - select exactly one evidence-backed next path and record it without running a new live attempt - done

21. **Implement higher-confidence observability input artifact + orchestrator gating**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 19-20
   - Acceptance:
     - add bounded helper to normalize stronger correlation evidence into machine-readable `OBSERVABILITY_INPUT.json` - done
     - mark inputs as `ready_for_orchestrator=false` when confidence is too weak/incomplete and include explicit `why_not_ready` - done
     - allow orchestrator to accept `--observability-input` and fail closed when provided input is not ready - done
     - make loop-breaker treat `OBSERVABILITY_INPUT.json` as primary evidence-quality improvement mechanism for repeated no-hit signature retries - done
     - keep `LIVE_DENY_OBSERVABILITY_TEMPLATE.md` optional/manual support, not preferred machine input - done
     - add focused non-live tests for helper and orchestrator behavior - done

22. **Execute one bounded distinct-signature run with ready observability input**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 20-21
   - Acceptance:
     - select one materially distinct candidate family from observability coverage - done (`10.1.99.3 -> 10.1.20.21:30053`, `app=not-applicable`, `rule=interzone-default`)
     - prepare `OBSERVABILITY_INPUT.json` with strong correlation evidence and verify `ready_for_orchestrator=true` - done
     - run exactly one bounded orchestrator attempt with `--observability-input` - done
     - treat resulting `OBSERVABILITY_RECORD.json`/`VALIDATION_RESULT.json` as source of truth and avoid same-run retries - done
     - promote assumptions only if new real-capture evidence justifies it - done (no promotions)

23. **Add candidate-family selector to prevent exhausted retry loops**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 20-22
   - Acceptance:
     - classify signature families into `proven`, `candidate`, `exhausted_pending_new_evidence`, `blocked_by_loop_breaker` from existing artifacts - done
     - generate `NEXT_CANDIDATE_DECISION.json` and `NEXT_CANDIDATE_DECISION.md` from evidence - done
     - select exactly one next recommendation (`candidate` family or `pause`) - done (current output: `pause_panos_token_expansion`)
     - record exhausted-family policy so repeated no-hit strong-input families are not retried without materially stronger evidence - done
     - add focused non-live selector tests - done

24. **Surface source-readiness snapshot in result API/UI output**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 1-9
   - Acceptance:
     - expose compact source-readiness summary in `DiagnosticResult` payload from persisted `report_json.source_readiness` - done
     - render the readiness summary in result UI for operator triage - done
     - keep verdict/classifier behavior unchanged - done
     - add focused route tests for API + UI readiness-summary surfacing - done

25. **Implement bounded SCM readiness probe state mapping**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: task 24
   - Acceptance:
     - implement SCM adapter readiness probe with explicit states (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`) - done
     - keep probe bounded (single lightweight auth request, short timeout, no retries, no evidence-query expansion) - done
     - normalize SCM readiness into existing persisted `source_readiness` structure without classifier/verdict changes - done
     - add focused non-live tests for SCM readiness states and readiness-step propagation - done

26. **Add compact per-source readiness detail block in result UI**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 24-25
   - Acceptance:
     - expose additive `source_readiness_details` in result load path from persisted `report_json.source_readiness` - done
     - render compact UI section with source + status + reason - done
     - handle missing/malformed readiness entries gracefully - done
     - keep verdict/classifier/worker behavior unchanged - done
     - add focused route tests for render and load-path fallback behavior - done

27. **Implement bounded SD-WAN readiness probe state mapping**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 24-26
   - Acceptance:
     - implement SD-WAN adapter readiness probe with explicit states (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`) - done
     - keep probe bounded (single lightweight request, short timeout, no retries, no evidence-query expansion) - done
     - normalize SD-WAN readiness into existing persisted `source_readiness` structure without classifier/verdict changes - done
     - add focused non-live tests for SD-WAN readiness states and readiness-step propagation - done

28. **Implement bounded Torq readiness probe state mapping**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 24-27
   - Acceptance:
     - implement Torq adapter readiness probe with explicit states (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`) - done
     - keep probe bounded (single lightweight request, short timeout, no retries, no workflow execution expansion) - done
     - normalize Torq readiness into existing persisted `source_readiness` structure without classifier/verdict changes - done
     - add focused non-live tests for Torq readiness states and readiness-step propagation - done

29. **Implement bounded LogScale readiness probe state mapping**
   - Status: completed (2026-03-11)
   - Priority: P1
   - Depends on: tasks 24-28
   - Acceptance:
     - implement LogScale adapter readiness probe with explicit states (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`) - done
     - keep probe bounded (single lightweight request, short timeout, no retries, no LogScale query execution expansion) - done
     - normalize LogScale readiness into existing persisted `source_readiness` structure without classifier/verdict changes - done
     - preserve LogScale enrichment-only/non-authoritative semantics - done
     - add focused non-live tests for LogScale readiness states and readiness-step propagation - done

30. **Implement bounded SCM authoritative evidence retrieval path**
   - Status: completed (2026-03-12)
   - Priority: P1
   - Depends on: tasks 25 and authoritative SCM gating hardening
   - Acceptance:
     - add one bounded SCM adapter evidence request path (worker-only) - done
     - normalize only clearly authoritative SCM deny/decrypt records with explicit authoritative flag + request-context match - done
     - fail closed for malformed/ambiguous/non-authoritative/non-deny SCM responses and transport/auth failures - done
     - keep classifier/verdict logic unchanged aside from consuming normalized authoritative SCM records - done
     - add focused mock-only adapter + authoritative-correlation tests - done

## ROI-Ranked TODO Backlog

1. Populate PAN-OS fixture pack with sanitized real-environment XML captures across each target PAN-OS version (deny/no-match/metadata/malformed matrix) and use them to validate/correct adapter query-field/XPath placeholders.
2. Validate unknown-confidence explainability wording with operators and tighten thresholds/messages if needed (explainability only).
3. Later enrichment work (SCM deepening, SD-WAN deepening, LogScale deepening, Torq).

## Active Blockers / Open Questions

- PAN-OS environment-specific XML details are still unverified in-repo:
  - target PAN-OS version/build for queried devices is not yet captured from real environments into the versioned fixture pack
  - exact filter shape for destination/port/time-window mapping
  - expected response variants across target PAN-OS versions
  - Panorama involvement in query flow (if any)
- Local-firewall auth/bootstrap is now working for bounded collection with current `.env` credentials, and real-capture scenario completeness is mixed:
  - deny-hit real-capture evidence now exists for observability-coupled UDP signature (`deny-hit-udp-obsgate-stage1_20260311T052621Z`, `deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`)
  - some prior scenarios still show submit errors or zero-entry polls (`deny-hit`/`query-shape` API error 17; `no-match`/`metadata-hit`/`xpath-shape` zero-entry polls)
- Query-token assumptions now split between proven scenario scope and broader open scope:
  - scenario-scoped proven (`11.0.6-h1`, UDP deny signature): `addr.dst` and `dport` matched in Stage 2 after Stage 1 qualifying deny capture
  - still `UNVERIFIED`: cross-scenario and cross-version destination-token behavior
  - canonical PAN-OS traffic-log port names for guidance: `sport`, `dport`, `natsport`, `natdport`
- Template-seeded/synthetic versioned fixture packs are now explicitly non-promotable for environment verification; only `capture_provenance=real_capture` can be used for assumption promotion.
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
- 2026-03-08: Fixture collection now uses versioned capture packs plus canonical file mirrors, so multi-version evidence can be stored without breaking existing fixture validation tests.
- 2026-03-08: Versioned fixture trust policy is now explicit: `real_capture` may support environment verification; `template_seeded`/`synthetic` are limited to wiring/parser-shape coverage and cannot promote `UNVERIFIED` assumptions.
- 2026-03-08: Local PAN-OS fixture collection is restricted to repo-owned read-only allowlist guard checks; arbitrary request classes/actions are disallowed by default.
- 2026-03-09: Local PAN-OS keygen preflight policy is fail-fast on credential/authz rejection with operator guidance; auth failure is treated separately from network reachability.
- 2026-03-09: Keygen auth guidance is emitted only for explicit `403 Invalid Credential`-class responses; other XML API keygen errors stay fail-fast but are reported as generic keygen/API failures.
- 2026-03-10: Live capture policy remains fail-fast: when keygen preflight does not return an API key, scenario collection is aborted immediately and no additional live capture scenarios are attempted.
- 2026-03-10: Dynamic log-query and config-xpath parameters in the collection harness are URL-encoded during live calls to avoid malformed URL failures while preserving read-only request guardrails.
- 2026-03-10: Real-capture `11.0.6-h1` evidence now supports partial promotion of base config XPath shape (`.../rulebase/security/rules` -> `<rules><entry ...>`), while query-token behavior remains unverified for deny/no-match claims.
- 2026-03-10: Additional bounded deny-focused `real_capture` run (`deny-hit_20260310T184847Z`) succeeded through keygen + submit job `217` + poll `FIN`, but poll returned `logs count="0"`; no deny/reset entry was captured, so query-token assumptions remain `UNVERIFIED`.
- 2026-03-10: One bounded operator-confirmed ICMP deny-target `real_capture` run (`deny-hit-icmp-management-servers_20260310T221249Z`) succeeded through keygen + submit job `278` + poll `FIN`, but poll returned `logs count="0"`; no qualifying deny/drop/policy-deny entry was captured, so query-token assumptions remain `UNVERIFIED`.
- 2026-03-10: Two-stage reproduction-coupled ICMP deny verification run attempted (`deny-hit-icmp-stage1-src-only_20260310T231306Z`): Stage 1 submit job `280` reached poll `FIN` with `logs count="0"`, so Stage 2 (`addr.dst` validation) was not run per fail-closed rule; `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-11: Two-stage reproduction-coupled ICMP deny verification run with exact log-signature filters attempted (`deny-hit-icmp-stage1-signature_20260311T010608Z`): Stage 1 submit job `281` reached poll `FIN` with `logs count="0"`, so Stage 2 (`addr.dst` validation) was not run per fail-closed rule; `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-11: Two-stage reproduction-coupled UDP deny verification run with exact deny-signature filters attempted (`deny-hit-udp-stage1-signature_20260311T012658Z`): Stage 1 submit job `390` reached poll `FIN` with `logs count="0"`, so Stage 2 (`addr.dst` + `port.dst` validation) was not run per fail-closed rule; `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-11: Self-contained UDP verification precondition failed for direct traffic generation: non-interactive SSH access to source host `10.1.99.10` was unavailable from this shell (`Permission denied` on tested users), so no additional Stage 1/Stage 2 capture was executed and assumptions remained unchanged.
- 2026-03-11: Operator-delegated bounded UDP generation run coupled with Stage 1 verification (`deny-hit-udp-stage1-signature-livegen_20260311T014031Z`) still returned poll `FIN` with `logs count="0"`; Stage 2 destination-token validation did not run and assumptions remained unchanged.
- 2026-03-11: Final bounded UDP verification with exact 60-second generation and two-pass Stage 1 confirmation (`deny-hit-udp-stage1a-live60_20260311T015054Z`, `deny-hit-udp-stage1b-post60_20260311T015148Z`) captured no qualifying deny entries in either Stage 1 pass; Stage 2 destination-token validation did not run and assumptions remained unchanged.
- 2026-03-11: Observability-first phase is now explicit: no further token-promotion attempts run until a completed fresh deny-row record exists for the current reproduction window; repeated zero-entry runs reframed the blocker from token mismatch to observability.
- 2026-03-11: Port-token guidance corrected in contract docs: PAN-OS traffic-log port fields are `sport`, `dport`, `natsport`, `natdport`; `port.src`/`port.dst` are not default candidates.
- 2026-03-11: Fresh live deny-row observability record captured for `11.0.6-h1` UDP path (`src=10.1.99.10`, `dst=10.1.20.20`, `dport=30053`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, `type=drop`, zones `management -> servers`) and stored in the observability template as the basis for the next bounded XML verification attempt.
- 2026-03-11: Executed one bounded observability-gated verification pair from the completed fresh deny-row record:
  - Stage 1 (`deny-hit-udp-obsgate-stage1_20260311T052621Z`) captured qualifying deny entries (job `444`, poll `FIN`, `logs count=\"20\"`) using row-derived signature without destination tokens.
  - Stage 2 (`deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`) captured the same deny signature (job `445`, poll `FIN`, `logs count=\"20\"`) with `addr.dst eq 10.1.20.20` and `dport eq 30053`.
  - Scenario-scoped promotion justified for `11.0.6-h1`: `addr.dst` and `dport` are now evidenced for this UDP deny signature under `capture_provenance=real_capture`; no cross-version/generalized promotion was made.
- 2026-03-11: Executed one additional bounded distinct-signature Stage 1 run from observability template (`src=10.1.99.3`, `dst=10.1.20.21`, `dport=30053`, `app=not-applicable`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, zones `management->servers`) with 15-minute receive-time bound and no destination-token clauses:
  - Stage 1 fixture: `deny-hit-udp-distinct-stage1_20260311T063652Z`
  - Stage 1 outcome: submit job `465`, poll `FIN`, `logs count=\"0\"`
  - Stage 2 execution: not run (required Stage 1 qualifying deny capture absent)
  - impact: no new token promotion; `addr.dst`/`dport` proof remains limited to the original obsgate UDP scenario pair.
- 2026-03-11: Re-ran one bounded distinct-signature Stage 1 from a freshly updated observability row (`src=10.1.99.3`, `dst=10.1.20.21`, `dport=30053`, `app=not-applicable`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, zones `management->servers`, type `drop`) with 15-minute receive-time bound and no destination-token clauses:
  - Stage 1 fixture: `deny-hit-tcp-distinct-stage1_20260311T064433Z`
  - Stage 1 outcome: submit job `472`, poll `FIN`, `logs count=\"0\"`
  - Stage 2 execution: not run (required Stage 1 qualifying deny capture absent)
  - impact: no extension beyond current scenario-scoped `addr.dst`/`dport` proof.
- 2026-03-11: Executed one bounded distinct-signature observe-and-validate orchestration run using `scripts/panos_observe_and_validate.py` and treated `VALIDATION_RESULT.json` as source of truth:
  - Observability record used: `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md` distinct row (`src=10.1.99.3`, `dst=10.1.20.21`, `dport=30053`, `app=not-applicable`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, zones `management->servers`, type `drop`).
  - Stage 1 fixture/result dir: `deny-hit-tcp-distinct-observe-validate-stage1_20260311T073259Z`
  - `VALIDATION_RESULT.json`: `observability_hit=false`, `matched_entry_count=0`, `reason_if_not_validated=no_qualifying_deny_row`
  - Stage 2 execution: not run by orchestrator (no qualifying Stage 1 deny row)
  - impact: no new token promotion; broader distinct-scenario behavior for `addr.dst`/`dport` remains `UNVERIFIED`.
- 2026-03-11: Executed one additional bounded distinct-signature orchestrator run with materially improved correlation inputs and machine-state gating:
  - command path: `scripts/panos_observe_and_validate.py` only (no ad hoc Stage 1/2 bypass)
  - distinct signature: `src=10.1.99.3`, `dst=10.1.20.21`, `dport=30053`, `app=not-applicable`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, zones `management->servers`
  - improved inputs supplied: `--session-id 0`, `--ui-filter-string "!( action eq 'allow' )"`, `--manual-observability-template docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`
  - loop-breaker state: not triggered (`blocked=false`, `prior_no_hit_count=0`, `improved_correlation_input=true`)
  - resulting fixture: `deny-hit-tcp-distinct-observe-validate-stage1_20260311T151256Z`
  - result outcome: `observability_hit=false`, `matched_entry_count=0`, `reason_if_not_validated=no_qualifying_deny_row`, no Stage 2 token validation
  - impact: no new token promotion; broader distinct-scenario behavior for `addr.dst`/`dport` remains `UNVERIFIED`.
- 2026-03-11: Added bounded orchestration workflow entrypoint `scripts/panos_observe_and_validate.py`:
  - generates bounded source traffic over SSH (or fails closed with one exact operator command if SSH unavailable),
  - runs Stage 1 broad deny observability sweep while traffic is active,
  - parses returned entries and selects freshest qualifying deny row,
  - runs independent Stage 2 token subqueries (`addr.dst`, `dport`) only after Stage 1 hit,
  - writes machine-readable `VALIDATION_RESULT.json` into the Stage 1 capture directory.
- 2026-03-11: Hardened orchestration state/gating:
  - always writes `OBSERVABILITY_RECORD.json` (success, no-hit, SSH unavailable, loop-breaker block, capture failure)
  - records attempt signature, loop-breaker state, run decision, and traffic-generation execution status
  - blocks repeated no-hit retries for materially identical attempt signatures unless correlation input improves (session ID, exact UI filter string, or manual supplement quality)
  - keeps manual template usage optional via `--manual-observability-template`
- 2026-03-11: Completed analysis-only postmortem of all versioned PAN-OS verification artifacts and generated coverage summaries:
  - machine-readable: `docs/fixtures/panos_verification/OBSERVABILITY_COVERAGE.json`
  - human-readable: `docs/fixtures/panos_verification/OBSERVABILITY_COVERAGE.md`
  - key decision: do not run more repeated no-hit distinct-signature attempts; next path is to acquire higher-confidence observability correlation evidence before any new live PAN-OS run.
- 2026-03-11: Implemented preferred pre-run correlation artifact workflow:
  - added `scripts/prepare_panos_observability_input.py` to normalize manual/CSV/JSON row evidence into `OBSERVABILITY_INPUT.json`
  - orchestrator now supports `--observability-input` and fails closed when provided artifact is not ready
  - loop-breaker now requires ready `OBSERVABILITY_INPUT.json` for repeated no-hit retries of materially identical signatures
  - manual markdown template remains optional supplemental context, not preferred machine input

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
- 2026-03-08: Ran `bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 4 tests).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/test_panos_verification_fixture_pack.py docs/fixtures/panos_verification/README.md docs/ai/REPO_MAP.md docs/ai/SOURCE_REFRESH.md IMPLEMENTATION_TRACKER.md` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 7 tests).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/panos_fixture_selector.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py -k "fixture_poll_shape_parses_log_entries_with_current_extractor"` (pass, 1 selected).
- 2026-03-08: Ran `uv run ruff check tests/adapters/test_panos_adapter.py tests/fixtures/panos_fixture_selector.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass; import order auto-fixed in `test_panos_adapter.py`).
- 2026-03-08: Ran `uv run ruff check tests/adapters/test_panos_adapter.py tests/fixtures/panos_fixture_selector.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass).
- 2026-03-08: Ran `bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py -k "fixture_poll_shape_parses_log_entries_with_current_extractor" tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 1 selected / 33 deselected due to targeted `-k` filter).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 13 tests).
- 2026-03-08: Ran `uv run ruff check tests/adapters/test_panos_adapter.py tests/fixtures/panos_fixture_selector.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass).
- 2026-03-08: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-08: Ran `uv run pytest -q tests/fixtures/test_panos_collection_harness.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py tests/adapters/test_panos_adapter.py -k "fixture_poll_shape_parses_log_entries_with_current_extractor or panos_collection_harness or panos_fixture_selector or verification_fixture_pack"` (pass, 17 tests; 20 deselected).
- 2026-03-08: Ran `uv run ruff check tests/fixtures/test_panos_collection_harness.py tests/fixtures/panos_fixture_selector.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py tests/adapters/test_panos_adapter.py` (pass).
- 2026-03-08: Attempted live harness run using `.env` credentials for `query-shape` real capture (`scripts/gather_panos_fixtures.sh ... --capture-label query-shape ...`) -> failed: PAN-OS XML API keygen returned `403 Invalid Credential`.
- 2026-03-08: Verified host resolution and TCP/443 connectivity now succeed for configured host; blocking condition is API authentication, not network reachability. No real-capture fixtures collected in this run.
- 2026-03-09: Ran `bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-09: Ran `uv run pytest -q tests/fixtures/test_panos_collection_harness.py` (initial run failed: 1 assertion mismatch after explicit error-text hardening; then pass after test update, 6 tests).
- 2026-03-09: Ran `uv run ruff check scripts/gather_panos_fixtures.sh tests/fixtures/test_panos_collection_harness.py docs/fixtures/panos_verification/README.md docs/ai/REPO_MAP.md docs/ai/SOURCE_REFRESH.md IMPLEMENTATION_TRACKER.md` (fails: ruff parses shell script as Python; command retired for this scope).
- 2026-03-09: Ran `uv run ruff check tests/fixtures/test_panos_collection_harness.py docs/fixtures/panos_verification/README.md docs/ai/REPO_MAP.md docs/ai/SOURCE_REFRESH.md IMPLEMENTATION_TRACKER.md` (pass).
- 2026-03-09: Ran `bash -n scripts/gather_panos_fixtures.sh && echo "bash -n OK"` (pass).
- 2026-03-10: Ran live harness preflight attempt using current `.env` credentials: `./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit" --dst "example.com" --dport "443" --hours "1"` -> fail-fast before capture (`ERROR: keygen response did not contain <key>; cannot continue.`).
- 2026-03-10: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-10: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 13 tests).
- 2026-03-10: Ran `uv run pytest -q tests/fixtures/test_panos_collection_harness.py` (pass, 6 tests).
- 2026-03-10: Ran live harness with current `.env` credentials after URL-encoding fix for bounded scenarios:
  - `deny-hit` (`--dst example.com --dport 443`) -> submit API error 17, no job-id/poll artifact
  - `no-match` (`--hours 1`) -> submit success, poll `FIN`, zero entries
  - `metadata-hit` (`--hours 1`) -> submit success, poll `FIN`, zero entries, config show/complete captured
  - `query-shape` (`--dst example.com --dport 443`) -> submit API error 17, no job-id/poll artifact
  - `xpath-shape` (`--hours 1`) -> submit success, poll `FIN`, zero entries, config show/complete captured
- 2026-03-10: Ran `uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_collection_harness.py` (initial fail: canonical poll fixture had zero entries and one partial capture dir lacked manifest; resolved by fixture-test marker update and partial-dir cleanup; final pass 20 tests).
- 2026-03-10: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py -k "real_capture_query_shape_selection_fails_closed_when_capture_incomplete or real_capture_xpath_shape_selection_is_provenance_gated or fixture_poll_shape_parses_log_entries_with_current_extractor"` (pass, 3 selected).
- 2026-03-10: Ran `uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py tests/fixtures/test_panos_fixture_selector.py tests/adapters/test_panos_adapter.py -k "real_capture or verification_fixture_pack"` (pass, 9 selected).
- 2026-03-10: Ran one bounded deny-focused live harness scenario with current `.env` credentials:
  - `set -a; source ./.env; set +a; ts=$(date -u -d '-1 hour' '+%Y/%m/%d %H:%M:%S'); q="(action neq allow) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit" --verification-scope "real_env_partial" --query "$q" --max-polls 10 --poll-interval 1`
  - outcome: keygen bootstrap succeeded, submit returned job `216`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no deny/reset entries), so no query-token promotions were made.
- 2026-03-10: Ran one additional bounded deny-focused live harness scenario with current `.env` credentials:
  - `set -a; source ./.env; set +a; ts=$(date -u -d '-6 hour' '+%Y/%m/%d %H:%M:%S'); q="(action neq allow) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit" --verification-scope "real_env_partial" --query "$q" --max-polls 10 --poll-interval 1`
  - outcome: keygen bootstrap succeeded, submit returned job `217`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no deny/reset entries), so no query-token promotions were made.
- 2026-03-10: Ran exactly one bounded operator-confirmed ICMP deny-target live harness scenario with current `.env` credentials:
  - `set -a; source ./.env; set +a; ts=$(date -u -d '-15 minutes' '+%Y/%m/%d %H:%M:%S'); q="(addr.src eq 10.1.99.3) and (addr.dst eq 10.1.20.180) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-icmp-management-servers" --verification-scope "real_env_partial" --query "$q" --max-polls 10 --poll-interval 1`
  - outcome: keygen bootstrap succeeded, submit returned job `278`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no entries), so deny/drop/policy-deny for the target was not observed and no query-token promotions were made.
- 2026-03-10: Ran two-stage reproduction-coupled ICMP deny verification (Stage 1 only; Stage 2 blocked by decision rule):
  - Stage 1 query used: `set -a; source ./.env; set +a; ts=$(date -u -d '-5 minutes' '+%Y/%m/%d %H:%M:%S'); q1="(addr.src eq 10.1.99.3) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-icmp-stage1-src-only" --verification-scope "real_env_partial" --query "$q1" --max-polls 10 --poll-interval 1`
  - Stage 1 outcome: keygen bootstrap succeeded, submit returned job `280`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no entries).
  - Stage 2 execution: not run (required Stage 1 qualifying deny entry was absent).
- 2026-03-11: Ran two-stage reproduction-coupled ICMP deny verification with exact signature constraints (Stage 1 only; Stage 2 blocked by decision rule):
  - Stage 1 query used: `set -a; source ./.env; set +a; ts=$(date -u -d '-5 minutes' '+%Y/%m/%d %H:%M:%S'); q1="(addr.src eq 10.1.99.3) and (app eq icmp) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-icmp-stage1-signature" --verification-scope "real_env_partial" --query "$q1" --max-polls 10 --poll-interval 1`
  - Stage 1 outcome: keygen bootstrap succeeded, submit returned job `281`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no entries).
  - Stage 2 execution: not run (required Stage 1 qualifying deny entry was absent).
- 2026-03-11: Ran two-stage reproduction-coupled UDP deny verification with signature constraints (Stage 1 only; Stage 2 blocked by decision rule):
  - Stage 1 query used: `set -a; source ./.env; set +a; ts=$(date -u -d '-5 minutes' '+%Y/%m/%d %H:%M:%S'); q1="(addr.src eq 10.1.99.10) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-udp-stage1-signature" --verification-scope "real_env_partial" --query "$q1" --max-polls 10 --poll-interval 1`
  - Stage 1 outcome: keygen bootstrap succeeded, submit returned job `390`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no entries).
  - Stage 2 execution: not run (required Stage 1 qualifying deny entry was absent).
- 2026-03-11: Attempted self-contained UDP traffic generation precondition for source host `10.1.99.10` before capture:
  - command: `for u in "$USER" root admin ubuntu; do ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$u@10.1.99.10" 'echo SSH_OK'; done`
  - outcome: all tested users returned `Permission denied (publickey,password)`; per run rule, no blind PAN-OS Stage 1/Stage 2 retry was performed.
- 2026-03-11: Ran two-stage UDP deny verification during operator-executed bounded traffic generation (Stage 1 only; Stage 2 blocked by decision rule):
  - operator traffic command in progress during capture: `python3 - <<'PY' ... send UDP datagrams to 10.1.20.20:30053 for ~25s ... PY`
  - Stage 1 query used: `set -a; source ./.env; set +a; ts=$(date -u -d '-5 minutes' '+%Y/%m/%d %H:%M:%S'); q1="(addr.src eq 10.1.99.10) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')"; ./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-udp-stage1-signature-livegen" --verification-scope "real_env_partial" --query "$q1" --max-polls 10 --poll-interval 1`
  - Stage 1 outcome: keygen bootstrap succeeded, submit returned job `401`, poll #1 returned `FIN`, poll payload had `logs count="0"` (no entries).
  - Stage 2 execution: not run (required Stage 1 qualifying deny entry was absent).
- 2026-03-11: Ran final bounded UDP verification with exact 60-second traffic generation and two-pass Stage 1:
  - traffic generation command used exactly: `python3 - <<'PY' ... dst=(\"10.1.20.20\", 30053) ... end=time.time()+60 ... sock.sendto(...) ... PY`
  - Stage 1A query (during active generation): `set -a; source ./.env; set +a; ts=$(date -u -d '-5 minutes' '+%Y/%m/%d %H:%M:%S'); q1=\"(addr.src eq 10.1.99.10) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')\"`
  - Stage 1A outcome: submit job `415`, poll `FIN`, `logs count=\"0\"` (`deny-hit-udp-stage1a-live60_20260311T015054Z`)
  - Stage 1B query (immediately post-generation, widened lookback): `set -a; source ./.env; set +a; ts=$(date -u -d '-15 minutes' '+%Y/%m/%d %H:%M:%S'); q1b=\"(addr.src eq 10.1.99.10) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '$ts')\"`
  - Stage 1B outcome: submit job `416`, poll `FIN`, `logs count=\"0\"` (`deny-hit-udp-stage1b-post60_20260311T015148Z`)
  - Stage 2 execution: not run (neither Stage 1A nor Stage 1B captured a qualifying deny entry).
- 2026-03-10: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-10: Ran `uv run pytest -q tests/fixtures/test_panos_collection_harness.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 20 tests).
- 2026-03-10: Ran `uv run pytest -q tests/adapters/test_panos_adapter.py` (pass, 23 tests).
- 2026-03-11: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 14 tests).
- 2026-03-11: Ran bounded Stage 1 live capture from completed observability record:
  - `q1="(addr.src eq 10.1.99.10) and (app eq not-applicable) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '2026/03/10 21:43:27')"`
  - `./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-udp-obsgate-stage1" --verification-scope "real_env_partial" --query "$q1" --max-polls 10 --poll-interval 1`
  - outcome: keygen path, submit job `444`, poll `FIN`, `logs count="20"` (qualifying deny entries captured).
- 2026-03-11: Ran bounded Stage 2 live capture after Stage 1 success:
  - `q2="(addr.src eq 10.1.99.10) and (app eq not-applicable) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '2026/03/10 21:43:27') and (addr.dst eq 10.1.20.20) and (dport eq 30053)"`
  - `./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-udp-obsgate-stage2-addrdst-dport" --verification-scope "real_env_partial" --query "$q2" --max-polls 10 --poll-interval 1`
  - outcome: keygen path, submit job `445`, poll `FIN`, `logs count="20"` (same deny signature captured with destination tokens).
- 2026-03-11: Ran one additional bounded distinct-signature Stage 1 capture (15m lookback, no destination tokens):
  - `q_distinct_stage1="(addr.src eq 10.1.99.3) and (from eq management) and (to eq servers) and (app eq not-applicable) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '2026/03/11 06:21:49')"`
  - `./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-udp-distinct-stage1" --verification-scope "real_env_partial" --query "$q_distinct_stage1" --max-polls 10 --poll-interval 1`
  - outcome: keygen path, submit job `465`, poll `FIN`, `logs count="0"`; Stage 2 not run per fail-closed rule.
- 2026-03-11: Re-ran bounded distinct-signature Stage 1 capture from refreshed observability row (15m lookback, no destination tokens):
  - `q_distinct_stage1_fresh="(addr.src eq 10.1.99.3) and (from eq management) and (to eq servers) and (app eq not-applicable) and (rule eq interzone-default) and (action eq deny) and (session_end_reason eq policy-deny) and (receive_time geq '2026/03/11 06:29:30')"`
  - `./scripts/gather_panos_fixtures.sh --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-tcp-distinct-stage1" --verification-scope "real_env_partial" --query "$q_distinct_stage1_fresh" --max-polls 10 --poll-interval 1`
  - outcome: keygen path, submit job `472`, poll `FIN`, `logs count="0"`; Stage 2 not run per fail-closed rule.
- 2026-03-11: Added orchestration logic/unit coverage:
  - `uv run pytest -q tests/fixtures/test_panos_observe_and_validate.py` (pass)
  - covers freshest deny-row selection, SSH-unavailable fail-closed path, no-observability-hit fail-closed path, token-validation result handling, and summary file writing.
- 2026-03-11: Ran orchestration + fixture validation slice after adding one-shot workflow:
  - `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass)
  - `uv run pytest -q tests/fixtures/test_panos_observe_and_validate.py tests/unit/test_panos_fixture_script.py tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 20 tests)
  - `uv run ruff check scripts/panos_observe_and_validate.py tests/fixtures/test_panos_observe_and_validate.py tests/unit/test_panos_fixture_script.py` (pass)
- 2026-03-11: Ran one bounded live orchestrator distinct-scenario execution:
  - `set -a && source ./.env && set +a && python3 scripts/panos_observe_and_validate.py --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-tcp-distinct-observe-validate" --source-ssh-target "root@10.1.99.3" --traffic-command "end=$((SECONDS+60)); while [ $SECONDS -lt $end ]; do nc -vz -w 3 10.1.20.21 30053 >/dev/null 2>&1 || true; sleep 0.5; done" --source-ip "10.1.99.3" --destination-ip "10.1.20.21" --destination-port 30053 --app "not-applicable" --rule "interzone-default" --action "deny" --session-end-reason "policy-deny" --zone-src "management" --zone-dst "servers" --lookback-minutes 15`
  - outcome: script exit code `11`, Stage 1 capture created, `VALIDATION_RESULT.json` reported `observability_hit=false`, no Stage 2 token queries executed.
- 2026-03-11: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-11: Ran `python3 -m py_compile scripts/panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 14 tests).
- 2026-03-11: Ran `python3 -m py_compile scripts/panos_observe_and_validate.py tests/fixtures/test_panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_panos_observe_and_validate.py` (pass, 7 tests).
- 2026-03-11: Ran `uv run ruff check scripts/panos_observe_and_validate.py tests/fixtures/test_panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh && python3 -m py_compile scripts/panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 14 tests).
- 2026-03-11: Ran `uv run ruff check scripts/panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `python3 scripts/summarize_panos_observability.py` (pass; wrote coverage JSON + MD artifacts).
- 2026-03-11: Ran `uv run ruff check scripts/summarize_panos_observability.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_prepare_panos_observability_input.py` (pass, 2 tests).
- 2026-03-11: Ran `uv run ruff check scripts/prepare_panos_observability_input.py tests/fixtures/test_prepare_panos_observability_input.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_prepare_panos_observability_input.py tests/fixtures/test_panos_observe_and_validate.py` (pass, 12 tests).
- 2026-03-11: Ran `uv run ruff check scripts/prepare_panos_observability_input.py scripts/panos_observe_and_validate.py tests/fixtures/test_prepare_panos_observability_input.py tests/fixtures/test_panos_observe_and_validate.py` (pass).
- 2026-03-11: Ran `python3 scripts/prepare_panos_observability_input.py ... --out docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json` (pass; artifact `ready_for_orchestrator=true`, `correlation_confidence=high`).
- 2026-03-11: Ran one bounded orchestrator attempt with observability-input gate:
  - `set -a && source ./.env && set +a && python3 scripts/panos_observe_and_validate.py --host "$PANOS_HOST" --username "$PANOS_USERNAME" --password "$PANOS_PASSWORD" --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" --capture-label "deny-hit-tcp-distinct-observe-validate-obsinput" --source-ssh-target "root@10.1.99.3" --traffic-command 'end=$((SECONDS+60)); while [ $SECONDS -lt $end ]; do nc -vz -w 3 10.1.20.21 30053 >/dev/null 2>&1 || true; sleep 0.5; done' --source-ip "10.1.99.3" --destination-ip "10.1.20.21" --destination-port 30053 --app "not-applicable" --rule "interzone-default" --action "deny" --session-end-reason "policy-deny" --zone-src "management" --zone-dst "servers" --lookback-minutes 15 --observability-input "docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json"`
  - outcome: exit `11`, `OBSERVABILITY_RECORD.json` + `VALIDATION_RESULT.json` written, `observability_hit=false`, no Stage 2 token subqueries.
- 2026-03-11: Ran `bash -n scripts/panos_readonly_guard.sh && bash -n scripts/gather_panos_fixtures.sh` (pass).
- 2026-03-11: Ran `python3 -m py_compile scripts/prepare_panos_observability_input.py scripts/panos_observe_and_validate.py scripts/summarize_panos_observability.py` (pass).
- 2026-03-11: Ran `uv run ruff check scripts/prepare_panos_observability_input.py scripts/panos_observe_and_validate.py scripts/summarize_panos_observability.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_panos_fixture_selector.py tests/fixtures/test_panos_verification_fixture_pack.py` (pass, 14 tests).
- 2026-03-11: Ran `python3 scripts/summarize_panos_observability.py` (pass; coverage updated to 23 analyzed runs, 20 no-hit, 2 observability records, 3 validation results).
- 2026-03-11: Ran `uv run pytest -q tests/fixtures/test_select_next_panos_candidate.py` (pass, 4 tests).
- 2026-03-11: Ran `uv run ruff check scripts/select_next_panos_candidate.py tests/fixtures/test_select_next_panos_candidate.py` (pass).
- 2026-03-11: Ran `uv run python scripts/select_next_panos_candidate.py` (pass; generated `NEXT_CANDIDATE_DECISION.json` + `.md` with single recommendation `pause_panos_token_expansion`).

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
- 2026-03-11: Added offline PAN-OS observability coverage summarizer script and artifacts to classify existing evidence and pick a single next path without launching a new live attempt.
- 2026-03-11: Added higher-confidence pre-run observability input path (`OBSERVABILITY_INPUT.json`) and wired orchestrator preflight + loop-breaker enforcement so repeated weak no-hit retries fail closed without ready machine-readable correlation evidence.
- 2026-03-11: One bounded distinct-signature run with ready observability input is now recorded as no-hit for `deny-hit-tcp-distinct-observe-validate-obsinput`; reruns for this same family are not recommended without materially stronger/newer correlation evidence.
- 2026-03-11: Coverage artifact refresh after the bounded observability-input run now shows `23` analyzed runs and `20` no-observability-hit outcomes; the single scenario-scoped `11.0.6-h1` UDP `addr.dst` + `dport` proof remains the only promoted destination-token evidence.
- 2026-03-11: Executed exactly one bounded distinct-signature attempt with ready `OBSERVABILITY_INPUT.json` (`deny-hit-tcp-distinct-observe-validate-obsinput-stage1_20260311T164815Z`); loop-breaker allowed run with improved correlation score, but Stage 1 still produced `observability_hit=false` and no token validation occurred.
- 2026-03-11: Added selector-driven family classification (`scripts/select_next_panos_candidate.py`) and decision artifacts (`NEXT_CANDIDATE_DECISION.json`/`.md`) so exhausted families are machine-marked and future live attempts are picked from selector output instead of ad hoc retries.
- 2026-03-11: Added compact `source_readiness_summary` surfacing in API/UI result output from persisted readiness data to reduce operator triage friction without changing verdict/classifier behavior.
- 2026-03-11: UI result route now normalizes dict-shaped persisted result payloads into `DiagnosticResult` before template rendering, so additive fields like `source_readiness_summary` render safely across mocked/test and DB-backed flows.
- 2026-03-11: SCM adapter readiness now uses a bounded auth probe (single token-endpoint request, short timeout, no retries) and emits explicit readiness states: `ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`.
- 2026-03-11: Worker source-readiness step now delegates SCM not-configured and probe diagnostics to the SCM adapter boundary rather than hardcoding SCM readiness fallback in the step.
- 2026-03-11: SD-WAN adapter readiness now uses a bounded single-request probe against configured SD-WAN API base URL with bearer token and explicit readiness states: `ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`.
- 2026-03-11: Worker source-readiness step now delegates SD-WAN configured/not-configured handling to the adapter boundary so persisted readiness diagnostics stay source-owned and explicit.
- 2026-03-11: Torq adapter readiness now uses a bounded single-request probe against configured Torq API base URL with explicit readiness states: `ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`.
- 2026-03-11: Worker source-readiness step now delegates Torq configured/not-configured handling to the adapter boundary so persisted readiness diagnostics stay source-owned and explicit.
- 2026-03-11: LogScale adapter readiness now uses a bounded single-request repository probe and reports explicit readiness states: `ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`.
- 2026-03-11: Worker source-readiness step now delegates LogScale configured/not-configured handling to the adapter boundary so persisted readiness diagnostics stay source-owned and explicit.
- 2026-03-11: Result load path now builds additive `source_readiness_details` from persisted `report_json.source_readiness` with safe normalization (`source`, `status`, optional `reason`, optional `latency_ms`) and malformed-entry filtering.
- 2026-03-11: Result page now renders compact “Source readiness details” block for per-source status/reason visibility, with fallback text when no details are present.
- 2026-03-11: Implemented bounded SD-WAN adapter readiness probe and mapped explicit readiness states into persisted `report_json.source_readiness`; scope remained readiness-only with no SD-WAN evidence-query expansion.
- 2026-03-11: Implemented bounded Torq adapter readiness probe and mapped explicit readiness states into persisted `report_json.source_readiness`; scope remained readiness-only with no Torq workflow/execution expansion.
- 2026-03-11: Implemented bounded LogScale adapter readiness probe and mapped explicit readiness states into persisted `report_json.source_readiness`; scope remained readiness-only with no LogScale query/evidence expansion, and enrichment-only authority boundaries were preserved.
- 2026-03-11: Tightened unknown-confidence explainability wording in API/UI to distinguish missing authoritative deny evidence, degraded source readiness, low path confidence, and inconclusive bounded checks; this pass is presentation-only and does not alter verdict logic/classifier/source-readiness behavior.
- 2026-03-11: Added bounded unknown-explainability operator review-pack workflow via `scripts/build_unknown_explainability_review.py`, generating `docs/review/UNKNOWN_EXPLAINABILITY_SAMPLES.json` and `docs/review/UNKNOWN_EXPLAINABILITY_REVIEW.md` from real persisted `ResultRow` unknown fixtures for structured feedback without runtime logic changes.
- 2026-03-11: Added structured unknown-explainability feedback workflow via `scripts/record_unknown_explainability_feedback.py`, with machine-readable append-safe `docs/review/UNKNOWN_EXPLAINABILITY_FEEDBACK.json` and grouped aggregate `docs/review/UNKNOWN_EXPLAINABILITY_FEEDBACK.md` for copy-only follow-up prioritization.
- 2026-03-11: Unknown-explainability wording follow-up is now parked pending real operator feedback; current feedback ledger has zero entries and cannot justify evidence-based copy changes yet.
- 2026-03-11: Authoritative-correlation now enforces SCM deny/decrypt authority gating (`source=scm`, `normalized.authoritative=true`, plus deny action or decrypt-error marker) before records can influence classification.
- 2026-03-11: Added unit coverage proving authoritative SCM deny/decrypt records are kept while non-authoritative SCM deny/decrypt and SCM allow records are excluded.
- 2026-03-12: SCM adapter now performs one bounded authenticated evidence retrieval request and emits normalized authoritative records only when SCM/Strata source-of-record, explicit `authoritative=true`, deny/decrypt-deny decision semantics, and bounded request-context matching are all present.
- 2026-03-12: Added SCM adapter tests for authoritative deny, authoritative decrypt-deny, non-authoritative/non-deny exclusion, malformed response exclusion, and auth/transport fail-closed behavior.
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py tests/unit/test_authoritative_correlation.py` (pass, 36 tests).
- 2026-03-12: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/scm/__init__.py tests/adapters/test_scm_adapter.py services/worker/am_i_blocked_worker/steps/authoritative_correlation.py tests/unit/test_authoritative_correlation.py` (pass).
- 2026-03-12: Added integration-style lifecycle proofs for authoritative SCM deny and authoritative SCM decrypt-deny records through submit -> queue -> worker -> persist -> API result retrieval using mock-only SCM adapter injection.
- 2026-03-12: Added bounded negative SCM lifecycle proof showing a deny-like SCM record with `authoritative=false` is dropped by authoritative correlation and does not produce a denied verdict through persisted API result retrieval.
- 2026-03-12: Added bounded malformed-shape SCM lifecycle proof showing a deny-like SCM candidate with malformed decision structure (no usable normalized deny action) fails closed and does not produce a denied verdict through persisted API result retrieval.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate missing source-of-record marker fails closed in normalization and yields no authoritative evidence records.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate with invalid non-SCM source marker fails closed in normalization and yields no authoritative evidence records.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate with valid SCM source marker and deny semantics still fails closed when destination is missing, yielding no authoritative evidence records.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate with valid SCM source marker and deny semantics still fails closed when destination is present but blank/whitespace-only, yielding no authoritative evidence records.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate with valid SCM source marker and deny semantics still fails closed when destination is present but object-typed/unusable, yielding no authoritative evidence records.
- 2026-03-12: Added bounded SCM adapter unit proof showing a deny-like authoritative candidate with valid SCM source marker and deny semantics still fails closed when timestamp is present but object-typed/non-string, yielding no authoritative evidence records.
- 2026-03-12: Consolidated remaining SCM normalization fail-closed gaps into one table-driven adapter unit batch proving deny-like authoritative candidates are dropped when critical fields are malformed/missing for `port` (missing/object-typed) and `timestamp` (missing), ending the one-field-per-run micro-loop.
- 2026-03-12: Added integration-style lifecycle proof that mixed source readiness states survive submit -> queue -> worker -> persist -> API result retrieval, with persisted `source_readiness` yielding expected `source_readiness_summary` and `source_readiness_details` in result output.
- 2026-03-12: Added lifecycle integration proof for fallback readiness-status derivation end-to-end: persisted mixed readiness entries with `available` but no explicit `status` now have retrieval assertions for `ready`/`unavailable` fallback statuses (plus optional `unknown` fallback when both fields are absent).
- 2026-03-12: Added lifecycle integration proof that `source_readiness_details` omits meaningless entries with no readiness keys while valid explicit/fallback entries still survive persistence and API retrieval; `source_readiness_summary` remains correct for valid availability signals.
- 2026-03-12: Added lifecycle integration proof that non-dict readiness entries are classified under `unknown_sources` in summary and excluded from details, plus a tiny runtime hardening in `ReadinessReport` dict-guards to prevent worker crashes on malformed readiness shapes.
- 2026-03-12: Added lifecycle integration proof that persisted readiness shaping survives into `/result/evidence-bundle`: mixed explicit/fallback/degraded source-readiness summary/details match between normal result API and evidence-bundle payload without schema expansion.
- 2026-03-12: Added lifecycle integration proof that `/result/evidence-bundle` preserves authoritative observed-fact metadata (PAN-OS `detail.rule_metadata`) with parity to normal result retrieval, while readiness summary/details remain present and unchanged.
- 2026-03-12: Added lifecycle integration proof that unknown-confidence explainability signals (`unknown_reason_signals`) survive persisted retrieval parity into `/result/evidence-bundle` alongside readiness summary/details for an unknown verdict case.
- 2026-03-12: Added lifecycle failure-path proof for submit -> queue -> worker failure -> persist -> API request-detail retrieval: controlled source-readiness-step exception now verifies persisted `failure_reason`, normalized `failure_stage`, and normalized `failure_category` visibility in `GET /api/v1/requests/{id}`.
- 2026-03-12: Added bounded request-detail route contract proof that malformed persisted audit metadata (`stage`/`category`) is normalized to `unknown` in `GET /api/v1/requests/{id}` while preserving `failure_reason`.
- 2026-03-12: Added bounded route contract proof that denied-path `/result/evidence-bundle` retrieval remains attachment-available and preserves authoritative PAN-OS observed-fact metadata (`detail.rule_metadata`) plus readiness summary/details.
- 2026-03-12: Added bounded route contract proof that `unknown`-verdict `unknown_reason_signals` are preserved with parity between `GET /api/v1/requests/{id}/result` and `GET /api/v1/requests/{id}/result/evidence-bundle`, while readiness summary/details remain unchanged and bundle attachment semantics remain intact.
- 2026-03-12: Added bounded worker unit mapping-stability proof that `_failure_category_for_stage` preserves the current normalized `FailureStage -> FailureCategory` taxonomy across all `FailureStage` enum values, preventing silent drift in failure metadata categorization.
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 10 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 12 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 14 tests).
- 2026-03-12: Ran `uv run pytest -q tests/unit/test_authoritative_correlation.py` (pass, 12 tests).
- 2026-03-12: Ran `uv run ruff check tests/fixtures/test_lifecycle_integration.py` (pass).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 26 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 28 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 30 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 32 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 34 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 36 tests).
- 2026-03-12: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py` (pass, 42 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 16 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 18 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 20 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 22 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 24 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 26 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 28 tests).
- 2026-03-12: Ran `uv run pytest -q tests/fixtures/test_lifecycle_integration.py` (pass, 30 tests).
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 49 tests).
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 50 tests).
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 51 tests).
- 2026-03-12: Ran `uv run pytest -q tests/unit/test_pipeline.py` (pass, 16 tests).
- 2026-03-12: Ran `uv run ruff check tests/adapters/test_scm_adapter.py` (pass).
- 2026-03-12: Ran `uv run ruff check tests/fixtures/test_lifecycle_integration.py` (pass).
- 2026-03-12: Ran `uv run ruff check tests/fixtures/test_lifecycle_integration.py services/worker/am_i_blocked_worker/steps/source_readiness_check.py` (pass).
- 2026-03-12: Ran `uv run ruff check tests/routes/test_api_routes.py` (pass).
- 2026-03-12: Ran `uv run ruff check tests/unit/test_pipeline.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "source_readiness or unknown_reason_signals"` (pass, 2 selected).
- 2026-03-11: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "load_result_record_unknown_derives_reasons_from_confidence_and_readiness or load_result_record_unknown_handles_missing_or_malformed_confidence_values"` (pass, 4 selected).
- 2026-03-11: Ran `uv run pytest -q tests/routes/test_api_routes.py` (pass, 43 tests).
- 2026-03-11: Ran `uv run ruff check services/api/am_i_blocked_api/routes/api.py packages/core/am_i_blocked_core/models.py tests/routes/test_api_routes.py` (pass).
- 2026-03-11: Ran `uv run ruff check services/api/am_i_blocked_api/routes/api.py services/api/am_i_blocked_api/routes/ui.py packages/core/am_i_blocked_core/models.py tests/routes/test_api_routes.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/adapters/test_scm_adapter.py tests/unit/test_source_readiness_check.py` (pass, 22 tests).
- 2026-03-11: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/scm/__init__.py services/worker/am_i_blocked_worker/steps/source_readiness_check.py tests/adapters/test_scm_adapter.py tests/unit/test_source_readiness_check.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/adapters/test_sdwan_adapter.py tests/unit/test_source_readiness_check.py` (pass, 28 tests).
- 2026-03-11: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/sdwan/__init__.py services/worker/am_i_blocked_worker/steps/source_readiness_check.py tests/adapters/test_sdwan_adapter.py tests/unit/test_source_readiness_check.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/adapters/test_torq_adapter.py tests/unit/test_source_readiness_check.py` (pass, 32 tests).
- 2026-03-11: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/torq/__init__.py services/worker/am_i_blocked_worker/steps/source_readiness_check.py tests/adapters/test_torq_adapter.py tests/unit/test_source_readiness_check.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/adapters/test_logscale_adapter.py tests/unit/test_source_readiness_check.py` (pass, 34 tests).
- 2026-03-11: Ran `uv run ruff check packages/adapters/am_i_blocked_adapters/logscale/__init__.py services/worker/am_i_blocked_worker/steps/source_readiness_check.py tests/adapters/test_logscale_adapter.py tests/unit/test_source_readiness_check.py` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "source_readiness"` (pass).
- 2026-03-11: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "load_result_record_unknown_derives_reasons_from_confidence_and_readiness or load_result_record_unknown_handles_missing_or_malformed_confidence_values"` (pass).
- 2026-03-11: Ran `uv run ruff check packages/core/am_i_blocked_core/models.py services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).
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
- 2026-03-08: Enhanced `scripts/gather_panos_fixtures.sh` and fixture docs to support versioned capture sets, capture metadata manifests, and canonical fixture mirrors for repeatable multi-version evidence collection.
- 2026-03-08: Added `tests/fixtures/panos_fixture_selector.py` helper so tests can resolve versioned fixture captures by `version + scenario`, and extended capture script auth to support API-key generation from username/password when needed.
- 2026-03-08: Wired one existing PAN-OS adapter fixture-alignment test to load fixtures through `select_versioned_capture(version, scenario)` and assert capture manifest metadata for explicit test provenance.
- 2026-03-08: Hardened fixture-manifest trust schema and selector gating so provenance/scope filters are explicit, fail-closed, and cannot silently downgrade real-capture verification requirements.
- 2026-03-08: Added a repo-owned read-only PAN-OS request guard and wired fixture collection through it; added harness tests with fake-curl execution to verify disallowed-action rejection and sanitized real-capture manifest output.
- 2026-03-08: Live real-capture collection attempt is currently blocked by PAN-OS API auth failure (`403 Invalid Credential` on keygen); assumptions remain `UNVERIFIED` pending valid API-auth-capable credentials or API key.
- 2026-03-09: Hardened keygen preflight failure handling so auth rejection is explicit, fail-fast, and accompanied by bounded operator guidance (API key preferred path + XML API role prerequisites).
- 2026-03-09: Tightened keygen auth-failure precision so only explicit `403 Invalid Credential` responses trigger auth guidance; added harness coverage for non-auth XML keygen errors to keep failure classification clear and fail-fast.
- 2026-03-10: Executed bounded live harness run with current credentials; keygen preflight returned no API key and capture stopped immediately. No real-capture scenario packs were generated and no PAN-OS assumptions were promoted.
- 2026-03-10: Fixed collection-harness malformed URL failure by URL-encoding dynamic query/xpath parameters; collected real-capture `11.0.6-h1` scenario packs and added strict real-provenance verification tests for assumption-promotion gating.
- 2026-03-10: Executed one bounded deny-focused real-capture scenario for `11.0.6-h1` (`action neq allow` + 1h window); capture path was healthy (keygen + job + poll `FIN`) but returned zero poll entries, so `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-10: Executed one additional bounded deny-focused real-capture scenario for `11.0.6-h1` (`action neq allow` + 6h window); capture path was healthy (keygen + job + poll `FIN`) but returned zero poll entries, so `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-10: Executed exactly one bounded real-capture attempt for operator-confirmed denied ICMP path (`src=10.1.99.3`, `dst=10.1.20.180`, `action=deny`, `session_end_reason=policy-deny`, 15m window); capture path was healthy (keygen + job + poll `FIN`) but returned zero poll entries, so `addr.dst`/`port.dst` remain `UNVERIFIED`.
- 2026-03-10: Executed reproduction-coupled two-stage ICMP deny verification policy for `11.0.6-h1`; Stage 1 (5m, source+deny+policy-deny) returned zero entries, so Stage 2 (`addr.dst`) was intentionally not run and no assumption promotions were made.
- 2026-03-11: Executed reproduction-coupled two-stage ICMP deny verification policy with exact signature filters (`app=icmp`, `rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`); Stage 1 returned zero entries, so Stage 2 (`addr.dst`) was intentionally not run and no assumption promotions were made.
- 2026-03-11: Executed reproduction-coupled two-stage UDP deny verification policy with exact signature filters (`rule=interzone-default`, `action=deny`, `session_end_reason=policy-deny`, source bound); Stage 1 returned zero entries, so Stage 2 (`addr.dst` + `port.dst`) was intentionally not run and no assumption promotions were made.
- 2026-03-11: Self-contained run policy decision: when direct non-interactive source-host execution is unavailable, fail closed and return one exact operator traffic-generation command instead of running blind capture attempts.
- 2026-03-11: Even with bounded operator-generated UDP traffic in flight, Stage 1 deny-signature query still returned zero entries in the 5-minute window; destination-token promotion remains blocked until Stage 1 can capture at least one qualifying deny event.
- 2026-03-11: Final bounded run used exact 60-second UDP generation plus Stage 1A/1B confirmation windows; both Stage 1 passes returned zero entries, so Stage 2 remained blocked and destination-token assumptions were not promoted.
- 2026-03-11: Final 60-second generation + Stage 1A/1B confirmation still returned zero qualifying deny entries, which currently points to deny-event observability/log visibility in XML results as the blocker rather than destination-token validation behavior.
- 2026-03-11: Candidate-family selection policy is now machine-driven; families can be marked `exhausted_pending_new_evidence` and must not be retried without materially stronger/newer evidence (known exhausted family: `10.1.99.3|10.1.20.21|30053|not-applicable|unknown|interzone-default|policy-deny|ssh_custom_command`).
- 2026-03-11: Added observability-first checklist template (`docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`) requiring fresh live deny-row evidence capture before any further bounded XML destination-token validation attempt.
- 2026-03-11: Minimal runtime/query-token reconciliation completed: PAN-OS adapter `_build_traffic_query(...)` now uses `dport` (not `port.dst`) for destination-port filtering, aligned to scenario-scoped `11.0.6-h1` UDP deny real-capture evidence.
- 2026-03-12: Reconciled stale next-task guidance: the suggested `FailureStage -> FailureCategory` mapping-stability proof already exists on `main` (`tests/unit/test_pipeline.py::test_failure_stage_to_category_mapping_is_stable`), so work pivoted to a non-contract MVP increment.
- 2026-03-12: Added bounded operator-facing `observed_fact_summary` shaping in result API/UI (authority vs enrichment counts and source lists derived from persisted `report_json.observed_facts`) with focused route/load tests and docs updates.
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "observed_fact_summary or load_result_record"` (pass, 10 selected).
- 2026-03-12: Ran `uv run ruff check packages/core/am_i_blocked_core/models.py services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).
- 2026-03-12: Added bounded API/UI routing-context surfacing: result context block now renders `routing_recommendation.reason` when present, and API result shaping now normalizes malformed/empty routing reason values to a safe fallback (`loaded from persisted result`) without changing routing semantics.
- 2026-03-12: Added focused route/UI coverage for routing-recommendation reason present and absent rendering behavior plus loader-level malformed/null routing reason normalization.
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "routing_recommendation_reason or load_result_record_handles_missing_or_null_routing_reason_gracefully"` (pass, 8 selected).
- 2026-03-12: Ran `uv run ruff check services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).
- 2026-03-12: Added bounded API/UI time-window handoff surfacing: result payload now carries `time_window_start`/`time_window_end` from request context, and result-page context block now renders compact `Time window` output for range/partial availability while hiding the line when both values are absent.
- 2026-03-12: Added focused route/UI tests for time-window context behavior: both values present, partial availability, and both missing; API result shaping coverage now verifies normalized start/end propagation and graceful `null` handling.
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "time_window"` (pass, 7 selected).
- 2026-03-12: Ran `uv run ruff check packages/core/am_i_blocked_core/models.py services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).
- 2026-03-12: Added bounded API/UI destination handoff surfacing: result payload now carries `destination_value` and optional `destination_port` from request context, and result-page context block now renders compact `Destination` output for destination-only/destination+port and hides when destination is missing.
- 2026-03-12: Added focused route/UI tests for destination context behavior: destination only, destination + port, and destination missing; API result shaping coverage now verifies graceful `null` handling.
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "destination"` (pass, 9 selected).
- 2026-03-12: Ran `uv run ruff check packages/core/am_i_blocked_core/models.py services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).
- 2026-03-12: Added bounded handoff-context consolidation slice by surfacing `destination_type` in `/api/v1/requests/{id}/result` and rendering destination as compact `value[:port] (type)` in existing context block when available.
- 2026-03-12: Added one compact consolidated route/UI contract proof for the operator handoff context block (routing reason + destination value/port/type + time window) to break one-field-at-a-time context slicing.
- 2026-03-12: Ran `uv run pytest -q tests/routes/test_api_routes.py -k "destination_type or handoff_context or destination_context"` (pass, 7 selected).
- 2026-03-12: Ran `uv run ruff check packages/core/am_i_blocked_core/models.py services/api/am_i_blocked_api/routes/api.py tests/routes/test_api_routes.py` (pass).

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

Pause result-context field additions; add one bounded non-context MVP slice (for example, compact operator-facing result API contract test that verifies all current handoff fields remain stable across `/result` and evidence-bundle retrieval paths).

## Deferred / Later

- SCM/Prisma deepening after first authoritative PAN-OS path is complete.
- SD-WAN deeper path-health enrichment after core deny authority path is live.
- LogScale query-job implementation only after explicit verification and intentional scope expansion.
- Torq outbound enrichment after core verdict path is stable.
- Multi-destination flows, broad UI work, and platform expansion (out of MVP scope).
