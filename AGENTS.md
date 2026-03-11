# AGENTS.md

This document is the durable execution contract for any AI agent (Codex/CoPilot) operating in this repository.  It exists to enforce **scope discipline**, **safety**, and **repeatable behaviour** across iterative runs.

> **Required pre‑flight:** Every agent must open and read the following files *before* doing anything else.  They collectively represent the single source of truth for the project.
>
> - `AGENTS.md` (this file)
> - `IMPLEMENTATION_TRACKER.md`
> - `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`
> - `docs/ai/REPO_MAP.md`
> - `docs/ai/SOURCE_REFRESH.md`

## Mission

Provide an internal, automated front‑end that answers "Am I blocked?" for a given destination, port, and time range.  Each run should make **small, test‑backed changes** that move the MVP forward within a tightly constrained scope.

## Current Phase / Scope

**MVP single‑flow:**
- One destination at a time (FQDN, URL, or IP)
- Optional single port
- Time windows: now, last_15m, last_60m
- Output verdict `allowed | denied | unknown` with path context and confidence
- Provide owner team routing recommendations with supporting evidence bundle
- Evidence must be authoritative; no guesses

The codebase currently contains a thin FastAPI API, a worker pipeline, and stubbed vendor adapters.  Only the flow above is allowed.  Vendor work is **stubbed** and must remain so unless explicitly asked to implement and verify.

## In Scope

1. Completing or refining pipeline steps (validation, context resolving, classification)
2. Adding concrete adapter implementations *only when a task is explicitly queued*.
3. Small refactors that simplify tests or reduce duplication, provided they do not expand scope.
4. Documentation, tests, and tracker updates that support the MVP.
5. Enforcing and codifying product invariants.

## Out of Scope

- Any feature outside the "Am I blocked?" verdict flow.
- Supporting multiple destinations/ports concurrently.
- UI changes beyond minimal support for the flow.
- Introducing new databases, queues, or architectures (no Kubernetes, no new storage types).
- Creating network scanning capabilities, packet crafting, or automated remediation.
- Vendor access from the API tier.
- Broad refactorings that touch unrelated subsystems.
- Hardcoding secrets or adding credentials in source control.
- Guessing or inventing vendor API behaviour not present in repository or documentation.

## Product Invariants

1. **Path context first** – evidence collection and verdicts revolve around path information.
2. **Denied requires authoritative evidence** – only system telemetry can produce a denial.
3. **Unknown is valid** and preferred over weak certainty.
4. **No scanning behaviour** – adapters must never probe networks; bounded probes are DNS/TCP/TLS/HTTP only, controlled by settings.
5. **Thin API rule** – the web tier only validates and queues; it never calls vendors.
6. **Worker‑only vendor access** – all interactions with external systems occur in the worker pipeline or its adapters.
7. **Scope discipline** – every change must be traceable to a queued task in the tracker.
8. **Minimal reversible changes** – prefer small commits; avoid large migrations without tracker approval.
9. **Secrets safety** – no credentials in source; configuration via environment or Vault.
10. **Tracker‑first workflow** – add or update tasks in `IMPLEMENTATION_TRACKER.md` before coding.
11. **No guessed vendor behaviour** – anything not documented is treated as `UNVERIFIED` and left for human review.
12. **Observed fact ≠ routing recommendation** – separate raw evidence from owner/team suggestions in models and output.
13. **Readiness before confidence** – adapters must report availability before their data can influence a verdict.

## Architecture Rules

- Monorepo Python packages under `packages/` and services under `services/`.
- FastAPI API (`services/api`) handles HTTP requests and HTML templates.
- Worker (`services/worker`) consumes a Redis queue and orchestrates steps defined under `am_i_blocked_worker.steps`.
- Adapters live in `packages/adapters/am_i_blocked_adapters` and implement `BaseAdapter`.
- Database models and shared types live in `packages/core/am_i_blocked_core`.
- Docker Compose is the approved local/infra orchestration; do not introduce Kubernetes or other orchestrators.
- Configuration is via Pydantic settings; secrets come from environment.

## Safety / Guardrails

- **Never** commit real credentials or tokens.  `.env.example` is for reference only.
- Avoid running any network calls during tests; use mocks.  Adapter contract tests exist to enforce this.
- Explicitly mark unimplemented or stubbed behaviour with `TODO` and descriptive comments.
- When adding vendor logic, update `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md` and `SOURCE_REFRESH.md` accordingly.
- Keep third‑party dependencies minimal and pinned in `pyproject.toml`/`requirements-dev.txt`.

## PAN-OS Verification Discipline

