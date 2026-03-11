---
title: AI Agent Vendor Knowledge Base
description: Repo-native grounding file for AI coding agents working on the Network Self-Diagnosis + Routing Assistant MVP.
repo_intent: Internal Network Self-Diagnosis + Routing Assistant
phase: Phase 1 MVP
primary_flow: Am I blocked?
status: active
last_curated_utc: 2026-03-07T00:00:00Z
maintainers:
  - repo owners
  - AI agents operating under AGENTS.md
read_before:
  - AGENTS.md
  - IMPLEMENTATION_TRACKER.md
  - docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md
update_policy: >-
  Add only durable, implementation-relevant facts. Prefer official vendor documentation.
  If exact endpoints, fields, or auth flows are uncertain, record the uncertainty and stop short of inventing behavior.
---

# AI Agent Vendor Knowledge Base

## 1. Purpose

This file is a durable grounding layer for AI coding agents working in this repository.

Use it to:
- avoid inventing vendor/API behavior
- keep MVP work aligned to real platform constraints
- preserve hard-won project decisions across long iterative runs
- reduce drift between code, docs, tests, and vendor reality

This file is **not** permission to make assumptions. When this file says something is uncertain, treat it as uncertain.

---

## 2. How the agent must use this file

Before making code changes, the agent must:
1. Read `AGENTS.md`
2. Read `IMPLEMENTATION_TRACKER.md`
3. Read this file
4. Inspect the actual repo structure and existing code

When this file conflicts with:
- **direct user instructions** → follow the user
- **AGENTS.md** → follow AGENTS.md
- **existing working code/tests** → prefer code/tests for implementation reality, but record the discrepancy in `IMPLEMENTATION_TRACKER.md`
- **official vendor docs newly provided by the user** → prefer the newer official docs and update this file

The agent must never treat this file as a license to:
- invent undocumented endpoints
- widen MVP scope
- add scanning behavior
- claim a deterministic verdict without authoritative evidence

---

## 3. Product grounding: stable project facts

These are repo-level facts the agent should assume unless the user explicitly changes them.

### 3.1 MVP goal
The current MVP is the single flow:
**“Am I blocked?”**

The MVP answers, for one destination and a short time window:
- `allowed`
- `denied`
- `unknown`

And also returns:
- `path_context`
- `enforcement_plane`
- evidence bundle
- owner routing recommendation
- next steps

### 3.2 Core design rule
**Path context first.**
The system must determine where traffic likely egressed and where enforcement likely occurred before making strong conclusions.

### 3.3 Current path contexts
Use these canonical values unless the user changes them:
- `sdwan_opscenter`
- `vpn_prisma_access`
- `vpn_gp_onprem_static`
- `campus_non_sdwan`
- `unknown`

### 3.4 Current enforcement planes
Use these canonical values unless the user changes them:
- `strata_cloud`
- `onprem_palo`
- `unknown`
- `mixed` only if the codebase already supports it explicitly

### 3.5 Current deployment expectation
Current phase is **Docker Compose on-prem**, not Kubernetes-first.

### 3.6 Current architecture expectation
Preferred architecture:
- FastAPI web/API tier
- async worker tier
- PostgreSQL as system of record
- Redis for queue/caching
- provider adapters for vendor systems

### 3.7 Current evidence rule
A result may only be classified as `denied` when there is authoritative policy/log evidence.
Active probes are supporting signals only.

### 3.8 Current safety scope
Out of scope unless the user explicitly changes scope:
- CIDR/range scanning
- port sweeps
- packet crafting
- intrusive packet capture
- direct firewall/policy mutation
- speculative “deny” conclusions from probes alone
- future-phase bot/chatops expansion
- Kubernetes work

---

## 4. Source-of-truth order for vendor behavior

When implementing vendor integrations, use this precedence:
1. direct user-provided credentials, examples, and environment-specific notes
2. official vendor documentation
3. existing repo code and tests that already encode a working integration
4. this file
5. general memory or prior habits

If an implementation detail is not confirmed by one of the top three items, do not invent it.
Record it as an open question or implement a stub with explicit TODOs.

