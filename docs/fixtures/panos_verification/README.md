# PAN-OS Verification Fixture Pack

This folder holds **sanitized** PAN-OS XML samples used to validate adapter assumptions
without changing runtime adapter behavior.

These files may be either:
- template-seeded packs with placeholders,
- synthetic/hand-authored fixtures (for malformed/edge parser tests), or
- sanitized real-environment captures.

In all cases, samples are verification artifacts, not production truth by themselves.
**Versioned does not automatically mean verified.**

## Observability Prerequisite (Before Token Validation)

Primary gate is now machine-recorded by the orchestrator:

- `OBSERVABILITY_RECORD.json` (always written by `scripts/panos_observe_and_validate.py`)
- Preferred pre-run correlation input when stronger evidence exists:
  - `OBSERVABILITY_INPUT.json` (prepared via `scripts/prepare_panos_observability_input.py`)

Optional supplemental/manual evidence:

- `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md`

If `OBSERVABILITY_RECORD.json` reports no qualifying observability hit, treat the blocker as
observability/log visibility and do not run token-promotion attempts in that cycle.

## Required Files

- `traffic_log_submit_response.xml`
- `traffic_log_poll_response.xml`
- `rule_metadata_config_response.xml`

These canonical files at the fixture root are the latest sanitized mirrors used by
fixture validation tests.

## Versioned Capture Layout

Use versioned packs for all non-root fixture sets:

- `versions/<panos_version>/<capture_label>_<timestamp>/traffic_log_submit_response.xml`
- `versions/<panos_version>/<capture_label>_<timestamp>/traffic_log_poll_response.xml`
- `versions/<panos_version>/<capture_label>_<timestamp>/rule_metadata_config_response.xml`
- `versions/<panos_version>/<capture_label>_<timestamp>/system_info.xml`
- `versions/<panos_version>/<capture_label>_<timestamp>/CAPTURE_METADATA.txt`

The helper script writes both:
- a versioned capture pack under `versions/...`, and
- canonical root mirrors for the three required XML files.

Current seeded example for selector wiring/tests:
- `versions/11.0.2/deny-hit_20260308T210000Z/`

Current real-capture examples (version-scoped evidence, mixed completeness):
- `versions/11.0.6-h1/no-match_20260310T173006Z/`
- `versions/11.0.6-h1/metadata-hit_20260310T173041Z/`
- `versions/11.0.6-h1/xpath-shape_20260310T173154Z/`

## Manifest Contract (Required)

Every versioned capture directory must include `CAPTURE_METADATA.txt` with at least:

- `capture_provenance`
  - allowed: `real_capture`, `template_seeded`, `synthetic`
- `verification_scope`
  - allowed: `parser_shape_only`, `query_shape_partial`, `xpath_shape_partial`, `real_env_partial`, `real_env_high_confidence`
- `panos_version_reported`
- `panos_version_source`
  - allowed: `auto_detected`, `override`, `unknown`
- `scenario`
- `captured_at_utc`
- `capture_label`
- `notes`

Additional safe fields are allowed. Do not add secrets or raw auth material.

### Trust-Level Meaning

- `capture_provenance=template_seeded`
  - for selector wiring and parser-shape checks.
  - does **not** prove real PAN-OS query-field or XPath correctness.
- `capture_provenance=synthetic`
  - for malformed/edge-case parser handling tests.
  - does **not** prove real PAN-OS behavior.
- `capture_provenance=real_capture`
  - sanitized real-firewall evidence capture.
  - only this provenance may be used to promote assumptions from `UNVERIFIED`.

### Verification Scope Meaning

- `parser_shape_only`: XML structure/parser marker checks only.
- `query_shape_partial`: partial evidence for query-shape assumptions.
- `xpath_shape_partial`: partial evidence for metadata XPath assumptions.
- `real_env_partial`: real environment evidence, not yet high-confidence/complete.
- `real_env_high_confidence`: strong real-environment evidence for targeted assumptions.

