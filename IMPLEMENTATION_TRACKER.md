# IMPLEMENTATION_TRACKER.md

This ledger tracks the current project state, objectives, workstreams, and task queue.  It is the authoritative source for planning and documentation during AI‑assisted development.

## Project

**Am I Blocked?** – internal network self‑diagnosis and routing assistant.

## Current Objective

Deliver a working MVP that accepts a single destination request and returns a verdict (`allowed`/`denied`/`unknown`) with evidence, path context, and owner team recommendations based on authoritative vendor telemetry.

## Current Phase

MVP single‑flow development.  All vendor adapters are stubs; API and worker pipelines are scaffolded and tested.

## Source of Truth Order

1. `IMPLEMENTATION_TRACKER.md`
2. `AGENTS.md`
3. `docs/ai/REPO_MAP.md`
4. `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`
5. `docs/ai/SOURCE_REFRESH.md`

## MVP Scope Snapshot

- Input: destination string, optional port, time window.
- Output: `verdict`, `path_context`, `confidence`, `routing_recommendation`, `evidence_bundle` (downloadable JSON).
- Only one destination/port pair per request.
- Verdict `denied` only with authoritative evidence; `unknown` otherwise.
- UI and API exist but are minimal and thin.
- Bounded probes and classifier implemented; adapters return stubbed evidence.

## Architecture Snapshot

- Monorepo with Python packages under `packages/` and services under `services/`.
- FastAPI service (`services/api`) handles request validation, template rendering, and queueing to Redis.
- Worker service (`services/worker`) executes pipeline steps sequentially.
- Adapters implement `BaseAdapter` and are instantiated only in the worker.
- Database models defined in core package; migrations present but DB currently in-memory for tests.

## Status Summary

- ✅ API endpoints implemented and tested.
- ✅ Worker pipeline steps scaffolded and pipeline fixture tests exist.
- 🔧 Vendor adapters stubbed with TODO comments for each.
- 🔧 DB schema/migrations present but not wired to production-level Postgres.
- 🔧 Redis placeholder exists; not fully integrated.
- 🟡 Unit tests cover request validation, context resolution, classification, and pipeline fixtures.

## Stable Workstreams

1. **Pipeline logic:** validation, context resolution, probes, correlation, classification, persistence.
2. **Adapter completion:** PAN-OS, SCM/Prisma, SD‑WAN, LogScale, Torq.
3. **API and UI fixes:** maintain thin interface, minimal templates.
4. **Infrastructure:** Docker Compose, migration support.
5. **Documentation & tracking:** keep control files current.

## Prioritized Task Queue

1. **(Next Recommended Task)** Harden tests around bounded probes to ensure failure modes return `unknown` rather than crash.
   - *Acceptance criteria:* new unit tests simulate probe timeouts/errors and assert `unknown` verdict.
2. Implement minimal Postgres connection in worker and API so that `migrate` command works with real DB (not just in-memory).  Update tests accordingly.
3. Add readiness check for LogScale adapter and normalize evidence sample.  Mark as `UNVERIFIED` in vendor KB.
4. Populate `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md` with any new vendor facts discovered while working on adapters.
5. Add UI element to download JSON evidence bundle from results page.
6. Review and expand security invariants in `docs/threat-model.md` based on current code.
7. Stub Torq workflow trigger with a non‑blocking optional step in worker (evidence only, not used for classification).
8. Implement `lookup_rule_metadata` for PAN-OS adapter with simple REST call (test against a dummy server or stub).
9. Add SQLAlchemy models for evidence and audit tables (if not present) and ensure migrations cover them.

## Active Blockers / Open Questions

- Adapter readiness semantics are lightly defined; should the worker halt if a source is unavailable or proceed with partial data?
- DB integration – in tests most persistence is in in‑memory dicts; production-ready code may need redesign.
- How will credentials and secrets be provisioned securely in Docker Compose? (ENV files currently used.)
- Is Torq integration strictly evidence enrichment or might it ever influence verdicts?  TBD.

## Decision Log

- 2026‑03‑07: Chose strictly separate API and worker tiers; vendors never called from API.
- 2026‑03‑07: Defined `unknown` as preferred default verdict to avoid guessing.

## Test Log

- Unit tests cover validation, context resolution, classification (`tests/unit`).
- Adapter contract tests exist to guarantee interface.
- Pipeline fixture tests simulate high‑level flows using mocks.

## Iteration Journal

- Initial repository scaffolding reviewed on 2026‑03‑07.  Control files created and hardened.
- 2026-03-07 (active): Started queue item #1 to harden bounded-probe failure handling tests so probe timeouts/errors degrade to `unknown` rather than crash.

## Next Recommended Task

Harden bounded‑probes tests to ensure the pipeline degrades safely when probes fail (see Prioritized Task Queue item #1).

## Deferred / Later

- Multi‑destination batching.
- Automated owner routing beyond simple rule lookup.
- Kubernetes or cloud deployment targets.
- Graphical UI enhancements.