---

## 5. Verified vendor knowledge

Only durable, implementation-relevant facts belong here.

### 5.1 Palo Alto Networks — PAN-OS on-prem firewalls

#### What is safe to assume
- PAN-OS REST API exists, but Palo Alto explicitly states REST covers only a subset of firewall and Panorama functionality.
- PAN-OS XML API remains necessary for some important operations.
- Log retrieval is documented under the XML API path.
- Retrieving logs is an **asynchronous job-based** flow: start the log job, then poll using `action=get` and the returned `job-id`.
- Traffic logs, threat logs, system logs, GlobalProtect logs, URL logs, and other types are available under XML log retrieval.
- API authentication commonly uses an API key; do not hardcode it.
- Palo Alto documents XML/CLI/web-debug approaches to discover exact XML syntax and XPath for environment-specific calls.
- PAN-OS traffic-log port field names are `sport`, `dport`, `natsport`, and `natdport`.

#### Implementation guidance
- For MVP, treat PAN-OS as the strongest first authoritative path for `denied`.
- Keep PAN-OS traffic-log and config/XPath verification as separate tracks:
  - traffic-log token verification uses XML `type=log` and Monitor-style `query=...`
  - config/rule metadata verification uses XML `type=config` with `action=get|show|complete` and `xpath=...`
  - do not promote traffic-log tokens from config/XPath evidence
  - do not claim config/XPath correctness from traffic-log evidence
- Prefer an adapter abstraction that can use:
  - XML API for logs
  - REST or XML for rule/config metadata, depending on actual need and version support
- Keep concurrency conservative to avoid impacting the management plane.
- Build polling/retry behavior into the worker, never the request thread.
- For current repo state (`11.0.6-h1`): token-promotion attempts are observability-gated and should run through `scripts/panos_observe_and_validate.py`.
- Treat orchestrator artifacts as primary evidence state:
  - `OBSERVABILITY_RECORD.json` (always written; includes attempt signature, loop-breaker state, and gating outcome)
  - `VALIDATION_RESULT.json` (validation-focused summary)
- Treat `OBSERVABILITY_INPUT.json` as the preferred pre-run correlation artifact when stronger evidence is available (session ID, exact UI filter string, or structured UI row export).
- `docs/fixtures/panos_verification/LIVE_DENY_OBSERVABILITY_TEMPLATE.md` is optional/manual supplemental evidence only.
- Loop-breaking is mandatory: repeated no-hit attempts for materially identical signatures must be blocked unless correlation input is improved, with `OBSERVABILITY_INPUT.json` as the primary improvement mechanism.
- Promotion from `UNVERIFIED` requires `capture_provenance=real_capture` only and must remain version-scoped/scenario-scoped.
- Use `dport` as the primary destination-port candidate in future PAN-OS traffic-log validation runs; `sport` is the source-port candidate if needed later.

#### Do not assume
- exact REST endpoint versions without checking the target PAN-OS release
- that every rule metadata lookup should use REST
- that XML query shapes are identical across all examples and versions
- that more concurrency is always safe
- that `port.dst` / `port.src` are preferred PAN-OS traffic-log field names
- that destination-address token behavior is portable across PAN-OS versions/environments without real-capture proof

#### Current repo verification state (version/scenario-scoped)
- `addr.dst` is evidenced for PAN-OS `11.0.6-h1` only in the proven UDP deny signature scenario captured by `deny-hit-udp-obsgate-stage1_20260311T052621Z` and `deny-hit-udp-obsgate-stage2-addrdst-dport_20260311T052747Z`; behavior outside that scope remains `UNVERIFIED`.
- `dport` is evidenced for that same PAN-OS `11.0.6-h1` UDP deny signature scenario only; broader/cross-scenario and cross-version behavior remains `UNVERIFIED`.
- `sport`, `natsport`, and `natdport` are the correct PAN-OS traffic-log field names to retain in guidance; environment-specific query validation in this repo remains incomplete outside the proven scenario above.

#### MVP-safe role
- authoritative deny evidence source
- rule name / action / device / vsys metadata source
- possible source for GlobalProtect-related visibility depending on environment

