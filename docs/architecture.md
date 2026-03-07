# Architecture

## Overview

Am I Blocked? is a monorepo-style Python application structured around a **thin API layer** and a **separate async worker** that orchestrates all vendor interactions.

## Component diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser / API client                     │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTPS
                    ┌────────────▼────────────┐
                    │   Reverse Proxy (nginx)  │
                    │  injects identity header │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      API service         │
                    │  (FastAPI / Uvicorn)     │
                    │  - POST /api/v1/am-i-blocked │
                    │  - GET  /api/v1/requests/{id}│
                    │  - GET  /api/v1/requests/{id}/result │
                    │  - GET  /healthz  /readyz│
                    │  - UI pages: / and /requests/{id} │
                    └────────────┬────────────┘
                                 │ enqueue job
                    ┌────────────▼────────────┐
                    │         Redis            │
                    │      (job queue)         │
                    └────────────┬────────────┘
                                 │ dequeue
                    ┌────────────▼────────────┐
                    │      Worker service      │
                    │   (diagnostic pipeline)  │
                    │  1. validate_request     │
                    │  2. source_readiness     │
                    │  3. context_resolver     │
                    │  4. bounded_probes       │
                    │  5. authoritative_corr.  │
                    │  6. classify             │
                    │  7. persist_and_report   │
                    └──────┬──────────────────┘
           ┌───────────────┼──────────────────────────┐
           ▼               ▼                          ▼
     ┌──────────┐   ┌──────────┐              ┌──────────────┐
     │  PAN-OS  │   │  SCM /   │   SD-WAN     │  LogScale    │
     │ Adapter  │   │  Prisma  │   Adapter    │  Adapter     │
     │ (stub)   │   │  Adapter │   (stub)     │  (stub)      │
     └──────────┘   │  (stub)  │              └──────────────┘
                    └──────────┘
                                 ┌──────────┐
                                 │   Torq   │
                                 │  Adapter │
                                 │  (stub)  │
                                 └──────────┘
                    ┌────────────────────────┐
                    │       PostgreSQL        │
                    │  requests / context /   │
                    │  evidence / result /    │
                    │  audit tables           │
                    └────────────────────────┘
```

## Why the API layer is thin

The API service's only job is to:
1. Authenticate the requester (via reverse-proxy header)
2. Validate and accept the request payload
3. Enqueue a job for the worker
4. Return a `request_id` for polling

**The API never calls vendor APIs directly.** This separation:
- Keeps the web process simple and fast
- Allows the worker to be independently scaled and retried
- Prevents timeouts from blocking the web tier
- Makes vendor adapter failures invisible to the web layer

## Request flow

```
Client                API                  Redis           Worker
  │                    │                     │                │
  │ POST /am-i-blocked │                     │                │
  │──────────────────▶│                     │                │
  │                    │ validate payload    │                │
  │                    │ create request_id   │                │
  │                    │ store in DB/memory  │                │
  │                    │─── enqueue job ───▶│                │
  │                    │                     │                │
  │ 202 {request_id}  │                     │                │
  │◀──────────────────│                     │                │
  │                    │                     │── dequeue ───▶│
  │                    │                     │                │ validate_request
  │                    │                     │                │ source_readiness
  │                    │                     │                │ context_resolver
  │                    │                     │                │ bounded_probes
  │                    │                     │                │ authoritative_correlation
  │                    │                     │                │ classify
  │                    │                     │                │ persist_and_report
  │                    │                     │                │
  │ GET /requests/{id} │                     │                │
  │──────────────────▶│                     │                │
  │ 200 {result}      │                     │                │
  │◀──────────────────│                     │                │
```

## Adapter boundaries

Each adapter in `packages/adapters/` must implement the `BaseAdapter` interface:

```python
class BaseAdapter(ABC):
    async def check_readiness(self) -> dict[str, Any]: ...
    async def query_evidence(...) -> list[EvidenceRecord]: ...
```

Adapters are only instantiated by the worker, never by the API service.

## Data flow and redaction

Evidence records have three layers:
- `normalized`: sanitized, safe for logging and display
- `redacted`: a redacted copy of normalized, safe for general distribution
- `raw_ref`: pointer to privileged raw log data (not included in public evidence bundle)

## Packages

| Package | Purpose |
|---|---|
| `am-i-blocked-core` | Shared enums, Pydantic models, SQLAlchemy DB models, config, logging |
| `am-i-blocked-adapters` | Vendor adapter interfaces and stubs |
| `am-i-blocked-api` | FastAPI service |
| `am-i-blocked-worker` | Pipeline worker |
