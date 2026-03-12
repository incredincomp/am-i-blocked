# API Reference

## Base URL

```
http://<host>:8000/api/v1
```

---

## Authentication

Authentication is handled by the reverse proxy (nginx, Cloudflare Access, etc.). The proxy injects the requester identity as an HTTP header configured by `APP_IDENTITY_HEADER` (default: `X-Forwarded-User`).

---

## Endpoints

### POST /api/v1/am-i-blocked

Submit a new diagnostic request.

**Request body** (JSON):

```json
{
  "destination": "api.example.com",
  "port": 443,
  "time_window": "last_15m"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `destination` | string | ✅ | URL, FQDN, or IP address (no CIDR ranges) |
| `port` | integer 1–65535 | ❌ | Optional single destination port |
| `time_window` | enum | ❌ | `now` \| `last_15m` (default) \| `last_60m` |

**Response** `202 Accepted`:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "status_url": "/api/v1/requests/550e8400-e29b-41d4-a716-446655440000"
}
```

---

### GET /api/v1/requests/{request_id}

Retrieve the status and detail of a diagnostic request.

**Response** `200 OK`:

```json
{
  "request_id": "550e8400-...",
  "status": "complete",
  "destination_type": "fqdn",
  "destination_value": "api.example.com",
  "port": 443,
  "time_window_start": "2026-01-01T00:00:00Z",
  "time_window_end": "2026-01-01T00:15:00Z",
  "requester": "alice",
  "created_at": "2026-01-01T00:14:00Z",
  "result": { ... }
}
```

Failed-state example (`status=failed`):

```json
{
  "request_id": "550e8400-...",
  "status": "failed",
  "destination_type": "fqdn",
  "destination_value": "api.example.com",
  "port": 443,
  "time_window_start": "2026-01-01T00:00:00Z",
  "time_window_end": "2026-01-01T00:15:00Z",
  "requester": "alice",
  "created_at": "2026-01-01T00:14:00Z",
  "failure_reason": "redis unavailable",
  "failure_stage": "queue_enqueue",
  "failure_category": "dependency",
  "result": null
}
```

Another failed-state example (worker pipeline step failure):

```json
{
  "request_id": "550e8400-...",
  "status": "failed",
  "destination_type": "fqdn",
  "destination_value": "api.example.com",
  "port": 443,
  "time_window_start": "2026-01-01T00:00:00Z",
  "time_window_end": "2026-01-01T00:15:00Z",
  "requester": "alice",
  "created_at": "2026-01-01T00:14:00Z",
  "failure_reason": "adapter unavailable",
  "failure_stage": "authoritative_correlation",
  "failure_category": "dependency",
  "result": null
}
```

Failed-state triage interpretation:

- `failure_reason`: raw diagnostic error text for first-hop context.
- `failure_stage`: normalized pipeline location where failure was recorded (for example `queue_enqueue`, `validate_request`, `authoritative_correlation`, `persist_and_report`).
- `failure_category`: normalized class used for routing (`dependency`, `validation`, `pipeline_step`, `persistence`, `internal`, `unknown`).
- UI triage hints are derived from `failure_stage` + `failure_category`; these fields are operational metadata and do not change verdict authority rules.

---

### GET /api/v1/requests/{request_id}/result

Retrieve the diagnostic result for a completed request.

**Response** `200 OK`:

```json
{
  "request_id": "550e8400-...",
  "verdict": "denied",
  "destination_type": "fqdn",
  "destination_value": "api.example.com",
  "destination_port": 443,
  "enforcement_plane": "strata_cloud",
  "path_context": "vpn_prisma_access",
  "path_confidence": 0.7,
  "result_confidence": 0.9,
  "evidence_completeness": 0.5,
  "operator_handoff_summary": "verdict=denied; path=vpn_prisma_access; enforcement=strata_cloud; authoritative_facts=1; ready_sources=2; unavailable_sources=1; routing_reason=Cloud policy deny evidence found",
  "time_window_start": "2026-01-01T00:00:00Z",
  "time_window_end": "2026-01-01T00:15:00Z",
  "summary": "Cloud policy deny detected in Strata/Prisma evidence.",
  "source_readiness_summary": {
    "total_sources": 4,
    "available_sources": ["panos", "logscale"],
    "unavailable_sources": ["scm"],
    "unknown_sources": ["torq"]
  },
  "source_readiness_details": [
    {
      "source": "scm",
      "status": "auth_failed",
      "reason": "SCM auth failed (401)",
      "latency_ms": 14
    }
  ],
  "observed_fact_summary": {
    "total_facts": 2,
    "authoritative_facts": 1,
    "enrichment_only_facts": 1,
    "authoritative_sources": ["scm"],
    "enrichment_only_sources": ["logscale"]
  },
  "observed_facts": [
    {
      "source": "scm",
      "summary": "Cloud policy deny: rule=block-all-saas",
      "detail": { "action": "deny", "rule_name": "block-all-saas" }
    }
  ],
  "routing_recommendation": {
    "owner_team": "SecOps",
    "reason": "Cloud policy deny evidence found",
    "next_steps": [
      "Review the identified Prisma Access security rule",
      "Open a SecOps ticket referencing the rule name and request ID"
    ]
  },
  "created_at": "2026-01-01T00:14:05Z"
}
```

