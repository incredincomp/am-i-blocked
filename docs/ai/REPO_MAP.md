# REPO_MAP.md

## Purpose

Living repository map for AI agents. Keep this aligned to real code paths, import names, and run commands.

## Top-Level Directories

- `packages/core`: shared models, enums, config, DB models (`am_i_blocked_core` import package).
- `packages/adapters`: adapter interfaces and vendor stubs (`am_i_blocked_adapters` import package).
- `services/api`: FastAPI web/API service (`am_i_blocked_api` import package).
- `services/worker`: async worker + diagnostic pipeline (`am_i_blocked_worker` import package).
- `migrations`: Alembic environment + revisions.
- `infra`: Docker Compose and `.env.example`.
- `tests`: unit, routes, fixtures, adapter contract tests.
- `docs` and `docs/ai`: architecture and agent-grounding docs.
- `docs/review`: operator review packs generated from repo-owned persisted result samples for bounded feedback workflows.
- `docs/fixtures/panos_verification`: sanitized PAN-OS XML verification fixture pack templates plus versioned evidence-capture folders (`versions/<panos_version>/<capture_label>_<timestamp>/`).
- `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`: optional manual observability supplement (not required for every orchestrator run).
- `docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json`: preferred machine-readable pre-run correlation artifact for stronger observability evidence.

## Package Import Names

- `am_i_blocked_core`
- `am_i_blocked_adapters`
- `am_i_blocked_api`
- `am_i_blocked_worker`

## App Entrypoints

- API ASGI app: `am_i_blocked_api:app` defined in `services/api/am_i_blocked_api/__init__.py`.
- Worker process: `python -m am_i_blocked_worker.main` (`services/worker/am_i_blocked_worker/main.py`).
- Pipeline orchestrator: `services/worker/am_i_blocked_worker/pipeline.py` (`run_diagnostic`).
- API routes: `services/api/am_i_blocked_api/routes/api.py` and `services/api/am_i_blocked_api/routes/ui.py`.

## Queue / Job Flow (Current vs Target)

- Current:
- API persists requests to Postgres on submit and uses DB-backed lookup for request/result endpoints.
- API returns explicit degraded (`503`) responses when persistence dependencies are unavailable.
- API now enqueues submitted diagnostics to Redis (`am_i_blocked:jobs`).
- API `/api/v1/readyz` now performs live DB (`SELECT 1`) and Redis (`PING`) checks.
- Worker main loop now dequeues Redis jobs and dispatches `run_diagnostic`.
- Worker startup now performs one DB/Redis readiness check and logs the result.
- Pipeline step 7 writes `requests.status` and `result.report_json` to Postgres as the operational persistence path.
- Pipeline no longer carries `request_store`/`result_store` in-memory request/result parameters; persistence failures now fail the job and are tracked via failed request status metadata.
- Failed status transitions are written to `audit` with structured metadata (`reason`, `stage`, `category`) using bounded enums (`FailureStage`, `FailureCategory`) and read back by API/UI (`failure_reason`, `failure_stage`, `failure_category`).
- UI request page maps normalized failure stage/category to compact first-hop triage hints while preserving raw failure values in the rendered metadata.
- Result evidence cards now visually distinguish observed facts tagged as enrichment-only vs authoritative using observed-fact detail metadata.
- Result evidence cards now also render minimal PAN-OS metadata from persisted observed-fact detail when authoritative PAN-OS deny facts include `detail.rule_metadata`.
- Unknown verdicts now render compact confidence explainability (`path_confidence`, `evidence_completeness`, `unknown_reason_signals`) in the result page "Why this is unknown" section, including explicit copy that `unknown` is not equivalent to `allowed`.
- Pipeline itself is implemented and exercised in tests via direct calls.
- Target MVP:
- API persists + enqueues.
- Worker dequeues + runs `run_diagnostic`.
- Persist step writes durable results.

## Migration Locations

