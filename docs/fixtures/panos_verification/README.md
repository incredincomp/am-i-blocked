# PAN-OS Verification Fixture Pack

This folder holds **sanitized** PAN-OS XML samples used to validate adapter assumptions
without changing runtime adapter behavior.

These files may be either:
- template scaffolding with placeholders, or
- sanitized real-environment captures.

In both cases, samples are verification artifacts, not production truth by themselves.

## Required Files

- `traffic_log_submit_response.xml`
- `traffic_log_poll_response.xml`
- `rule_metadata_config_response.xml`

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

See the script header for more details.

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

It validates:
- required files exist
- XML parses
- minimal structural markers are present
- sanitization contract text is present in this README

## What This Pack Can and Cannot Verify

Can verify (when samples are present):
- submit response job-id parsing shape
- poll response status/log-entry container shape
- metadata response rule-entry field shape

Cannot verify by itself:
- universal PAN-OS behavior across versions
- query field correctness beyond what samples explicitly show
- Panorama-specific behavior unless explicitly represented in samples
