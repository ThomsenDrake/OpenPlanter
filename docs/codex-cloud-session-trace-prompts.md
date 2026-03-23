# Codex Cloud Prompt Pack: Session Trace Work

All paths below are repo-relative. Run each cloud Codex session from the repo root.

Global rules for every cloud session:

- You are not alone in the repo. Only edit the files explicitly assigned to you.
- Do not revert unrelated changes and do not expand your write scope.
- Before editing, read the files you own plus the referenced docs.
- At the end, run the most targeted verification you can for your scope and report exactly what you ran.
- End with a focused commit on your branch.

## Execution Order

1. Run Prompt 1 first.
2. After Prompt 1, run Prompts 2, 3, and 6 in parallel.
3. After Prompt 3 lands, run Prompt 4.
4. After Prompt 4 lands, run Prompt 5.
5. After Prompts 4 and 5 land, run Prompt 7.

## Parallelism Map

- Prompt 1: sequential
- Prompt 2: parallel with 3 and 6
- Prompt 3: parallel with 2 and 6
- Prompt 4: sequential after 3
- Prompt 5: sequential after 4
- Prompt 6: parallel with 2 and 3
- Prompt 7: sequential after 4 and 5

## Prompt 1

Status: sequential first  
Depends on: nothing  
Can run in parallel with: nothing
Suggested branch: `chore/session-trace-v2-spec`

```text
Read docs/session-trace-deepdive-2026-03-23.md and VISION.md.

You are not alone in the repo. Only edit the file listed below. Do not implement code yet.

Create a concrete v2 session trace spec for OpenPlanter.

Own only:
- docs/session-trace-v2-spec.md

Define:
- Canonical metadata schema
- Canonical replay/event envelope
- Minimum durable per-turn record
- Provenance fields needed for evidence drill-down
- Failure taxonomy (rate_limit, timeout, cancelled, degraded, resumed_from_partial, etc.)
- Compatibility strategy for old Python and newer desktop sessions
- Rollout plan and test matrix

Keep the design additive and backwards-compatible. Existing sessions must remain readable without destructive migration.

Deliverable:
- A spec that is concrete enough for parallel implementation by Python, Rust, and frontend sessions

Verification:
- Re-read the finished spec for internal consistency and make sure every field needed by later prompts is explicitly named

End by creating a focused commit.
```

## Prompt 2

Status: parallel after 1  
Depends on: Prompt 1  
Can run in parallel with: Prompts 3 and 6
Suggested branch: `chore/session-trace-python-v2`

```text
Read docs/session-trace-deepdive-2026-03-23.md and docs/session-trace-v2-spec.md.

You are not alone in the repo. Only edit the files listed below. Do not touch desktop Rust or frontend files.

Implement the Python-side session/replay compatibility layer.

Own only:
- agent/runtime.py
- agent/replay_log.py
- tests/test_session.py
- tests/test_session_complex.py
- tests/test_replay_log.py

Goals:
- Support the v2 schema from the spec
- Preserve read compatibility with legacy metadata and replay logs
- Preserve child conversation/subtask replay semantics
- Do not rewrite old logs in place
- Add tests for mixed old/new session directories

Verification:
- Run the narrowest relevant Python tests for session and replay behavior
- Report exactly which tests passed and any gaps

End by creating a focused commit.
```

## Prompt 3

Status: parallel after 1  
Depends on: Prompt 1  
Can run in parallel with: Prompts 2 and 6
Suggested branch: `chore/session-trace-desktop-v2`

```text
Read docs/session-trace-deepdive-2026-03-23.md and docs/session-trace-v2-spec.md.

You are not alone in the repo. Only edit the files listed below. Do not touch wiki.rs or frontend files.

Implement the desktop-side session contract, logging completeness, and failure taxonomy.

Own only:
- openplanter-desktop/crates/op-core/src/session/replay.rs
- openplanter-desktop/crates/op-core/src/events.rs
- openplanter-desktop/crates/op-tauri/src/commands/session.rs
- openplanter-desktop/crates/op-tauri/src/commands/agent.rs
- openplanter-desktop/crates/op-tauri/src/bridge.rs

Goals:
- Read both legacy and newer session metadata/replay shapes
- Emit the minimum durable per-turn record on every solve
- Add explicit failure states and preserve cancel/resume behavior
- Remove the per-append full replay scan if possible
- Keep changes backwards-compatible

Verification:
- Run the narrowest relevant Rust tests for replay/session/bridge behavior
- Report exactly which tests passed and any gaps

End by creating a focused commit.
```

