# Threat Model

## Scope

This threat model covers the Am I Blocked? internal diagnostic application. It is intended for internal use only and must not be exposed to the public internet.

---

## Trust boundary summary

| Boundary | Notes |
|---|---|
| Reverse proxy → API | Identity header must be injected by the proxy. The API trusts this header. |
| API → Worker | Internal job queue (Redis). Not directly accessible. |
| Worker → Vendor APIs | Outbound only. Credentials in env vars. |
| Worker → Torq | Outbound trigger only. No inbound webhooks. |

---

## Abuse scenarios

### 1. Scanning abuse

**Risk**: A user submits a series of requests to discover which ports/hosts are reachable, effectively performing a network scan.

**Mitigations**:
- Single destination + optional single port only – CIDR ranges are rejected at input validation.
- Rate limiting should be applied at the reverse proxy or application layer (TODO for production).
- Audit log records all requests with requester identity.
- Bounded probes are disabled-able via `ENABLE_BOUNDED_PROBES=false`.

**Residual risk**: A determined user could submit many individual requests. Rate limiting is required before production use.

### 2. Credential exposure

**Risk**: Vendor API credentials (`PANOS_API_KEY`, `SCM_CLIENT_SECRET`, `LOGSCALE_TOKEN`, etc.) are exposed via logs or error messages.

**Mitigations**:
- Credentials are in environment variables, not source code.
- Structured logs do not log credential values.
- Error messages from adapters do not echo credential values.
- Raw evidence (which may contain log data) is not included in public evidence bundles.

**Residual risk**: Container runtime environment may expose env vars to sufficiently privileged users. Use secrets management (Vault, cloud secrets manager) for production.

### 3. Sensitive destination exposure

**Risk**: Diagnostic requests reveal internal host topology or network structure via the audit log.

**Mitigations**:
- Audit log access should be restricted to SecOps/NetOps roles (TODO: RBAC).
- Evidence bundles contain redacted copies of evidence by default.

### 4. Unauthorized access

**Risk**: An unauthenticated user submits diagnostic requests.

**Mitigations**:
- The application relies on a reverse proxy (nginx/Cloudflare Access) to inject the identity header.
- The `APP_IDENTITY_HEADER` setting controls which header is trusted.
- If the header is absent, the requester is recorded as `anonymous` – consider blocking anonymous requests in production.

**Residual risk**: If deployed without a reverse proxy enforcing authentication, anyone can submit requests. **Do not expose this service directly to the internet.**

### 5. Torq trigger abuse

**Risk**: A user tricks the system into triggering Torq workflows.

**Mitigations**:
- Torq adapter is outbound only; no inbound webhooks.
- Torq triggers should only fire on specific high-confidence verdicts (TODO: wire in production).

---

## Logging and retention concerns

- All requests generate an audit record with requester identity, destination, time window, and actions taken.
- Structured JSON logs include `request_id` and `actor` for correlation.
- Log retention policy must be defined by the operator – recommend 90 days minimum for audit logs.
- Logs may contain destination hostnames and IPs – treat as sensitive.

---

## RBAC

Current MVP state: identity is injected via reverse-proxy header. No application-level RBAC is implemented.

**Recommended production model**:
- All employees: can submit requests and view their own results.
- SecOps / NetOps: can view all results and audit logs.
- Admins: can configure source adapters.

TODO: Implement role-based access control using identity header claims or a separate authz service.

---

## Explicit non-goals (safety guardrails)

The following are explicitly **not** implemented and must never be added:

- Port scanning or IP range scanning
- Intrusive packet capture
- Packet crafting
- Autonomous rule changes to PAN-OS, SCM, SD-WAN, or Torq
- Inbound webhooks from Torq
