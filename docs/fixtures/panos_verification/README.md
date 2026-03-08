# PAN-OS Verification Fixture Pack

This folder holds **sanitized** PAN-OS XML samples used to validate adapter assumptions
without changing runtime adapter behavior.

These files are **fixture templates/scaffolding**, not verified environment truth.
Replace placeholder values with sanitized real-environment captures when available.

## Required Files

- `traffic_log_submit_response.xml`
- `traffic_log_poll_response.xml`
- `rule_metadata_config_response.xml`

## Sanitization Rules (Required)

1. Remove or replace all secrets:
   - API keys, auth tokens, cookies, session IDs.
2. Remove or anonymize environment identifiers:
   - firewall hostnames, serial numbers, device groups, vsys labels that map to production naming.
3. Replace sensitive network/app data:
   - internal IPs, private domains/FQDNs, URLs, usernames, email addresses, ticket IDs.
4. Keep protocol structure intact:
   - XML tags/attributes required for parsing must remain.
5. Keep one realistic deny example where available:
   - include a deny/reset traffic entry and associated rule metadata entry.

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
