# Operators Runbook

## Configuring environment variables

Copy `infra/.env.example` to `infra/.env` and fill in values.

### Required for minimum operation (stub mode)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |

### PAN-OS adapter

| Variable | Description |
|---|---|
| `PANOS_FW_HOSTS` | Comma-separated firewall management hostnames |
| `PANOS_API_KEY` | PAN-OS API key with log read access |
| `PANOS_VERIFY_SSL` | `true` (recommended) or `false` for self-signed certs |
| `PANOS_MAX_CONCURRENT` | Max concurrent API requests per firewall (default: 2) |

### SCM / Prisma Access adapter

| Variable | Description |
|---|---|
| `SCM_CLIENT_ID` | OAuth2 client ID |
| `SCM_CLIENT_SECRET` | OAuth2 client secret |
| `SCM_TSG_ID` | Tenant Service Group ID |

### SD-WAN adapter

| Variable | Description |
|---|---|
| `SDWAN_API_URL` | OpsCenter API base URL |
| `SDWAN_API_KEY` | API key |

### LogScale adapter

| Variable | Description |
|---|---|
| `LOGSCALE_URL` | LogScale cluster URL |
| `LOGSCALE_REPO` | Repository / view name |
| `LOGSCALE_TOKEN` | API token |

### Torq adapter

| Variable | Description |
|---|---|
| `TORQ_CLIENT_ID` | Torq OAuth2 client ID |
| `TORQ_CLIENT_SECRET` | Torq OAuth2 client secret |

---

## Validating adapters are wired

Use the `/api/v1/readyz` endpoint (TODO: extend with source readiness detail):

```bash
curl http://localhost:8000/api/v1/readyz
# {"status": "ok"}
```

To check adapter connectivity manually, inspect worker startup logs:
```
[INFO] source readiness  source=panos  available=true  reason="2/2 firewalls reachable"
[INFO] source readiness  source=scm    available=false reason="not configured"
```

---

## Inspecting worker logs

Worker logs are structured JSON (in production) or console-formatted (in dev).

### Follow Docker Compose logs

```bash
docker compose -f infra/docker-compose.yml logs -f worker
```

### Filter by request ID

```bash
docker compose -f infra/docker-compose.yml logs worker | grep '"request_id":"<uuid>"'
```

### Key log events

| Event | Meaning |
|---|---|
| `diagnostic request submitted` | API accepted a new request |
| `source readiness` | Per-source readiness check result |
| `probe result` | Result of a bounded probe (DNS/TCP/TLS/HTTP) |
| `evidence collected` | Adapter returned evidence records |
| `adapter query failed` | Adapter returned an error (non-fatal, logged as warning) |
| `diagnostic complete` | Pipeline finished, result stored |
| `diagnostic pipeline failed` | Unhandled error in pipeline (check stack trace) |

---

## Troubleshooting unknown results

An `unknown` verdict with low confidence usually means one of:

1. **No adapters configured** – all sources show `available=false` in readiness.
   - Check env vars: `PANOS_FW_HOSTS`, `SCM_CLIENT_ID`, `LOGSCALE_URL`, etc.

2. **Adapters configured but stubs not wired** – adapters return stub evidence.
   - This is expected until adapter implementation TODOs are completed.
   - Check for `"stub": true` in evidence normalized JSON.

3. **Adapter timeout or error** – upstream unreachable.
   - Look for `adapter query failed` log events with `error=` field.
   - Verify network connectivity from the worker container to the vendor API.

4. **Time window too narrow** – logs for the period are not yet indexed.
   - Retry with `last_60m` time window.

5. **Destination not indexed** – the specific destination has no log entries.
   - This is a valid `unknown` outcome. No evidence means no verdict.

---

## Running database migrations

```bash
# With Docker services running:
docker compose -f infra/docker-compose.yml exec api alembic upgrade head

# Or directly (with DATABASE_URL set):
alembic upgrade head

# Check current migration state:
alembic current

# Roll back one migration:
alembic downgrade -1
```

---

## Health and readiness endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/healthz` | Liveness – returns 200 if the process is running |
| `GET /api/v1/readyz` | Readiness – returns 200 if the service is ready to accept traffic |