- Current PAN-OS token-validation phase is **observability-gated**.
- Do not run another PAN-OS Stage 1/Stage 2 token-validation attempt until a completed fresh deny-row record exists in `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md` for the current reproduction window.
- Do not perform blind repeated deny-hit XML retries when no fresh observability record exists.
- Stage 1/Stage 2 query construction must come from the completed fresh observability record, not stale screenshots or prior memory.
- Promotion of PAN-OS query-token assumptions from `UNVERIFIED` requires version-scoped, provenance-scoped evidence from `capture_provenance=real_capture` only.
- Template-seeded and synthetic fixtures are valid for parser-shape/selector/malformed-shape tests only; they are non-promotable for environment/version token or XPath behavior.
- Keep PAN-OS traffic-log and config workflows separate:
  - traffic-log retrieval: XML API `type=log` with Monitor-style `query=...` and `action=get` polling
  - config/rule metadata retrieval: XML API `type=config` with `action=get|show|complete` and `xpath=...`
- Do not use config/XPath evidence to promote traffic-log query tokens, and do not use traffic-log evidence to claim config/XPath correctness.
- Prefer using `scripts/panos_observe_and_validate.py` for bounded PAN-OS verification runs so observability sweep, freshest-row capture, and token subqueries stay coupled in one guarded workflow.
- PAN-OS traffic-log port field guidance for this repo:
  - canonical fields: `sport`, `dport`, `natsport`, `natdport`
  - default destination-port candidate for future validation: `dport` (scenario-scoped evidence exists for `11.0.6-h1` UDP deny signature only; broader behavior remains `UNVERIFIED`)
  - default source-port candidate if needed later: `sport`
  - `port.dst` and `port.src` must not be used as default candidates
- Destination-address token behavior remains environment/version-specific; `addr.dst` is evidenced only for the `11.0.6-h1` UDP deny signature proven by real capture and remains `UNVERIFIED` outside that scope.

## Evidence and Classification Rules

- Evidence records are normalized by adapters and contain `source`, `kind`, and sanitized `normalized` data.
- `EvidenceSource` enum defines PANOS, SCM, SDWAN, LOGSCALE, TORQ, etc.
- The classifier must resolve `denied` only when evidence includes an action != `allow` from an authoritative source.
- `unknown` should be the default when evidence is inconclusive or absent.
- Routing recommendation decisions must rely solely on evidence classification and stored mappings.

## Execution Contract

Before writing code or tests:
1. Read the five control files above.
2. Open `IMPLEMENTATION_TRACKER.md` and either locate an existing queued task or add a new one describing the intent.
3. Work only on tasks marked `Next Recommended Task` or active queue items.
4. After changes, update the tracker with progress, decisions, or new tasks.
5. Write tests covering new behaviour and ensure `make test` passes.
6. Document any architecture changes or assumptions in `docs/ai/REPO_MAP.md` and/or `SOURCE_REFRESH.md`.

## Definition of Done

A change can be considered done when:
- It implements a tracked task or clearly documents why it cannot immediately.
- There are corresponding unit/service tests and they pass locally.
- `black`, `ruff`, and `mypy` checks (if configured) are clean.
- The tracker is updated with a status entry and the `Next Recommended Task` is set.
- No vendor credentials or secrets are hardcoded.
- Documentation files reflect the change's impact.

## Test Contract

- Unit tests live under `tests/unit` and should exercise core logic without external dependencies.
- Adapter contract tests under `tests/adapters/test_adapter_contracts.py` must remain green; they ensure readiness and query interface compliance.
- Fixture and route tests cover the pipeline happy path and API surface.
- New features must include tests before review; refactors must not decrease coverage.

## Documentation Contract

- Any new function, class, or module must have a docstring.
- Major flows or design decisions must be described in `docs/` files, preferably under `docs/ai` for agent‑relevant information.
- Update `docs/ai/REPO_MAP.md` with new entrypoints, packages, or config keys.
- Update `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md` when vendor APIs or adapter behaviours change.

## Forbidden Actions

The following are strictly prohibited unless a human explicitly overrides them in writing:

- Network scanning, range sweeps, or active probing beyond the bounded probes step.
- Crafting packets, altering firewall rules, or directly modifying remote policy.
- Calling vendor APIs from the API service.
- Hardcoding credentials, API keys, tokens, or any secret in source or tests.
- Inventing undocumented vendor endpoints, response formats, or logic.
- Performing large architecture rewrites (e.g., introducing a new service class, switching frameworks) without prior tracker discussion.
- Expanding scope to multi-destination flows, automated remediation, or data collection unrelated to "Am I blocked?".
- Changing remote state anywhere in the network under any pretense.

## Iteration Protocol

- Each agent run should end by updating `IMPLEMENTATION_TRACKER.md` with:
  - Completed items
  - New or modified tasks
  - Decision notes and reasoning
  - A small `Next Recommended Task` (often the next item in the queue)
- If the workspace is in a bad compile or test state at any point, the run must stop and fix the break first before adding more tasks.
- When encountering an unknown or unclear area, add a note to `SOURCE_REFRESH.md` and mark the relevant statement `UNVERIFIED`.
- Err on the side of conservatism: prefer leaving functionality stubbed and marking `unknown` rather than guessing.
- Always leave the repository in a clean, test‑passing state before concluding a run.