## Safe Selector Semantics

Selectors should resolve "latest" only among captures that satisfy requested trust filters.
Required trust filters must fail closed:

- no silent fallback from `real_capture` to template or synthetic packs.
- no implicit trust escalation from version naming alone.
- newest-match behavior is applied only after provenance/scope gating.
- if a real-capture scenario is incomplete (for example, submit error with no poll file),
  selector-based promotion tests must fail closed rather than downgrading requirements.

## PAN-OS Protocol Distinction (Required)

Keep these API contracts distinct:

- Traffic log retrieval:
  - `type=log`
  - `query=...` uses Monitor/Traffic filter syntax.
  - polling uses `type=log&action=get&job-id=...`
- Rule/config metadata retrieval:
  - `type=config`
  - `action=get|show|complete`
  - `xpath=...` uses XPath semantics.

Do not treat log-query tokens as XPath claims, and do not treat XPath examples as log-query token evidence.

## Helper script

There is a convenience shell script at `scripts/gather_panos_fixtures.sh` which
can be run against a live firewall to grab the usual set of API exchanges and
perform a first-pass sanitisation.  It is not required – you can collect your
own samples by hand – but it can speed up fixture creation in a repeatable
manner.

Usage:

```sh
./scripts/gather_panos_fixtures.sh <firewall-host> <api-key> <rule-xpath-or-name>
```

Preferred explicit usage:

```sh
./scripts/gather_panos_fixtures.sh \
  --host <firewall-host> \
  --api-key <api-key> \
  --rule-xpath <rule-xpath> \
  --capture-label <label> \
  --dst <destination> \
  --dport <port> \
  --hours <lookback-hours>
```

If an API key is not available, the script can request one first:

```sh
./scripts/gather_panos_fixtures.sh \
  --host <firewall-host> \
  --username <username> \
  --password <password> \
  --rule-xpath <rule-xpath> \
  --capture-label <label>
```

Script behavior:
- captures PAN-OS system info and uses `sw-version` for version foldering (unless overridden),
- optionally requests an API key via XML `type=keygen` when `--api-key` is omitted and username/password are provided,
- URL-encodes dynamic `query=` and `xpath=` values for live XML API calls to avoid malformed URL failures on bounded filters,
- captures async traffic-log submit and poll responses,
- captures rule metadata config responses (`show` and `complete`),
- writes request logs and a capture manifest for traceability,
- applies first-pass sanitization and mirrors the latest sanitized required files.
- writes provenance-aware capture manifests for real collection:
  - `capture_provenance=real_capture`
  - `panos_version_source=auto_detected` when discovered from system info
  - `panos_version_source=override` when `--version` is explicitly used
  - `verification_scope` defaults to `real_env_partial` (override via `--verification-scope`)

### One-Shot Observe + Validate Orchestrator

Use `scripts/panos_observe_and_validate.py` to run one bounded workflow end-to-end:

1. generate bounded source traffic over SSH,
2. run a broad Stage 1 deny observability sweep (`addr.src`/rule/action/session-end-reason/app/zones + bounded `receive_time`),
3. auto-select the freshest qualifying deny row,
4. run independent token subqueries (`addr.dst` and `dport`) only when Stage 1 finds a qualifying row,
5. write `OBSERVABILITY_RECORD.json` and `VALIDATION_RESULT.json` in the Stage 1 capture directory (or fallback preflight directory on early stop).

When correlation evidence is available, prepare and provide `OBSERVABILITY_INPUT.json`:
- preferred strong signals: `session_id`, exact `ui_filter_string`, and structured row export fields
- if the artifact is marked not-ready/low-confidence, orchestrator preflight fails closed
- repeated no-hit retries for materially identical signatures require ready `OBSERVABILITY_INPUT.json`

