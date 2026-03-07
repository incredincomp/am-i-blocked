# Am I Blocked? – Network Self-Diagnosis + Routing Assistant

**Am I Blocked?** is an internal, self-service diagnostic tool that helps employees answer:

> _"Is my traffic to this destination being blocked — and by whom?"_

It determines the likely **verdict** (`allowed | denied | unknown`), **enforcement plane**, **path context**, and **owner team routing recommendation**, backed by authoritative telemetry from your security and network stack.

---

## MVP scope

This is an MVP focused on a single primary workflow:

| Input | Output |
|---|---|
| Destination (URL / FQDN / IP) | Verdict: `allowed \| denied \| unknown` |
| Optional port | Enforcement plane: `onprem_palo \| strata_cloud \| unknown` |
| Time window (`now \| last_15m \| last_60m`) | Path context, confidence scores, evidence cards |
| | Owner team routing + next steps |
| | Downloadable JSON evidence bundle |

### What is stubbed vs implemented

| Area | Status |
|---|---|
| FastAPI API layer | ✅ Implemented |
| Server-rendered UI | ✅ Implemented |
| Request validation and guardrails | ✅ Implemented |
| Context resolver | ✅ Implemented |
| Classifier (rules-based) | ✅ Implemented |
| Bounded probes (DNS/TCP/TLS/HTTP) | ✅ Implemented |
| Worker pipeline orchestrator | ✅ Implemented |
| PAN-OS adapter | 🔧 Stub (TODO: XML API job polling) |
| SCM / Prisma adapter | 🔧 Stub (TODO: OAuth2 + API queries) |
| SD-WAN adapter | 🔧 Stub (TODO: OpsCenter API) |
| LogScale adapter | 🔧 Stub (TODO: async query jobs) |
| Torq adapter | 🔧 Stub (TODO: workflow trigger + polling) |
| DB persistence | 🔧 Schema + migration ready; in-memory store used for now |
| Redis job queue | 🔧 Placeholder in worker main loop |

---

## Architecture overview

```
┌──────────┐  POST /api/v1/am-i-blocked   ┌──────────┐
│  Browser  │ ──────────────────────────▶ │   API    │
│ or API    │                              │ (FastAPI)│
│  client   │ ◀── 202 {request_id} ─────  └────┬─────┘
└──────────┘                                   │ enqueue job (Redis)
                                               ▼
                                        ┌──────────────┐
                                        │    Worker    │
                                        │  (pipeline)  │
                                        └──────┬───────┘
                          ┌─────────────┬──────┴──────┬──────────────┐
                          ▼             ▼             ▼              ▼
                      PAN-OS         SCM /        LogScale        SD-WAN
                      Adapter       Prisma        Adapter         Adapter
                      (stub)        Adapter       (stub)          (stub)
                                    (stub)
```

See `docs/architecture.md` for the full component diagram and request flow.

---

## Local dev quickstart

### Prerequisites

- Python 3.12+
- Docker + Docker Compose (for full stack)
- `make` (optional, for convenience commands)

### Setup

```bash
# Clone and enter the repo
git clone <repo-url>
cd am-i-blocked

# Install all packages in editable mode
make install
# or: pip install -r requirements-dev.txt

# Configure environment
cp infra/.env.example .env
# Edit .env with your adapter credentials (all optional for stub mode)
```

### Run locally (stubs only, no Docker)

```bash
make run-api
# API now at http://localhost:8000
# UI at http://localhost:8000/
# Swagger at http://localhost:8000/docs
```

### Run with Docker Compose (full stack)

```bash
make docker-up
# or: docker compose -f infra/docker-compose.yml up --build
```

### Run database migrations

```bash
make migrate
# or: alembic upgrade head
```

---

## How to run tests

```bash
make test
# or: pytest -v

# With coverage:
make test-cov
```

---

## Project structure

```
am-i-blocked/
├── packages/
│   ├── core/           # Shared models, enums, config, logging
│   └── adapters/       # Vendor adapter stubs (panos, scm, sdwan, logscale, torq)
├── services/
│   ├── api/            # FastAPI web service + UI templates
│   └── worker/         # Async diagnostic pipeline worker
├── infra/
│   ├── docker-compose.yml
│   └── .env.example
├── migrations/         # Alembic migration scripts
├── tests/
│   ├── unit/           # Unit tests (validate, classify, context)
│   ├── fixtures/       # End-to-end pipeline fixture tests
│   ├── adapters/       # Adapter contract tests (mocked HTTP)
│   └── routes/         # FastAPI smoke tests
├── docs/               # Architecture, threat model, runbook, roadmap
├── Makefile
├── pyproject.toml
└── requirements-dev.txt
```