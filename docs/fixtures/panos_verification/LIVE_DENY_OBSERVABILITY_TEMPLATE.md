# LIVE_DENY_OBSERVABILITY_TEMPLATE.md

Use this checklist before any new PAN-OS XML token-validation run (`addr.dst` / `dport` candidate).

Goal: prove whether the just-generated deny traffic is visible in live Traffic logs, and capture the exact observed signature.

## Run Header

- PAN-OS version: 11.0.6-h1
- Firewall/serial or device label (sanitized if needed):
- Capture timestamp (UTC): 2026/03/10 23:36:42
- Traffic reproduction window (UTC start/end): 2026/03/10 23:36:42 to 2026/03/10 23:36:42
- Reproduction command used: `nc -vz -w 3 10.1.20.21 30053`
  - `10.1.20.21: inverse host lookup failed: Unknown host`
  - `(UNKNOWN) [10.1.20.21] 30053 (?) : Connection timed out`

## Fresh Live Traffic Row (UI/CLI) Evidence

- Fresh row confirmed during/just after reproduction: `yes`
- Source IP: `10.1.99.3`
- Destination IP: `10.1.20.21`
- Destination port: `30053`
- App: `not-applicable`
- Action: `deny`
- Rule: `interzone-default`
- Session end reason: `policy-deny`
- Type/detail (if shown): `drop`
- Source zone (if shown): `management`
- Destination zone (if shown): `servers`
- Session ID (if shown): `0`
- Exact Monitor filter string used (if shown): `!( action eq 'allow' )`
- Freshness note tying row to this reproduction: `Immediately after running the nc test to 10.1.20.21:30053 from 10.1.99.3, a deny traffic log appeared showing src=10.1.99.3, dst=10.1.20.21, dport=30053, action=deny, rule=interzone-default, and session end reason=policy-deny at 2026/03/10 23:36:42.`

## Optional additional fields observed in the log view

- Rule UUID: `e6e730d3-c9d2-438e-a98e-edc883c723ce`
- IP Protocol: `tcp`
- Source port: `58070`
- Source interface: `ethernet1/1.99`
- Source country: `10.0.0.0-10.255.255.255`
- Destination country: `10.0.0.0-10.255.255.255`
- Bytes: `78`
- Bytes sent: `78`
- Bytes received: `0`
- Packets sent: `1`
- Packets received: `0`
- Repeat count: `1`
- Flow type: `NonProxyTraffic`
- Tunnel type: `N/A`

## Observability Decision

- If no fresh row is confirmed:
  - mark blocker as `observability` (not token-validation)
  - do not run destination-token promotion attempts
- If fresh row exists but signature differs:
  - record exact observed fields above
  - use that exact signature in the next bounded XML Stage 1 run
- If fresh row exists and signature matches expected deny signature:
  - proceed in the next run with bounded Stage 1 then Stage 2 destination-token validation

## Expected Deny Signature for Current UDP Scenario (`11.0.6-h1`)

- `addr.src = 10.1.99.10`
- `addr.dst = 10.1.20.20`
- `dport = 30053`
- `rule = interzone-default`
- `action = deny`
- `session_end_reason = policy-deny`
- traffic-log detail/type observed historically: `drop`

## Latest Completed Record (`11.0.6-h1`)

- PAN-OS version: `11.0.6-h1`
- Reproduction time/window (firewall local time): `2026/03/10 21:48:27`
- Freshness tie note: row observed immediately after reproducing UDP traffic to the same target/port in this window.
- Source IP: `10.1.99.10`
- Destination IP: `10.1.20.20`
- Destination host label: `k3s_master`
- Destination port: `30053`
- App: `not-applicable`
- Action: `deny`
- Rule: `interzone-default`
- Session end reason: `policy-deny`
- Type/detail: `drop`
- Source zone: `management`
- Destination zone: `servers`
- Session ID: `78` (field-label confirmation pending)
- Exact Monitor filter string: not captured
- Destination address token candidate for next bounded validation: `addr.dst`
- Destination port token candidate for next bounded validation: `dport`
