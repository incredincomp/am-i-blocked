# Roadmap

## Week 1–2: Core "Am I Blocked?" workflow

### Goals
- Establish the monorepo scaffold and Python package structure
- Implement the full diagnostic pipeline with stub adapters
- Implement the rules-based classifier with all initial rules
- Implement bounded probes (DNS, TCP, TLS, HTTP)
- Implement context resolver with signal-based inference
- Working FastAPI service with UI form and result page
- Unit and integration tests for all pipeline steps
- Docker Compose stack operational
- Alembic migrations scaffolded
- Basic structured logging with request correlation IDs

### Deliverables
- Diagnostic requests can be submitted and polled
- Stub adapters return marked evidence
- Probes run and contribute to classification
- `unknown` verdict returned when evidence is incomplete

---

## Week 3–4: Evidence and report enrichment

### Goals
- Wire PAN-OS adapter: XML API log retrieval with job polling
- Wire LogScale adapter: async query job + result normalization
- Wire SCM adapter: OAuth2 + security rule metadata lookup
- Persist results to PostgreSQL (replace in-memory stores)
- Wire Redis job queue for API → Worker handoff
- Improve evidence normalization and redaction model
- Add rate limiting (per-requester, configurable)
- Enrich result page with rule names and log timestamps

### Deliverables
- Real evidence flowing from at least one PAN-OS source
- Results persisted to DB and retrievable after worker restart
- Evidence bundle JSON downloadable from result page

---

## Week 5+: Torq and ownership enrichment

### Goals
- Wire SD-WAN adapter: OpsCenter site/path/health queries
- Wire Torq adapter: outbound trigger on high-confidence deny verdict
- Add owner enrichment: look up owner team from CMDB or mapping config
- Add RBAC: restrict audit log access to SecOps/NetOps roles
- Add Prisma Access / SCM decryption rule lookup
- Improve path confidence scoring with multi-signal weighting
- Operator runbook validation and documentation polish
- Consider webhook receiver for async Torq result delivery

### Deliverables
- End-to-end flow: deny detected → Torq workflow triggered
- SD-WAN path degradation signals integrated into classification
- Owner routing recommendations enriched with CMDB data

---

## Future / post-MVP considerations

- Teams bot integration (out of scope for MVP)
- Full ticketing system integration (Jira, ServiceNow)
- Kubernetes deployment manifests
- Multi-tenant / multi-org support
- Historical trend dashboard
- Automated retests on verdict change