---

### 5.2 Palo Alto Networks — Prisma Access / Strata Cloud Manager / Strata Logging Service

#### What is safe to assume
- Prisma Access logs are viewable in Strata Cloud Manager Log Viewer.
- Prisma Access provides network logs such as Traffic, Threat, URL, File, and HIP Match, plus common logs.
- Prisma Access infrastructure forwards logs to Strata Logging Service.
- Strata Cloud Manager Log Viewer works against logs stored in Strata Logging Service.
- NGFW logs are not automatically present in Strata Logging Service by default simply because Prisma Access is there; verify actual log availability.
- Decryption visibility depends on logging configuration; successful TLS events may not be available unless decryption logging is explicitly enabled.
- Prisma Access Agent activity/logs are sent to Strata Logging Service and can help distinguish policy deny from tunnel/agent/client issues.
- Strata Cloud Manager can also expose logs for supported NGFW scenarios when licensing and access are in place.

#### Implementation guidance
- Treat cloud log availability as a readiness check, not a given.
- If inbound log-query APIs are unclear or limited in the actual tenant, do not invent them.
- A safe MVP pattern is:
  - use authoritative PAN-OS on-prem path first
  - use SCM/Prisma metadata where confirmed
  - use forwarded logs or existing queryable stores where cloud query access is operationally verified
- Distinguish these concepts in code:
  - cloud policy metadata
  - cloud log presence
  - agent/tunnel troubleshooting signals
  - decryption evidence completeness

#### Do not assume
- that a simple universal cloud log query endpoint is available and approved for your tenant
- that decryption logs are complete by default
- that cloud and on-prem logs have identical fields
- that SCM alone should be the single source of truth for every path

#### MVP-safe role
- authoritative cloud-side policy/log context when confirmed
- path and tunnel-side evidence source
- decryption context source
- metadata enrichment source

---

### 5.3 Palo Alto Networks — SD-WAN / unified SASE context

#### What is safe to assume
- SD-WAN telemetry matters for path context and routing decisions.
- Site/path health and steering signals are relevant to classifying NetOps-oriented outcomes.
- In research performed for this project, a critical operational note was recorded: after generating a unified SASE access token for SD-WAN APIs, an initial profile/bootstrap call may be required before later SD-WAN calls succeed.

#### Implementation guidance
- Treat SD-WAN as a context and health source, not as the first authoritative deny source.
- Prefer an adapter design that separates:
  - site lookup
  - path health lookup
  - steering/path-change lookup
- Keep SD-WAN influence strongest for `unknown` or path-quality cases, not for direct policy-deny claims.

#### Do not assume
- exact SD-WAN endpoint shapes without current tenant validation
- exact auth headers or region headers without checking current vendor docs and tenant examples

#### MVP-safe role
- context resolver signal
- NetOps routing evidence
- incident-time path degradation evidence

---

### 5.4 Torq

#### What is safe to assume
- Torq supports API-key-based programmatic access using client ID and client secret.
- Torq public API uses bearer tokens.
- Torq bearer tokens are time-limited.
- Torq supports workflow triggers, including webhook/integration-trigger patterns.
- Torq supports synchronous and asynchronous trigger styles.
- Polling execution status by execution ID is a viable outbound-only pattern.

#### Implementation guidance
- For this MVP, Torq should remain optional and outbound-only.
- Worker should be the only service that talks to Torq.
- Store execution IDs in evidence or enrichment records if Torq is used.
- Treat Torq failures as enrichment failures, not primary diagnostic failures.

#### Do not assume
- Torq is required for MVP verdict generation
- webhook callbacks into on-prem are necessary
- all workspaces share the same exact permissions model or key type requirements

#### MVP-safe role
- optional enrichment
- downstream routing/ticket orchestration later
- non-blocking workflow execution and polling

---

### 5.5 CrowdStrike NG SIEM / Falcon LogScale