## Prompt 4

Status: sequential after 3  
Depends on: Prompt 3  
Can run in parallel with: nothing important
Suggested branch: `chore/session-trace-overview-provenance`

```text
Read docs/session-trace-deepdive-2026-03-23.md, docs/session-trace-v2-spec.md, and the current desktop session/bridge code.

You are not alone in the repo. Only edit the file listed below. Do not edit frontend files.

Implement backend provenance enrichment for the investigation overview.

Own only:
- openplanter-desktop/crates/op-tauri/src/commands/wiki.rs

Goals:
- Replace shallow revelation provenance with evidence-ready references
- Include stable IDs or references that let the UI jump to exact replay entries, event records, artifacts, or wiki updates
- Preserve existing overview behavior where possible
- Add tests for dedupe/order/provenance behavior

If you need a payload field that does not exist yet, use the fields added by Prompt 3 rather than introducing a second contract.

Verification:
- Run the narrowest relevant Rust tests around overview/provenance behavior
- Report exactly which tests passed and any gaps

End by creating a focused commit.
```

## Prompt 5

Status: sequential after 4  
Depends on: Prompt 4  
Can run in parallel with: nothing important
Suggested branch: `chore/session-trace-overview-ui`

```text
Read docs/session-trace-deepdive-2026-03-23.md and the backend overview/provenance changes.

You are not alone in the repo. Only edit the files listed below. Do not edit Rust backend files.

Implement a curated replay + evidence-linked overview UI.

Own only:
- openplanter-desktop/frontend/src/api/types.ts
- openplanter-desktop/frontend/src/api/invoke.ts
- openplanter-desktop/frontend/src/components/InvestigationPane.ts
- openplanter-desktop/frontend/src/components/OverviewPane.ts
- openplanter-desktop/frontend/src/components/GraphPane.ts

Goals:
- Show evidence links for revelations/actions/gaps
- Surface context continuity and failure/recovery state
- Make curated replay feel like the primary UX, not a thin summary card
- Keep the visual language consistent with the existing app

Verification:
- Run the narrowest frontend checks available for this app
- If no automated frontend verification exists, state that clearly and do a careful code-level consistency pass

End by creating a focused commit.
```

## Prompt 6

Status: parallel after 1  
Depends on: Prompt 1  
Can run in parallel with: Prompts 2 and 3  
Best as: design/spike, not merge-critical
Suggested branch: `chore/session-change-sets-spike`

```text
Read docs/session-trace-deepdive-2026-03-23.md and VISION.md.

You are not alone in the repo. Only edit the files listed below. Do not touch backend files.

Design the next step after basic trace unification: ontology-backed session change sets.

Own only:
- openplanter-desktop/frontend/src/graph/sessionBaseline.ts
- openplanter-desktop/frontend/src/graph/cytoGraph.ts
- docs/session-change-sets.md

Goals:
- Explain how “new this session” should evolve from a baseline filter into durable change sets
- If low-risk, add small non-breaking scaffolding in the frontend for future change-set support
- Do not require backend contract changes in this pass
- Produce a concrete design with rollout phases

Verification:
- Re-read the design doc and any scaffolding changes for consistency with the existing graph/session behavior
- If you add code, run the narrowest relevant checks available

End by creating a focused commit.
```

## Prompt 7

Status: sequential last  
Depends on: Prompts 4 and 5  
Can run in parallel with: nothing
Suggested branch: `chore/session-handoffs`

```text
Read docs/session-trace-deepdive-2026-03-23.md, the final session trace contract, and the new provenance UI/backend.

You are not alone in the repo. Keep your write scope narrow and centered on the handoff/export path.

Implement a durable handoff/checkpoint package for investigations.

Own only new files plus any minimal glue you need for export/import:
- Prefer new files under openplanter-desktop/
- Add docs at docs/session-handoffs.md

Goals:
- Define or implement a checkpoint artifact containing objective, open questions, candidate actions, evidence index, and replay span
- Make it easy to resume or review an investigation from a stable snapshot
- Keep the design aligned with the ontology-first vision
- Avoid broad refactors outside the handoff path

Assume the provenance and replay contract from earlier prompts is already in place.

Verification:
- Run the narrowest relevant checks for the export/import path you implement
- Report exactly what passed and any follow-up work still needed

End by creating a focused commit.
```
