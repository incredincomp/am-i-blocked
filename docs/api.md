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

---

### GET /api/v1/requests/{request_id}/result

Retrieve the diagnostic result for a completed request.

**Response** `200 OK`:

```json
{
  "request_id": "550e8400-...",
  "verdict": "denied",
  "enforcement_plane": "strata_cloud",
  "path_context": "vpn_prisma_access",
  "path_confidence": 0.7,
  "result_confidence": 0.9,
  "evidence_completeness": 0.5,
  "summary": "Cloud policy deny detected in Strata/Prisma evidence.",
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

**Response** `404 Not Found` if the request does not exist or result is not yet available.

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
