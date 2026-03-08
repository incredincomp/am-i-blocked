# CODEX_TRACKER_UPDATE_PROMPT.md

Use this prompt when you want Codex to update `IMPLEMENTATION_TRACKER.md` without letting it become an append-only dump.

## Usage

1. Run this from the repository root.
2. Use it when the repo already has:
   - `AGENTS.md`
   - `IMPLEMENTATION_TRACKER.md`
   - `docs/ai/REPO_MAP.md`
   - `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`
   - `docs/ai/SOURCE_REFRESH.md`
3. Paste the **Prompt Body** into Codex.
4. Optionally append one short sentence naming the immediate reason for the tracker refresh.

## Prompt Body

```text
Before editing `IMPLEMENTATION_TRACKER.md`, read:
- `AGENTS.md`
- `IMPLEMENTATION_TRACKER.md`
- `docs/ai/REPO_MAP.md`
- `docs/ai/AI_AGENT_VENDOR_KNOWLEDGE_BASE.md`
- `docs/ai/SOURCE_REFRESH.md`

Your task is to update `IMPLEMENTATION_TRACKER.md` so it remains a clean, current planning ledger rather than an append-only dump.

Tracker update rules:
1. Preserve useful history, but do not let historical entries masquerade as current state.
2. Reconcile contradictions. If a newer completed checkpoint supersedes an older blocker or transitional state, either:
   - remove the stale statement from active sections, or
   - move it into a clearly marked historical/superseded section.
3. Keep active sections current:
   - `Current Phase`
   - `Architecture Snapshot`
   - `Status Summary`
   - `Prioritized Task Queue`
   - `ROI-Ranked TODO Backlog`
   - `Active Blockers / Open Questions`
   - `Next Recommended Task`
4. Do not leave resolved blockers in `Active Blockers / Open Questions`.
5. Do not leave obsolete priorities in `Prioritized Task Queue`.
6. Do not let documentation-only or enrichment-only work outrank the first real authoritative MVP path unless direct user instructions explicitly change priorities.
7. Treat the first real authoritative PAN-OS deny path as higher priority than Torq, broad docs expansion, SCM/SD-WAN deepening, or LogScale deepening, unless the repo state clearly proves otherwise.
8. Keep the tracker aligned with these MVP truths:
   - path context first
   - denied requires authoritative evidence
   - unknown is preferred over weak certainty
   - LogScale remains non-authoritative/enrichment-only unless intentionally verified and implemented
   - worker-only vendor access
   - API remains thin
9. Keep `Decision Log` for durable decisions, not checkpoint noise.
10. Keep `Iteration Journal` chronological, but compress or label superseded checkpoint notes when they no longer help current planning.
11. If old checkpoint entries contain outdated blockers, mark them as historical rather than leaving them ambiguous.
12. If a section header or structure is malformed, fix it.
13. Do not invent vendor behavior while updating the tracker.
14. Prefer concise, high-signal tracker content over exhaustive repetition.

When updating the tracker:
- preserve completed work already achieved
- preserve important historical milestones
- improve clarity and current usefulness
- keep the next task bounded and implementation-focused

Recommended tracker hygiene edits when needed:
- soften any opening sentence that claims the tracker outranks direct user instructions, `AGENTS.md`, or current code/tests
- add a clearly named historical/superseded section if old checkpoints are still valuable but no longer current
- move durable strategic choices into `Decision Log`
- keep transient implementation details in `Iteration Journal`

At the end of the run, return:
- what sections were reconciled
- what stale or superseded items were moved, removed, or rewritten
- the exact `Next Recommended Task`
- any assumptions you had to make
```

## Optional one-line preface for broader implementation prompts

Use this short guard block at the top of normal Codex implementation runs when you want to force better tracker hygiene:

```text
Tracker hygiene requirement:
When updating `IMPLEMENTATION_TRACKER.md`, do not only append. Reconcile stale state, move superseded blockers out of active sections, keep the task queue current, and ensure the next recommended task reflects the highest-ROI unfinished MVP work.
```

## Notes

This prompt is meant to improve tracker quality, not to change product scope.
It should not cause Codex to invent vendor behavior, widen the MVP, or demote the current highest-value work of implementing the first real authoritative PAN-OS deny path unless the user explicitly changes priorities.