The orchestrator delegates PAN-OS API capture to `gather_panos_fixtures.sh`, so read-only guardrails remain enforced through `scripts/panos_readonly_guard.sh`.

Example:

```sh
./scripts/panos_observe_and_validate.py \
  --host "$PANOS_HOST" \
  --username "$PANOS_USERNAME" \
  --password "$PANOS_PASSWORD" \
  --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules" \
  --capture-label "deny-hit-distinct" \
  --source-ssh-target "root@10.1.99.3" \
  --source-ip "10.1.99.3" \
  --destination-ip "10.1.20.21" \
  --destination-port 30053 \
  --app "not-applicable" \
  --rule "interzone-default" \
  --action "deny" \
  --session-end-reason "policy-deny" \
  --zone-src "management" \
  --zone-dst "servers" \
  --observability-input "docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json" \
  --lookback-minutes 15
```

Prepare observability input artifact example:

```sh
./scripts/prepare_panos_observability_input.py \
  --row-json /path/to/ui_row.json \
  --evidence-origin ui_json_export \
  --freshness-note "row observed immediately after reproduction" \
  --out docs/fixtures/panos_verification/OBSERVABILITY_INPUT.json
```

`VALIDATION_RESULT.json` includes machine-readable fields such as:
- `observability_hit`
- `matched_entry_count`
- `best_match_timestamp`
- `validated_tokens`
- `addr_dst_validated`
- `dport_validated`
- `reason_if_not_validated`
- `panos_version`
- `capture_provenance`
- `scenario_name`

`OBSERVABILITY_RECORD.json` is the primary run-state artifact and includes:
- run timing (`run_started_at`, `run_finished_at`)
- attempt signature and loop-breaker state
- traffic-generation execution status
- observability hit/no-hit and best-match summary
- token-validation outcomes (`validated_tokens`, `addr_dst_validated`, `dport_validated`)
- stop reason / run decision when execution is blocked or fails closed

### Local Firewall Run Pattern

When collecting from a local firewall using repo `.env` credentials:

```sh
set -a
source ./.env
set +a

./scripts/gather_panos_fixtures.sh \
  --host <local-fw-host> \
  --username "$PANOS_USERNAME" \
  --password "$PANOS_PASSWORD" \
  --rule-xpath "<read-only-xpath>" \
  --capture-label "deny-hit"
```

The harness enforces a read-only allowlist and fails closed on disallowed request types/actions.

Allowed live request classes/actions:
- `type=op` with read-only `show_system_info`
- `type=log` submit and `action=get` poll
- `type=config` with `action=get|show|complete`
- `type=keygen` bootstrap only

Disallowed live actions include:
- `set`, `edit`, `delete`, `move`, `rename`, `clone`, `override`
- `multi-config`, `commit`, `commit-all`
- any request type/action outside the allowlist

### Authentication Preflight and `403 Invalid Credential`

For key bootstrap mode (`--username` + `--password`), the harness now uses documented
form-urlencoded POST keygen first (`POST /api/` with `type=keygen`).

If keygen returns PAN-OS XML API `403 Invalid Credential`, the harness fails fast and stops.
It treats this as an auth/authorization blocker, not a connectivity blocker.
It does not run repeated invalid-credential retry loops.
If keygen returns a non-auth XML error (or any response without `<key>`), the harness also fails fast
with a generic keygen/API blocker and still does not proceed to live capture steps.

Operator prerequisites before re-running live capture:
- preferred: provide a known-good API key (`--api-key`) to bypass keygen uncertainty
- ensure the account role has PAN-OS XML API access enabled
- ensure XML API role permissions include read access needed here:
  - traffic log retrieval (`type=log` submit/get)
  - config read (`type=config` action=`get|show|complete`)
- if using external auth, confirm username format matches backend expectations
- do not retry capture until valid API credentials/API key are confirmed

If external troubleshooting has already confirmed both keygen forms (`GET` and documented `POST`)
return `403 Invalid Credential`, do not continue live capture attempts until auth prerequisites are fixed.

