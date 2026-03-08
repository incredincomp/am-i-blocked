# SOURCE_REFRESH.md

**Purpose**

Maintain a living log of vendor facts, verification status, and areas that require further investigation.  This helps keep the AI agent honest about what it knows.

## How Entries Are Recorded

- Each entry includes date/time, source (file or external doc), a concise fact, and a status.
- Status values: `VERIFIED`, `UNVERIFIED`, `CHANGED`, `NEEDS_CONFIRMATION`.
- Confidence and implementation impact are noted, along with any follow‑up actions.

## Verification Log

_No entries yet._

## Open Verification Needs

- **PAN-OS XML API job syntax** – no concrete example in repo. Status: `UNVERIFIED` (2026-03-07).
- **SCM log query JSON schema** – assumed but not present. Status: `UNVERIFIED` (2026-03-07).
- **SD-WAN controller auth & endpoints** – completely unspecified. Status: `NEEDS_CONFIRMATION` (2026-03-07).
- **LogScale authoritative vs enrichment capability** – unverified whether it can supply denial evidence. Status: `UNVERIFIED` (2026-03-07).
- **Torq webhook payload** – not defined; assumed optional. Status: `UNVERIFIED` (2026-03-07).

