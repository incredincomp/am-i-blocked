# Next PAN-OS Candidate Decision

Generated from `NEXT_CANDIDATE_DECISION.json` inputs.

## Primary Recommendation

- Action: **pause_panos_token_expansion**
- Why: No worthwhile non-exhausted candidate family with sufficient destination-token potential; avoid further no-hit loop retries.

## Family Classifications

- `10.1.99.10|10.1.20.20|30053|not-applicable|tcp|interzone-default|policy-deny|unknown` -> `proven`
- `10.1.99.10|unknown|unknown|not-applicable|tcp|interzone-default|policy-deny|unknown` -> `candidate`
- `10.1.99.10|unknown|unknown|unknown|unknown|interzone-default|policy-deny|unknown` -> `exhausted_pending_new_evidence`
- `10.1.99.3|10.1.20.180|unknown|unknown|unknown|unknown|policy-deny|unknown` -> `candidate`
- `10.1.99.3|10.1.20.21|30053|not-applicable|unknown|interzone-default|policy-deny|ssh_custom_command` -> `exhausted_pending_new_evidence`
- `10.1.99.3|unknown|unknown|icmp|unknown|interzone-default|policy-deny|unknown` -> `candidate`
- `10.1.99.3|unknown|unknown|not-applicable|unknown|interzone-default|policy-deny|unknown` -> `exhausted_pending_new_evidence`
- `10.1.99.3|unknown|unknown|unknown|unknown|unknown|policy-deny|unknown` -> `candidate`
- `unknown|example.com|443|unknown|unknown|unknown|unknown|unknown` -> `candidate`
- `unknown|unknown|unknown|unknown|unknown|unknown|unknown|unknown` -> `exhausted_pending_new_evidence`

## Exhausted Families

- `10.1.99.10|unknown|unknown|unknown|unknown|interzone-default|policy-deny|unknown`: repeated_no_hit_pattern, destination_ip_not_specific, destination_port_not_specific
- `10.1.99.3|10.1.20.21|30053|not-applicable|unknown|interzone-default|policy-deny|ssh_custom_command`: repeated_no_hit_with_high_confidence_attempt
- `10.1.99.3|unknown|unknown|not-applicable|unknown|interzone-default|policy-deny|unknown`: repeated_no_hit_pattern, destination_ip_not_specific, destination_port_not_specific
- `unknown|unknown|unknown|unknown|unknown|unknown|unknown|unknown`: repeated_no_hit_pattern, destination_ip_not_specific, destination_port_not_specific, source_ip_not_specific