### Template or Synthetic Seeding (Manual)

When creating a fixture pack manually (copy/seed/hand-author), you must set:

- `capture_provenance=template_seeded` for wiring/template packs
- `capture_provenance=synthetic` for hand-authored malformed/edge fixtures

Do not label manual seeds as `real_capture`.

## Sanitization Rules (Required)

1. Redact/tokenize **all auth/session material**:
   - API keys, bearer tokens, cookies, session IDs, auth headers.
2. Redact/tokenize sensitive infrastructure identifiers:
   - public/private IPs when sensitive, hostnames, firewall serial numbers, device names.
3. Redact/tokenize sensitive identity/business data:
   - usernames, emails, ticket IDs, internal references, internal object names when sensitive.
4. Redact/tokenize policy identifiers when needed:
   - rule names if sensitive.
5. Preserve XML protocol shape:
   - keep tag names, nesting, and relevant attributes required for parser behavior.
6. Preserve representative response shape:
   - keep realistic field names and structural placement used by adapter parsing.
7. Use consistent placeholders when redacting values:
   - prefer `REDACTED_*` or `SANITIZED_*` patterns within a file set.
8. Never commit raw secrets:
   - no tokens, cookies, API keys, credentials, or session material in git.
9. Never treat redacted sample values as authoritative production values:
   - only structure and field presence are considered evidence.

## Expected Structural Fields

### `traffic_log_submit_response.xml`

- XML root response
- asynchronous job id field:
  - `.//job`

### `traffic_log_poll_response.xml`

- XML root response
- job status:
  - `.//status` (`FIN` preferred for completed sample)
- log entries container:
  - `.//logs/entry`

Recommended entry fields (when available):
- `action`
- `rule`
- `time_generated` or `receive_time`
- `dst`
- `dport`

### `rule_metadata_config_response.xml`

- XML root response
- rule entry node:
  - `.//entry[@name='...']`

Recommended rule fields (when available):
- `action`
- `description`
- `disabled`
- `tag/member`

## Validation Usage

A small fixture-pack loader/validator test exists at:
- `tests/fixtures/test_panos_verification_fixture_pack.py`
- `tests/fixtures/panos_fixture_selector.py` (version + scenario selector helper for integration tests)

Example selector usage in tests:
- `select_versioned_capture(version="11.0.2", scenario="deny-hit", require_provenance="template_seeded")`

It validates:
- required files exist
- XML parses
- minimal structural markers are present
- sanitization contract text is present in this README

Fixture test usage by type:
- parser-shape tests: may use `template_seeded` or `synthetic` when explicit.
- selector/wiring tests: may use `template_seeded`.
- real-environment verification tests: must require `real_capture` and an appropriate verification scope.

## Recommended Collection Matrix

For each PAN-OS version you support, capture at least:

1. deny hit sample (`action=deny` or reset equivalent in poll response)
2. no-match sample (valid poll response with no relevant deny entry)
3. rule metadata sample for a known deny rule
4. malformed/partial sample (manually sanitized to preserve malformed structure for parser hardening tests)

If a live scenario yields a valid real-capture submit error (for example query-shape/API error)
but does not produce all required XML artifacts, keep it as real evidence with an appropriate
partial `verification_scope`, and do not use it to promote assumptions that require complete
submit+poll+metadata proof.

Keep each sample set in a separate labeled versioned folder so future tests can select
fixtures by version and condition.

## What This Pack Can and Cannot Verify

Can verify (when samples are present):
- submit response job-id parsing shape
- poll response status/log-entry container shape
- metadata response rule-entry field shape

Cannot verify by itself:
- universal PAN-OS behavior across versions
- query field correctness beyond what samples explicitly show
- Panorama-specific behavior unless explicitly represented in samples
- real-environment assumptions from template-seeded or synthetic fixtures