#### What is safe to assume
- CrowdStrike positions Falcon LogScale as centralized log management / observability.
- CrowdStrike Next-Gen SIEM uses the CrowdStrike Parsing Standard (CPS), which is based on ECS with CrowdStrike-specific clarifications.
- LogScale is a strong candidate query layer for forwarded logs and historical enrichment.

#### Implementation guidance
- Do **not** make CrowdStrike the first authoritative source of `denied` for MVP if Palo/Prisma authoritative logs are available.
- Use it as:
  - secondary correlation layer
  - enrichment source
  - forwarded-log query layer when official forwarding/query paths are established
- Keep field normalization explicit; do not assume Palo/Prisma fields map cleanly without a documented transform.

#### Current repo implementation status (`UNVERIFIED`)
- `check_readiness` currently performs a lightweight repository endpoint reachability check and treats HTTP `200` and `403` as reachable.
- `query_evidence` currently returns a normalized stub sample tagged:
  - `classification_role=enrichment_only_unverified`
  - `authoritative=false`
  - message prefixed with `UNVERIFIED`
- Async LogScale query-job submit/poll flows are not implemented yet in this repo and remain `UNVERIFIED`.
- These enrichment records must remain excluded from deny authority decisions in MVP.

#### Do not assume
- that LogScale field names match raw Palo/Prisma names
- that NG SIEM alone should determine the final policy verdict in MVP
- that parser mappings already exist for your exact forwarded log shape

#### MVP-safe role
- enrichment
- historical correlation
- queryable store for forwarded cloud/on-prem logs where implemented

---

## 6. MVP-specific engineering rules derived from vendor reality

### 6.1 Verdict rules
- `denied` requires authoritative deny evidence from a relevant policy/log source.
- `allowed` may use a combination of allow/no-deny evidence plus successful probes, but should still be conservative.
- `unknown` is preferred whenever telemetry is incomplete, source readiness fails, or path context is weak.

### 6.2 Separate observed facts from ownership routing
The code should distinguish:
- **observed_fact**: e.g. traffic log shows deny on rule X at time Y
- **owner_team recommendation**: e.g. route to SecOps

Never let the owner recommendation become the evidence.

### 6.3 Readiness checks must exist
Before strong classification, the system should know whether these sources are actually queryable:
- on-prem PAN-OS logs
- cloud/Strata/Prisma logs or confirmed forwarded logs
- decryption evidence availability if relevant
- SD-WAN telemetry availability if relevant

### 6.4 Probe guardrails
Bound active checks strictly:
- DNS: one normal resolution attempt
- TCP: one connect to one port
- TLS: metadata only, short timeout
- HTTP: HEAD or tightly bounded GET, short timeout, low redirect limit

Probes support context; they do not prove deny.

---

## 7. Canonical vocabulary for the repo

Use these terms consistently in code, docs, and tests.

### 7.1 Verdict
- `allowed`
- `denied`
- `unknown`

### 7.2 Owner teams
- `SecOps`
- `NetOps`
- `AppOps`
- `Unknown`
- `Vendor` only if the existing repo already models it distinctly

### 7.3 Evidence source types
Prefer normalized source names such as:
- `panos_xml`
- `panos_rest`
- `strata_cloud`
- `prisma_agent`
- `sdwan`
- `logscale`
- `probe_dns`
- `probe_tcp`
- `probe_tls`
- `probe_http`
- `torq`

### 7.4 Confidence concepts
If the repo already supports or plans these, keep them distinct:
- `path_confidence`
- `evidence_completeness`
- overall result confidence

---

## 8. Known-safe implementation biases for Codex

When choosing what to build next, bias in this order unless the user explicitly says otherwise:
1. persist requests/results in PostgreSQL
2. wire API → queue → worker correctly
3. implement one real authoritative PAN-OS deny path end-to-end
4. normalize evidence records
5. harden readiness checks and unknown reasons
6. improve SCM/Prisma enrichment only after authoritative path exists
7. add SD-WAN context improvements
8. add optional Torq/LogScale enrichments

This ordering is safer than trying to build every adapter at once.

---

## 9. Gaps that must be treated as environment-specific