`source_readiness_summary` is a compact operator-facing view derived from persisted `report_json.source_readiness`:
- `total_sources`: number of sources with readiness entries
- `available_sources`: sources reporting `available=true`
- `unavailable_sources`: sources reporting `available=false`
- `unknown_sources`: sources with malformed/missing readiness state

Per-source readiness diagnostics remain in persisted `report_json.source_readiness` and may include source-specific `status` values (for example SCM, SD-WAN, Torq, and LogScale: `ready`, `not_configured`, `auth_failed`, `unauthorized`, `unreachable`, `timeout`, `unexpected_response`, `internal_error`).
`source_readiness_details` is a compact presentation-safe list derived from that persisted readiness object and includes `source`, normalized `status`, optional `reason`, and optional `latency_ms`.
For `verdict="unknown"`, API responses may include `unknown_reason_signals` as operator-facing explainability hints (for example low path confidence, degraded source readiness, or inconclusive bounded checks). These hints are descriptive only and do not change verdict authority semantics.
`observed_fact_summary` is a compact authority-mix view derived from persisted `report_json.observed_facts`:
- `total_facts`: number of structurally valid observed-fact entries
- `authoritative_facts`: observed facts not tagged as enrichment-only
- `enrichment_only_facts`: observed facts tagged via `classification_role=enrichment_only_unverified` or `authoritative=false`
- `authoritative_sources`: unique source list for authoritative facts
- `enrichment_only_sources`: unique source list for enrichment-only facts
`destination_type`, `destination_value`, and optional `destination_port` in result payloads are sourced from persisted request context and are intended for direct operator ticket handoff/copy-paste.
`time_window_start` and `time_window_end` in result payloads are sourced from persisted request context for operator handoff and may be `null` when unavailable.
`operator_handoff_summary` is an additive compact plain-text handoff line persisted in `report_json` and surfaced in result responses when present.
`routing_recommendation.reason` is normalized as a non-empty string in result shaping; malformed or empty persisted values fall back to `"loaded from persisted result"` for API/model safety.

**Response** `404 Not Found` if the request does not exist or result is not yet available.

---

### GET /api/v1/requests/{request_id}/result/handoff-note

Download a compact plain-text operator handoff note for ticket copy/paste.

- Response content type: `text/plain`
- Response header: `Content-Disposition: attachment; filename="handoff-{request_id}.txt"`
- The note is derived from existing normalized request/result fields and uses compact deterministic sections:
  - request + verdict header (`request_id`, `verdict`, `summary`, optional `operator_handoff_summary`)
  - context (`destination`, `time window`, `path context`, `enforcement plane`)
  - routing (`owner team`, routing reason)
  - evidence snapshot (`observed_fact_summary` counts/sources)
  - readiness snapshot (`source_readiness_summary` counts/source lists)
  - unknown signals section only when verdict is `unknown` and signals are present
  - next steps (`routing_recommendation.next_steps`, or `none provided`)
- This is presentation-only formatting and does not change verdict/classifier/routing semantics.

**Response** `404 Not Found` if the request does not exist or result is not yet available.

---

## Observed Fact Detail Contract

`observed_facts[].detail` is an extensible metadata object. For UI fact-type labeling, these keys are reserved:

| Key | Type | Required | Meaning |
|---|---|---|---|
| `classification_role` | string | ❌ | Classification role hint. Current recognized enrichment value: `enrichment_only_unverified`. |
| `authoritative` | boolean | ❌ | Whether this fact is authoritative for deny decisions. `false` means enrichment-only context. |

Rules:
- If `classification_role == "enrichment_only_unverified"` or `authoritative == false`, UI should label the fact as enrichment-only.
- Absence of both keys implies no enrichment-only hint; UI may treat as authoritative signal by default.
- These keys are presentation metadata and do not expand deny authority.

Example enrichment-only observed fact:

```json
{
  "source": "logscale",
  "summary": "LogScale enrichment-only signal (UNVERIFIED) observed; excluded from deny authority decisions.",
  "detail": {
    "classification_role": "enrichment_only_unverified",
    "authoritative": false,
    "repo": "ng-siem"
  }
}
```

---

### GET /api/v1/healthz

Liveness check.

```json
{"status": "ok"}
```

---

### GET /api/v1/readyz

Readiness check.

```json
{"status": "ok"}
```

---

## Verdict values

| Value | Meaning |
|---|---|
| `allowed` | Traffic is permitted by policy |
| `denied` | Traffic is blocked by policy |
| `unknown` | Insufficient evidence to determine |

## Enforcement plane values

| Value | Meaning |
|---|---|
| `onprem_palo` | On-prem PAN-OS firewall |
| `strata_cloud` | Strata Cloud Manager / Prisma Access |
| `unknown` | Not determinable |

## Path context values

| Value | Meaning |
|---|---|
| `vpn_prisma_access` | User is on Prisma Access |
| `vpn_gp_onprem_static` | User is on on-prem GlobalProtect with static IP |
| `sdwan_opscenter` | User is on SD-WAN path |
| `campus_non_sdwan` | User is on campus, non-SD-WAN path |
| `unknown` | Path not determinable |
