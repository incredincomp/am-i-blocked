# Developer Setup

## Prerequisites

- Python 3.12 or later
- `pip` and optionally `venv`
- Docker + Docker Compose (for full integration stack)
- `make` (optional)

---

## Local development (no Docker)

### 1. Create a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
make install
# or manually:
pip install -r requirements-dev.txt
```

This installs all packages in **editable mode** (`-e`), so local source changes are immediately reflected.

### 3. Configure environment

```bash
cp infra/.env.example .env
# Edit .env – all vendor credentials are optional for stub mode
```

### 4. Start the API

```bash
make run-api
# FastAPI starts at http://localhost:8000
# Swagger UI: http://localhost:8000/docs
# UI: http://localhost:8000/
```

### 5. Run tests

```bash
make test
# or: pytest -v
```

---

## Running with Docker Compose

```bash
make docker-up
# or: docker compose -f infra/docker-compose.yml up --build
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- API (port 8000)
- Worker

### Run migrations after Docker is up

```bash
# With Docker services running:
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
# or locally against the Docker Postgres:
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/amiblockeddb alembic upgrade head
```

---

## Project layout

```
packages/core/am_i_blocked_core/
  enums.py           # Domain enums (Verdict, PathContext, etc.)
  models.py          # Pydantic v2 request/response models
  db_models.py       # SQLAlchemy 2.x ORM models
  config.py          # Pydantic settings (env-driven)
  logging_helpers.py # structlog setup

packages/adapters/am_i_blocked_adapters/
  base.py            # BaseAdapter ABC
  panos/             # PAN-OS adapter stub
  scm/               # SCM / Prisma adapter stub
  sdwan/             # SD-WAN adapter stub
  logscale/          # LogScale adapter stub
  torq/              # Torq adapter stub

services/api/am_i_blocked_api/
  __init__.py        # FastAPI app factory
  routes/
    api.py           # /api/v1/* routes
    ui.py            # HTML routes
  templates/
    index.html       # Landing page
    result.html      # Result page

services/worker/am_i_blocked_worker/
  pipeline.py        # Pipeline orchestrator
  main.py            # Worker entry point
  steps/
    validate_request.py
    source_readiness_check.py
    context_resolver.py
    bounded_probes.py
    authoritative_correlation.py
    classify.py
    persist_and_report.py

migrations/
  env.py             # Alembic env
  versions/
    0001_initial.py  # Initial schema migration
```

---

## Adding a new adapter

1. Create a new directory under `packages/adapters/am_i_blocked_adapters/<name>/`
2. Create `__init__.py` implementing `BaseAdapter`
3. Implement `check_readiness()` and `query_evidence()`
4. Add configuration fields to `packages/core/am_i_blocked_core/config.py`
5. Register the adapter in `services/worker/am_i_blocked_worker/steps/source_readiness_check.py`
6. Register the adapter in `services/worker/am_i_blocked_worker/steps/authoritative_correlation.py`
7. Add adapter contract tests in `tests/adapters/`

---

## Linting and formatting

```bash
make lint          # Check only
make lint-fix      # Fix in place
```

Uses [ruff](https://docs.astral.sh/ruff/) for both linting and formatting.
