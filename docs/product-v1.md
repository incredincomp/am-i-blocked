# AIB Product v1 — Architecture Milestone

Status: **ACTIVE**  
Linear owner: **DEV-281**  
Execution lane: **DEV-282**  
Baseline: `main@1ca5d1b6f35fada8813c3cbbebf79757d2d8b95f` (2026-09-27)

## Product intent

Am I Blocked? becomes a self-hosted network-security evidence appliance, not a vendor-specific ping button.

The product answers one bounded question:

> What happened to this connection, where was the decision made, what evidence supports that conclusion, and how certain are we?

The existing evidence engine remains the product core. Product v1 adds a stable appliance boundary, a replaceable connector boundary, and a public-safe synthetic demonstration surface.

## 1. Appliance boundary

The supported v1 appliance is Docker Compose first.

Core-owned surfaces:

- API and authenticated operator UI
- diagnostic orchestration
- bounded DNS/TCP/TLS/HTTP probes
- context, correlation, classification, confidence, and routing policy
- PostgreSQL persistence and audit history
- Redis job lifecycle
- evidence bundle and operator handoff artifacts
- connector discovery/client logic
- product/version identity and health/readiness

The core must not contain customer-specific vendor policy logic.

Customer/vendor credentials belong to the connector side of the trust boundary. Vendor traffic remains worker/connector initiated; the API tier never calls vendor systems.

Kubernetes packaging, SaaS multi-tenancy, licensing/entitlements, marketplace mechanics, and automatic updater implementation are not Product v1 acceptance requirements.

## 2. Connector protocol v1

Product v1 replaces "vendor module linked into the worker" as the long-term integration contract with a versioned connector protocol.

The protocol must expose these semantic operations:

1. **Manifest / capabilities**
   - protocol version
   - connector identity and version
   - vendor/product identity
   - supported evidence kinds and query capabilities
   - supported authority roles
   - configuration-schema identity, never secret values

2. **Readiness**
   - ready / degraded / unavailable
   - bounded reason
   - latency when available
   - per-capability readiness when useful

3. **Bounded evidence query**
   - one diagnostic request context
   - one destination and optional port
   - bounded time window
   - normalized evidence response compatible with core evidence semantics
   - no scanning/range expansion
   - deterministic timeout/failure semantics

Core owns the final authority policy. A connector may declare what authority modes it supports; it may not unilaterally make its own evidence authoritative for a customer.

### Compatibility

- Protocol major-version mismatch fails closed.
- Minor evolution is additive/backward-compatible.
- Connector failures must produce explicit degraded/unavailable readiness, not fabricated evidence.
- Existing `BaseAdapter` integrations remain usable through a compatibility bridge while connectors migrate incrementally.
- PAN-OS is the first real compatibility target, not a special case in the protocol.

### Initial transport target

HTTP + JSON on the private appliance/Compose network is the Product v1 transport target. Protocol models should remain separable from transport so a later transport change does not redefine evidence semantics.

## 3. Synthetic public demo

The public demo is a deterministic simulator of the product experience, not an Internet diagnostic proxy.

It must use the same normalized result/evidence presentation contracts as the appliance and must never send traffic to a destination supplied by a public user.

Initial scenario catalog:

- firewall policy deny
- SSE/SWG policy deny
- DNS resolution failure
- TLS failure
- degraded evidence / `unknown`

The demo should visibly exercise:

- request lifecycle
- path/enforcement context
- source readiness
- authoritative vs enrichment evidence
- confidence and evidence completeness
- evidence cards
- operator handoff / evidence receipt

The synthetic provider must be clearly identifiable as synthetic in evidence metadata.

## 4. Security and evidence invariants

Productization must preserve:

- `denied` requires authoritative evidence
- `unknown` is valid and preferred to weak certainty
- readiness is evaluated before source data influences confidence/verdict
- observed facts remain separate from routing recommendations
- raw privileged evidence is not copied into general evidence bundles
- no network scanning, range sweeps, packet crafting, or automated policy changes
- no arbitrary public-target probing
- no vendor API access from the API tier

## 5. Migration strategy

Do not rewrite all adapters.

1. Freeze Product v1 protocol models and compatibility tests.
2. Add a compatibility bridge for the current `BaseAdapter` contract.
3. Implement a synthetic connector through the new protocol.
4. Drive public-demo scenarios through the normal result/evidence UI path.
5. Migrate PAN-OS behind the connector boundary without changing its proven evidence-authority behavior.
6. Only then expand vendor breadth.

## 6. Milestone acceptance

Product v1 architecture is frozen when:

- this product boundary is represented in repo control docs;
- versioned connector manifest/readiness/query contracts exist in code;
- compatibility/version-failure behavior has tests;
- current adapters can operate through a bounded compatibility bridge;
- a synthetic connector can generate the initial demo scenario catalog;
- the demo reaches the real result/evidence presentation path without external target egress;
- PAN-OS semantics are not encoded as core protocol assumptions;
- all inherited safety/evidence invariants remain green.

## Deferred after boundary freeze

- licensing and entitlement enforcement
- paid support/maintenance packaging
- signed release/update channel and automatic rollback implementation
- connector marketplace/discovery service
- broad vendor connector expansion
- multi-destination diagnostics
