# REPO_MAP.md

**Purpose**

Provide an up‑to‑date map of the repository for an AI agent.  It describes directories, entrypoints, config, and known gaps.

## Top-Level Layout

```
/ (repo root)
├── AGENTS.md
├── IMPLEMENTATION_TRACKER.md
├── README.md
├── docs/               # developer docs & architecture
│   ├── ai/             # agent‑focused docs (this folder)
│   ├── architecture.md
│   ├── api.md
│   ├── developer-setup.md
│   ├── operators-runbook.md
│   ├── roadmap.md
│   └── threat-model.md
├── infra/              # deployment helper files
│   ├── docker-compose.yml
│   └── .env.example
├── migrations/         # Alembic migration scripts
├── packages/           # Python libraries (core + adapters)
│   ├── core/           # shared models, config, logging
│   └── adapters/       # vendor adapter interfaces & stubs
├── services/           # runnable services
│   ├── api/            # FastAPI application
│   └── worker/         # async diagnostic pipeline
├── tests/              # test suite
├── Makefile
├── pyproject.toml
└── requirements-dev.txt
```

## Service / Package Map

| Path | Description |
|------|-------------|
| `packages/core/am_i_blocked_core` | shared enums (`EvidenceKind`, `Verdict`, etc.), Pydantic models, SQLAlchemy models, config (`Settings`), logging helpers |
| `packages/adapters/am_i_blocked_adapters` | base adapter class and per‑vendor modules (`panos`, `scm`, `sdwan`, `logscale`, `torq`) |
| `services/api/am_i_blocked_api` | FastAPI application and route definitions (`routes/api.py`, `routes/ui.py`), HTML templates under `templates/` |
| `services/worker/am_i_blocked_worker` | pipeline orchestration (`pipeline.py`) and step modules under `steps/` |

## Entrypoints

- `services/api/main.py` (invoked by `make run-api` or `uvicorn`): starts FastAPI web server.
- `services/worker/main.py` (invoked by `make run-worker` or Python): runs an async loop pulling jobs from Redis and calling `pipeline.run_diagnostic`.
- `Makefile` targets such as `run-api`, `run-worker`, `migrate`, `test`, `docker-up`.

## Config and Environment Loading

Configuration is managed via Pydantic `Settings` in `am_i_blocked_core.config`.  Values are read from environment variables or `.env` file when running locally.

Key settings include:
- `database_url` (Postgres connection string)
- vendor credentials (`panos_fw_hosts`, `panos_api_key`, `scm_client_id`, etc.)
- timeouts for bounded probes and job execution
- Redis URL
- log level and format

## Queue / Job Flow

- API receives POST `/api/v1/am-i-blocked` and validates payload with Pydantic models.
- API creates a `request_id`, stores a minimal record (in-memory or DB depending on config), enqueues a job to Redis.
- Worker reads job, executes pipeline steps sequentially: validation, readiness, context resolution, bounded probes, authoritative correlation, classify, persist and report.
- Worker writes results back to result store (in-memory dict for tests; later Postgres).

## Database / Migrations

- `migrations/` contains Alembic revision files (`0001_initial.py` etc.).
- Models defined in `packages/core/am_i_blocked_core/db_models.py`.
- Current state: schema ready, but production DB not yet wired (tests use in‑memory DB or mocks).

## Tests

- Unit tests in `tests/unit` for core logic (`test_validate_request.py`, `test_context_resolver.py`, `test_classify.py`).
- Adapter contract tests in `tests/adapters/test_adapter_contracts.py` ensure readiness and evidence query signatures.
- Route tests in `tests/routes/test_api_routes.py` exercise the FastAPI endpoints.
- Fixture tests in `tests/fixtures/test_pipeline_fixtures.py` simulate end‑to‑end pipeline execution with mocks.

Run tests with `make test` or `pytest -v`.  Coverage via `make test-cov`.

## Commands

Common make targets:

```
make install         # install dependencies in editable mode
make run-api         # start the API service
make run-worker      # start the worker loop
make migrate         # run alembic upgrade head
make test            # run pytest
make test-cov        # pytest with coverage
make docker-up       # bring up full stack with Docker Compose
```

## Known Seams / Extension Points

- Adapter interface (`BaseAdapter`) allows new vendors to be added with minimal impact.
- Pipeline steps are discrete modules under `services/worker/am_i_blocked_worker/steps`; new steps can be injected by editing `pipeline.py`.
- Settings class centralises configuration; adding a new adapter requires adding new settings keys.
- UI templates are simple Jinja2 files; additional pages can be introduced under `services/api/am_i_blocked_api/templates`.
- Database models are defined in `db_models.py`; migrations add new tables.

## Observed Gaps or Unclear Areas

- Implementation of PostgreSQL persistence is incomplete; most code uses in-memory stores for testing.
- Redis integration is currently a placeholder; worker loop may not actually connect to Redis.
- No explicit health check endpoints for individual adapters beyond readiness stubs.