- Alembic config: `alembic.ini`
- Alembic env: `migrations/env.py`
- Revisions: `migrations/versions/*.py`
- DB models: `packages/core/am_i_blocked_core/db_models.py`

## Config and Env Loading Paths

- Settings class: `packages/core/am_i_blocked_core/config.py`
- Loader: `am_i_blocked_core.config.get_settings()`
- Source: environment variables and optional `.env` (via Pydantic settings config)
- Example env: `infra/.env.example`

## Test Layout

- `tests/unit`: step and classifier unit tests.
- `tests/routes`: FastAPI API/route tests.
- `tests/routes/test_api_routes.py`: includes route/UI checks for PAN-OS metadata render behavior (present, absent, malformed).
- `tests/routes/test_api_routes.py`: also covers unknown-confidence explainability rendering, `source_readiness_summary` surfacing in API/UI results, and persisted-result fallback handling for missing/malformed confidence values.
- `tests/fixtures`: pipeline integration-style tests with mocked adapters/readiness.
- `tests/fixtures/test_lifecycle_integration.py`: integration-style submit -> queue -> worker -> persist -> API result retrieval + UI render coverage with controlled PAN-OS deny/no-authoritative-evidence outcomes, including persisted PAN-OS metadata present/malformed lifecycle assertions.
- `tests/fixtures/test_panos_verification_fixture_pack.py`: fixture-pack scaffolding validation (required PAN-OS XML sample files exist, parse, and contain minimum structural markers).
- `tests/fixtures/panos_fixture_selector.py`: helper for selecting versioned PAN-OS captures by `version + scenario` with provenance/scope gating (`require_provenance`, `minimum_verification_scope`) and strict manifest validation.
- `tests/fixtures/test_panos_fixture_selector.py`: unit coverage for version/scenario fixture selection and manifest parsing.
- `tests/fixtures/test_panos_collection_harness.py`: harness safety tests for read-only allowlist enforcement and real-capture manifest/sanitization behavior using fake `curl`.
- `tests/fixtures/test_panos_observe_and_validate.py`: orchestration logic tests for bounded observe-and-validate flow (freshest deny-row matching, always-written observability records, SSH-unavailable/no-hit fail-closed behavior, loop-breaker gating, optional manual template handling, and token-result handling).
- `scripts/gather_panos_fixtures.sh`: helper to capture sanitized PAN-OS XML samples, write versioned fixture packs, and mirror canonical required fixture files.
- `scripts/panos_observe_and_validate.py`: bounded one-shot orchestrator that runs source-host traffic generation + Stage 1 observability sweep + Stage 2 token subqueries (`addr.dst` and `dport`) and writes both `OBSERVABILITY_RECORD.json` (primary run-state/gating artifact) and `VALIDATION_RESULT.json`.
- `scripts/panos_observe_and_validate.py`: supports optional `--observability-input` preflight gating; when repeated no-hit signatures exist, ready `OBSERVABILITY_INPUT.json` is required for retried identical signatures.
- `scripts/prepare_panos_observability_input.py`: helper to normalize session/filter/structured row evidence (manual, CSV, or JSON input) into `OBSERVABILITY_INPUT.json` with readiness/confidence flags.
- `scripts/summarize_panos_observability.py`: offline artifact summarizer that classifies versioned PAN-OS verification runs and writes coverage outputs (`OBSERVABILITY_COVERAGE.json` and `OBSERVABILITY_COVERAGE.md`) without making live PAN-OS calls.
- `scripts/select_next_panos_candidate.py`: offline selector that classifies signature families (`proven`, `candidate`, `exhausted_pending_new_evidence`, `blocked_by_loop_breaker`) from coverage + versioned observability artifacts and writes `NEXT_CANDIDATE_DECISION.json`/`.md` with exactly one primary recommendation.
- `scripts/panos_readonly_guard.sh`: read-only PAN-OS XML request allowlist guard used by fixture collection harness and testable via `--assert`.
- `scripts/build_unknown_explainability_review.py`: extracts persisted `unknown` `ResultRow` fixtures from route tests and generates `docs/review/UNKNOWN_EXPLAINABILITY_SAMPLES.json` plus `docs/review/UNKNOWN_EXPLAINABILITY_REVIEW.md` for structured operator wording feedback.
- `scripts/record_unknown_explainability_feedback.py`: records partial-safe operator feedback against known sample IDs into `docs/review/UNKNOWN_EXPLAINABILITY_FEEDBACK.json` and generates grouped aggregate summary output in `docs/review/UNKNOWN_EXPLAINABILITY_FEEDBACK.md`.
- `tests/adapters`: adapter contract tests (`BaseAdapter` compliance).
- `tests/adapters/test_scm_adapter.py`: bounded SCM readiness probe coverage for state mapping (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`).
- `tests/adapters/test_sdwan_adapter.py`: bounded SD-WAN readiness probe coverage for state mapping (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`).
- `tests/adapters/test_torq_adapter.py`: bounded Torq readiness probe coverage for state mapping (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`).
- `tests/adapters/test_logscale_adapter.py`: bounded LogScale readiness probe coverage for state mapping (`ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`) and enrichment-only evidence contract preservation.
- `tests/adapters/test_panos_adapter.py`: PAN-OS XML traffic-log job submission/polling behavior (success, timeout, no-match, malformed XML).
- `tests/adapters/test_panos_adapter.py`: also covers PAN-OS rule metadata lookup behavior (success, no-match, malformed response, timeout/failure) and graceful deny-path behavior when metadata lookup fails.
- `tests/adapters/test_panos_adapter.py`: includes PAN-OS fixture-pack alignment checks proving current parser assumptions match fixture submit/poll/metadata XML shapes.
- `tests/adapters/test_panos_adapter.py`: fixture poll-alignment test now uses `select_versioned_capture(version=\"11.0.2\", scenario=\"deny-hit\")` + manifest loading as canonical versioned-fixture pattern.
- `tests/adapters/test_panos_adapter.py`: now also includes real-capture trust-gated checks for `11.0.6-h1` (`require_provenance=\"real_capture\"`) proving fail-closed behavior on incomplete `query-shape` capture and partial XPath-shape evidence selection.
- `tests/unit/test_authoritative_correlation.py`: step-level PAN-OS authoritative gating tests (deny accepted, non-deny/malformed/timeout/no-match excluded).
- `tests/unit/test_source_readiness_check.py`: readiness-step coverage including LogScale configured/unconfigured paths.

## Commands

- `make install`
- `make run-api`
- `make run-worker`
- `make migrate`
- `make test`
- `make test-cov`
- `make lint`
- `make docker-up`

## Known Architectural Seams

- Adapter abstraction in `packages/adapters/am_i_blocked_adapters/base.py`.
- PAN-OS adapter now contains XML log-job submit/poll helpers, conservative deny/reset normalization, and optional XML config-based `lookup_rule_metadata(...)` enrichment in `packages/adapters/am_i_blocked_adapters/panos/__init__.py`.
- SCM adapter readiness now performs a bounded auth probe (single token-endpoint request) and reports explicit readiness states in `source_readiness` without expanding SCM evidence-query scope.
- LogScale adapter readiness now performs a bounded repository probe request and reports explicit readiness states in `source_readiness` without expanding LogScale evidence-query scope or authority semantics.
- SD-WAN adapter readiness now performs a bounded single-request probe against configured SD-WAN API base URL and reports explicit readiness states in `source_readiness` without expanding SD-WAN evidence-query scope.
- Torq adapter readiness now performs a bounded single-request probe against configured Torq API base URL and reports explicit readiness states in `source_readiness` without expanding Torq workflow/execution scope.
- PAN-OS traffic-log destination token validation remains observability-gated for new attempts; latest real-capture Stage 1/Stage 2 pair for `11.0.6-h1` UDP deny signature (`deny-hit-udp-obsgate-stage1_20260311T052621Z`, `deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`) provides scenario-scoped evidence for `addr.dst` + `dport`.
- PAN-OS traffic-log field-name guidance for future validation is `sport`, `dport`, `natsport`, `natdport`; `port.src`/`port.dst` are not default candidates.
- PAN-OS runtime query construction now uses `addr.dst` + `dport` for destination filtering in the adapter query builder, aligned to scenario-scoped `11.0.6-h1` UDP deny real-capture evidence.
- PAN-OS one-shot orchestration now supports bounded observability-first validation in a single run while preserving fail-closed semantics: Stage 2 token checks run only when Stage 1 captures a qualifying deny row.
- Orchestrator loop-breaker state is machine-recorded and enforced for repeated no-hit retries on materially identical attempt signatures, and repeated retries now require ready `OBSERVABILITY_INPUT.json` as the preferred evidence-quality improvement path.
- PAN-OS metadata XPath shape remains explicitly `UNVERIFIED`/version-dependent pending target-environment capture; no PAN-OS version pin/source file exists in repo config today.
- PAN-OS fixture pack currently validates parser shape expectations (`.//job`, `.//status`, `.//logs/entry`, `.//entry[@name]`) but does not independently verify version-specific query-field/XPath correctness.
- Fixture helper supports explicit capture labels, optional destination/port/time-window query generation, API-key or keygen-based auth (`--username`/`--password` fallback), and per-capture metadata manifests with required trust fields (`capture_provenance`, `verification_scope`, `panos_version_source`).
- Fixture helper now URL-encodes dynamic XML API query/xpath values via curl `--data-urlencode` for live collection safety (prevents malformed URL failures on bounded query strings) while preserving read-only guardrails.
- Keygen bootstrap preflight is fail-fast on explicit PAN-OS XML API auth rejection signatures (`403 Invalid Credential`) with operator guidance for API-key mode and XML-API-role prerequisites; non-auth XML keygen errors fail fast with generic keygen/API error messaging, and no invalid-credential retry loop is used.
- Current local-firewall run state: keygen preflight succeeds with current `.env` credentials, and real-capture versioned scenarios now exist for PAN-OS `11.0.6-h1` (`deny-hit`, `no-match`, `metadata-hit`, `query-shape`, `xpath-shape`, `deny-hit-icmp-management-servers`, `deny-hit-icmp-stage1-src-only`, `deny-hit-icmp-stage1-signature`, `deny-hit-udp-stage1-signature`) with mixed completeness by scenario; latest two-stage UDP signature-coupled run stopped after Stage 1 (`deny-hit-udp-stage1-signature_20260311T012658Z`) because submit+poll `FIN` returned zero log entries, so Stage 2 destination-token validation was not executed.
- Latest self-contained UDP verification precondition check: non-interactive SSH execution to source host `10.1.99.10` was unavailable from the current shell in this run, so bounded traffic generation could not be started directly and no additional PAN-OS capture stage was executed.
- Latest operator-delegated UDP verification run (`deny-hit-udp-stage1-signature-livegen_20260311T014031Z`) executed during bounded source-host traffic generation, but Stage 1 still returned submit+poll `FIN` with zero log entries; Stage 2 destination-token validation did not run.
- Latest final bounded UDP verification used exact 60-second generation plus two-pass Stage 1 (`deny-hit-udp-stage1a-live60_20260311T015054Z` during flow, `deny-hit-udp-stage1b-post60_20260311T015148Z` after flow with wider lookback); both returned submit+poll `FIN` with zero log entries, so Stage 2 destination-token validation did not run.
- Current immediate follow-up is observability-first through orchestrator artifacts: check latest `OBSERVABILITY_RECORD.json` for gating outcome, then rerun only when loop-breaker allows or correlation input materially improves.
- PAN-OS evidence-landscape summaries now live at `docs/fixtures/panos_verification/OBSERVABILITY_COVERAGE.json` and `.md`; they are generated from existing versioned fixture artifacts for postmortem/next-path planning.
- PAN-OS next-attempt selection is now machine-driven via `docs/fixtures/panos_verification/NEXT_CANDIDATE_DECISION.json`; future live attempts should follow selector output, not ad hoc family choice.
- Families marked `exhausted_pending_new_evidence` in selector output are blocked for retries until materially stronger/newer evidence exists.
- The manual template remains useful as optional supplemental context for operator-observed UI details (for example session ID/filter string), but it is not the required input gate for every bounded run.
- Latest bounded execution from that record succeeded in both stages (`jobs 444/445`, `FIN`, `logs count=20`) and is now the version/scenario proof anchor for destination-token behavior in this environment.
- Versioned fixture selectors can now require `capture_provenance` and minimum `verification_scope`; newest-match selection is applied only after those trust filters pass.
- Live fixture collection is constrained to read-only PAN-OS classes/actions by guard helper: `op(show_system_info)`, `log(submit/get)`, `config(get/show/complete)`, and `keygen` bootstrap only.
- Worker step modules in `services/worker/am_i_blocked_worker/steps/`.
- Authoritative-correlation now applies PAN-OS deny-authoritative gating before passing evidence to classification (`services/worker/am_i_blocked_worker/steps/authoritative_correlation.py`).
- Authoritative-correlation now applies conservative PAN-OS/SCM authority gating before passing evidence to classification; SCM records must be explicitly authoritative and deny/decrypt-relevant to pass through.
- Classification logic isolated in `services/worker/am_i_blocked_worker/steps/classify.py`.
- Classifier deny authority is constrained to authoritative sources (PAN-OS/SCM); enrichment sources like LogScale cannot independently produce `denied`.
- Classifier now labels LogScale `enrichment_only_unverified` records as explicit observed facts so report bundles clearly separate enrichment from authority.
- Persistence is isolated in `services/worker/am_i_blocked_worker/steps/persist_and_report.py`.
- Lifecycle integration test uses real route/worker/persistence functions with controlled queue and adapter test doubles to validate persisted result retrieval and UI metadata rendering behavior without route-loader patching.

## Obsolete / Duplicate Paths

- Root-level `AI_AGENT_VENDOR_KNOWLEDGE_BASE.md` is obsolete; canonical file is `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`.
- There is no `services/api/main.py`; API entrypoint is package-level `am_i_blocked_api:app`.

## API Contract Notes

- `docs/api.md` defines observed-fact detail metadata keys used by UI fact-type labeling:
  - `classification_role` (recognized enrichment value: `enrichment_only_unverified`)
  - `authoritative` (boolean; `false` indicates enrichment-only context)
- PAN-OS rule metadata is currently surfaced through existing observed-fact detail payload (`observed_facts[].detail.rule_metadata`) without introducing new top-level API fields.
- Diagnostic result now includes a minimal additive explainability field:
  - `unknown_reason_signals` (list of short strings; populated for unknown verdicts when available)
- Diagnostic result now includes a compact additive readiness field:
  - `source_readiness_summary` (`total_sources`, `available_sources`, `unavailable_sources`, `unknown_sources`)
- Diagnostic result now includes a compact per-source readiness field:
  - `source_readiness_details` (list of `source`, `status`, optional `reason`, optional `latency_ms`), derived from persisted `report_json.source_readiness`
- `docs/api.md` now also includes `RequestDetail` failed-state response examples documenting:
  - `failure_reason`
  - `failure_stage`
  - `failure_category`
- Result evidence bundle download route for UI/operator workflows:
  - `GET /api/v1/requests/{request_id}/result/evidence-bundle`
  - returns JSON with `Content-Disposition: attachment; filename="evidence-{request_id}.json"`
