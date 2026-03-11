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
- `docs/fixtures/panos_verification`: sanitized PAN-OS XML verification fixture pack templates plus versioned evidence-capture folders (`versions/<panos_version>/<capture_label>_<timestamp>/`).
- `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`: required checklist for confirming fresh live deny-row observability before another XML destination-token validation run.

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
- Unknown verdicts now render compact confidence explainability (`path_confidence`, `evidence_completeness`, `unknown_reason_signals`) in the result page "Why unknown" section.
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
- `tests/routes/test_api_routes.py`: also covers unknown-confidence explainability rendering and persisted-result fallback handling for missing/malformed confidence values.
- `tests/fixtures`: pipeline integration-style tests with mocked adapters/readiness.
- `tests/fixtures/test_lifecycle_integration.py`: integration-style submit -> queue -> worker -> persist -> API result retrieval + UI render coverage with controlled PAN-OS deny/no-authoritative-evidence outcomes, including persisted PAN-OS metadata present/malformed lifecycle assertions.
- `tests/fixtures/test_panos_verification_fixture_pack.py`: fixture-pack scaffolding validation (required PAN-OS XML sample files exist, parse, and contain minimum structural markers).
- `tests/fixtures/panos_fixture_selector.py`: helper for selecting versioned PAN-OS captures by `version + scenario` with provenance/scope gating (`require_provenance`, `minimum_verification_scope`) and strict manifest validation.
- `tests/fixtures/test_panos_fixture_selector.py`: unit coverage for version/scenario fixture selection and manifest parsing.
- `tests/fixtures/test_panos_collection_harness.py`: harness safety tests for read-only allowlist enforcement and real-capture manifest/sanitization behavior using fake `curl`.
- `tests/fixtures/test_panos_observe_and_validate.py`: orchestration logic tests for bounded observe-and-validate flow (freshest deny-row matching, fail-closed no-hit behavior, SSH-unavailable fail-closed behavior, token-result handling, and summary writing).
- `scripts/gather_panos_fixtures.sh`: helper to capture sanitized PAN-OS XML samples, write versioned fixture packs, and mirror canonical required fixture files.
- `scripts/panos_observe_and_validate.py`: bounded one-shot orchestrator that runs source-host traffic generation + Stage 1 observability sweep + Stage 2 token subqueries (`addr.dst` and `dport`) and writes `VALIDATION_RESULT.json`.
- `scripts/panos_readonly_guard.sh`: read-only PAN-OS XML request allowlist guard used by fixture collection harness and testable via `--assert`.
- `tests/adapters`: adapter contract tests (`BaseAdapter` compliance).
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
- PAN-OS traffic-log destination token validation remains observability-gated for new attempts; latest real-capture Stage 1/Stage 2 pair for `11.0.6-h1` UDP deny signature (`deny-hit-udp-obsgate-stage1_20260311T052621Z`, `deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`) provides scenario-scoped evidence for `addr.dst` + `dport`.
- PAN-OS traffic-log field-name guidance for future validation is `sport`, `dport`, `natsport`, `natdport`; `port.src`/`port.dst` are not default candidates.
- PAN-OS runtime query construction now uses `addr.dst` + `dport` for destination filtering in the adapter query builder, aligned to scenario-scoped `11.0.6-h1` UDP deny real-capture evidence.
- PAN-OS one-shot orchestration now supports bounded observability-first validation in a single run while preserving fail-closed semantics: Stage 2 token checks run only when Stage 1 captures a qualifying deny row.
- PAN-OS metadata XPath shape remains explicitly `UNVERIFIED`/version-dependent pending target-environment capture; no PAN-OS version pin/source file exists in repo config today.
- PAN-OS fixture pack currently validates parser shape expectations (`.//job`, `.//status`, `.//logs/entry`, `.//entry[@name]`) but does not independently verify version-specific query-field/XPath correctness.
- Fixture helper supports explicit capture labels, optional destination/port/time-window query generation, API-key or keygen-based auth (`--username`/`--password` fallback), and per-capture metadata manifests with required trust fields (`capture_provenance`, `verification_scope`, `panos_version_source`).
- Fixture helper now URL-encodes dynamic XML API query/xpath values via curl `--data-urlencode` for live collection safety (prevents malformed URL failures on bounded query strings) while preserving read-only guardrails.
- Keygen bootstrap preflight is fail-fast on explicit PAN-OS XML API auth rejection signatures (`403 Invalid Credential`) with operator guidance for API-key mode and XML-API-role prerequisites; non-auth XML keygen errors fail fast with generic keygen/API error messaging, and no invalid-credential retry loop is used.
- Current local-firewall run state: keygen preflight succeeds with current `.env` credentials, and real-capture versioned scenarios now exist for PAN-OS `11.0.6-h1` (`deny-hit`, `no-match`, `metadata-hit`, `query-shape`, `xpath-shape`, `deny-hit-icmp-management-servers`, `deny-hit-icmp-stage1-src-only`, `deny-hit-icmp-stage1-signature`, `deny-hit-udp-stage1-signature`) with mixed completeness by scenario; latest two-stage UDP signature-coupled run stopped after Stage 1 (`deny-hit-udp-stage1-signature_20260311T012658Z`) because submit+poll `FIN` returned zero log entries, so Stage 2 destination-token validation was not executed.
- Latest self-contained UDP verification precondition check: non-interactive SSH execution to source host `10.1.99.10` was unavailable from the current shell in this run, so bounded traffic generation could not be started directly and no additional PAN-OS capture stage was executed.
- Latest operator-delegated UDP verification run (`deny-hit-udp-stage1-signature-livegen_20260311T014031Z`) executed during bounded source-host traffic generation, but Stage 1 still returned submit+poll `FIN` with zero log entries; Stage 2 destination-token validation did not run.
- Latest final bounded UDP verification used exact 60-second generation plus two-pass Stage 1 (`deny-hit-udp-stage1a-live60_20260311T015054Z` during flow, `deny-hit-udp-stage1b-post60_20260311T015148Z` after flow with wider lookback); both returned submit+poll `FIN` with zero log entries, so Stage 2 destination-token validation did not run.
- Current immediate follow-up is observability-first: use the completed fresh deny-row record in `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`, then run one bounded XML Stage 1 from that exact row; run Stage 2 only if Stage 1 captures a qualifying deny event.
- Latest completed observability row for that workflow is recorded in the template (`11.0.6-h1`, UDP deny signature for `10.1.99.10 -> 10.1.20.20:30053`) and is the required input for the next bounded Stage 1 query.
- Latest bounded execution from that record succeeded in both stages (`jobs 444/445`, `FIN`, `logs count=20`) and is now the version/scenario proof anchor for destination-token behavior in this environment.
- Versioned fixture selectors can now require `capture_provenance` and minimum `verification_scope`; newest-match selection is applied only after those trust filters pass.
- Live fixture collection is constrained to read-only PAN-OS classes/actions by guard helper: `op(show_system_info)`, `log(submit/get)`, `config(get/show/complete)`, and `keygen` bootstrap only.
- Worker step modules in `services/worker/am_i_blocked_worker/steps/`.
- Authoritative-correlation now applies PAN-OS deny-authoritative gating before passing evidence to classification (`services/worker/am_i_blocked_worker/steps/authoritative_correlation.py`).
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
- `docs/api.md` now also includes `RequestDetail` failed-state response examples documenting:
  - `failure_reason`
  - `failure_stage`
  - `failure_category`
- Result evidence bundle download route for UI/operator workflows:
  - `GET /api/v1/requests/{request_id}/result/evidence-bundle`
  - returns JSON with `Content-Disposition: attachment; filename="evidence-{request_id}.json"`
