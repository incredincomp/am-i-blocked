# PAN-OS Observability Coverage

Generated from repository artifacts under `/home/adminer/gitstuff/am-i-blocked/docs/fixtures/panos_verification/versions`.

## Snapshot

- Total versioned runs analyzed: 22
- Runs with `OBSERVABILITY_RECORD.json`: 1
- Runs with `VALIDATION_RESULT.json`: 2
- Proven token-validation scenarios: 1
- Observability-hit but token-not-proven scenarios: 1
- No-observability-hit scenarios: 19
- Loop-breaker blocked/rerun-risk scenarios: 16

## What Is Proven

- deny-hit-udp-obsgate-stage2-addrdst-dport (11.0.6-h1): validated tokens ['addr.dst', 'dport'] from run(s) ['deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z']

## Repeated No-Hit Patterns

- Family `10.1.99.10|unknown|unknown|unknown|unknown|interzone-default|policy-deny|unknown`: 4 no-hit run(s), 0 hit run(s), proven tokens=[].
- Family `10.1.99.3|unknown|unknown|not-applicable|unknown|interzone-default|policy-deny|unknown`: 3 no-hit run(s), 0 hit run(s), proven tokens=[].
- Family `10.1.99.3|unknown|unknown|unknown|unknown|unknown|policy-deny|unknown`: 2 no-hit run(s), 0 hit run(s), proven tokens=[].
- Family `unknown|example.com|443|unknown|unknown|unknown|unknown|unknown`: 2 no-hit run(s), 0 hit run(s), proven tokens=[].
- Family `unknown|unknown|unknown|unknown|unknown|unknown|unknown|unknown`: 5 no-hit run(s), 0 hit run(s), proven tokens=[].

## Likely Non-Observable Classes On This Path

- Distinct-signature family `src=10.1.99.3,dst=10.1.20.21,dport=30053,app=not-applicable,rule=interzone-default,session_end_reason=policy-deny` has repeated Stage-1 no-hit outcomes (including orchestrator runs) and no validated tokens.
- UDP-signature replay family `src=10.1.99.10,rule=interzone-default,action=deny,session_end_reason=policy-deny` has repeated no-hit Stage-1 runs during replay/livegen windows, despite one separate observability-gated success pair.

## Single Next Recommended Path

- Recommendation: **Use a higher-confidence observability source before any new live PAN-OS attempt**
- Why: Only one scenario-scoped success exists (11.0.6-h1 UDP obsgate pair), while repeated distinct-signature and replay families show no Stage-1 observability hit. Additional retries in those families have high marginal risk and low expected return without stronger observability evidence.
- Stop condition: Do not run another distinct-signature observe-and-validate attempt until new evidence quality is materially improved (for example: authoritative exported deny rows/session correlation for the exact candidate family).

## Artifact Inputs

- Observability records analyzed: 1
- Validation results analyzed: 2
- Capture manifests analyzed: 22
