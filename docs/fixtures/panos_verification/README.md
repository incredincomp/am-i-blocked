# PAN-OS Verification Fixture Pack

This folder holds **sanitized** PAN-OS XML samples used to validate adapter assumptions
without changing runtime adapter behavior.

These files may be either:
- template-seeded packs with placeholders,
- synthetic/hand-authored fixtures (for malformed/edge parser tests), or
- sanitized real-environment captures.

In all cases, samples are verification artifacts, not production truth by themselves.
**Versioned does not automatically mean verified.**

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
- captures async traffic-log submit and poll responses,
- captures rule metadata config responses (`show` and `complete`),
- writes request logs and a capture manifest for traceability,
- applies first-pass sanitization and mirrors the latest sanitized required files.
- writes provenance-aware capture manifests for real collection:
  - `capture_provenance=real_capture`
  - `panos_version_source=auto_detected` when discovered from system info
  - `panos_version_source=override` when `--version` is explicitly used
  - `verification_scope` defaults to `real_env_partial` (override via `--verification-scope`)

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