These items require confirmation from repo code, environment config, or user instructions:
- exact PAN-OS versions and which REST endpoints are valid
- whether Panorama sits in front of the queried firewalls
- exact SCM tenant/region/base URL details
- whether cloud logs are queried directly or through forwarding into another store
- exact SD-WAN auth/bootstrap sequence in the tenant
- exact LogScale repository, parser, and field mappings
- exact Torq workspace permissions and workflow IDs
- SSO provider and injected identity headers
- exact redaction policy for raw evidence

If any of these become important to a task, record the assumption or blocker explicitly.

---

## 10. Update rules for future agents

When updating this file:
- keep only durable facts
- prefer official vendor docs
- note uncertainty explicitly
- remove stale assumptions when repo code proves otherwise
- do not paste large proprietary examples or secrets
- do not add speculative endpoint paths

When adding a new source, append it to the source register below.

---

## 11. Source register

This section is deliberately concise so agents can see what knowledge was curated from where.

### 11.1 Official vendor references used for this file
- Palo Alto Networks — Prisma Access logs in Strata Cloud Manager / Strata Logging Service
  - https://docs.paloaltonetworks.com/prisma-access/administration/monitor/prisma-access-logs
- Palo Alto Networks — Log Viewer in Strata Cloud Manager
  - https://docs.paloaltonetworks.com/strata-cloud-manager/getting-started/log-viewer
- Palo Alto Networks — Configure decryption logging
  - https://docs.paloaltonetworks.com/network-security/decryption/administration/monitoring-decryption/configure-decryption-logging
- Palo Alto Networks — Prisma Access Agent logs / Strata Logging Service visibility
  - https://docs.paloaltonetworks.com/prisma-access-agent/administration/troubleshoot-prisma-access-agents/download-prisma-access-agent-logs/logs-collected-by-prisma-access-agent
- Palo Alto Networks — PAN-OS REST API intro / limited scope reminder
  - https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-panorama-api/get-started-with-the-pan-os-rest-api
- Palo Alto Networks — PAN-OS XML API request types
  - https://docs.paloaltonetworks.com/pan-os/11-0/pan-os-panorama-api/pan-os-xml-api-request-types/pan-os-xml-api-request-types-and-actions/request-types
- Palo Alto Networks — PAN-OS XML API log retrieval parameters
  - https://docs.paloaltonetworks.com/pan-os/11-0/pan-os-panorama-api/pan-os-xml-api-request-types/retrieve-logs-api/api-log-retrieval-parameters
- Palo Alto Networks — PAN-OS XML API async request pattern
  - https://docs.paloaltonetworks.com/pan-os/11-0/pan-os-panorama-api/pan-os-xml-api-request-types/asynchronous-and-synchronous-requests-to-the-pan-os-xml-api
- Torq — API keys / programmatic access
  - https://kb.torq.io/en/articles/9145827-create-a-torq-api-key-enable-programmatic-access/
- Torq — Webhook/integration-trigger model
  - https://kb.torq.io/en/articles/9139841-webhook
- CrowdStrike — Falcon NG SIEM / CPS documentation
  - https://developer.crowdstrike.com/docs/ng-siem/
  - https://developer.crowdstrike.com/docs/ng-siem/cps-standard/

### 11.2 Project-local references used for this file
- AGENTS.md (repo-local; expected to exist)
- IMPLEMENTATION_TRACKER.md (repo-local; expected to exist)
- project notes and MVP research artifacts already created for this repository

---

## 12. Ready-to-copy prompt prefix for future Codex runs

Use this at the top of future Codex prompts:

> Before making changes, read and follow `AGENTS.md`, `IMPLEMENTATION_TRACKER.md`, and `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`. Treat them as the repo operating contract and vendor-grounding layer. Do not invent vendor API behavior. When vendor details are uncertain, record the uncertainty in `IMPLEMENTATION_TRACKER.md`, keep the implementation behind an adapter boundary, and prefer a stub or safe fallback over a guessed integration.

---

## 13. Optional file placement recommendation

Recommended repo path:

`docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`

If the repo already has a stronger conventions path for agent guidance, place it there instead and update prompt references accordingly.
