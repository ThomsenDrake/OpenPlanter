# Ontology-First Session Unification Plan

## Context

OpenPlanter's VISION.md defines "ontology as the universal API" as the project's core differentiator, but the session trace deep dive (`docs/session-trace-deepdive-2026-03-23.md`) reveals the current system behaves more like "logs plus post-hoc summaries." Three structural problems drive this gap:

1. **VISION.md lacks measurable goals** — all success criteria are qualitative, making it impossible to verify progress toward the vision.
2. **The provenance pipeline is truncated** — `wiki.rs` already computes `RevelationTraceRefs` (turn_id, event_id, source_refs, evidence_refs) but the Rust `OverviewRevelationProvenanceView` struct only serializes 2 of 8 fields the frontend already expects. This means evidence drill-down is dead code.
3. **Replay entries lack v2 envelopes** — `bridge.rs` writes bare `ReplayEntry` records to `replay.jsonl` without `event_id`, `turn_id`, or provenance, forcing `wiki.rs` to use fragile text-matching heuristics to cross-reference replay with events.

This plan addresses all four tiers of improvements: provenance struct expansion, session contract unification, frontend drill-down, and strategic architectural alignment — plus SMART goals for every phase of the roadmap.

---

## Tier 1: Provenance Struct + SMART Goals (Highest ROI)

### 1.1 Expand `OverviewRevelationProvenanceView` Rust struct

**Problem**: The Rust struct has 2 fields; the frontend TypeScript interface has 8. The `wiki.rs` revelation builder already computes `RevelationTraceRefs` with all the data, but discards it at serialization time.

**Files**:
- `openplanter-desktop/crates/op-core/src/events.rs` (lines 241-245)
- `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs` (lines 1608-1621)

**Changes**:

In `events.rs`, expand the struct to match `frontend/src/api/types.ts` (lines 142-151):

```rust
pub struct OverviewRevelationProvenanceView {
    pub source: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub step_index: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub turn_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub event_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub replay_seq: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub replay_line: Option<u64>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub source_refs: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence_refs: Vec<String>,
}
```

### 1.2 Wire `RevelationTraceRefs` into overview output

**Problem**: `wiki.rs` line 1608 looks up `candidate_trace_refs` from the pre-computed `trace_refs` map but only passes it to `build_revelation_id()` — the actual provenance fields are not populated.

**File**: `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs` (lines 1608-1621)

**Change**: Populate the expanded struct from `candidate_trace_refs`:

```rust
provenance: OverviewRevelationProvenanceView {
    source: candidate.source.to_string(),
    step_index: if candidate.step_index == 0 { None } else { Some(candidate.step_index) },
    turn_id: candidate_trace_refs.and_then(|r| r.turn_id.clone()),
    event_id: candidate_trace_refs.and_then(|r| r.event_id.clone()),
    replay_seq: Some(candidate.replay_seq),
    replay_line: candidate_trace_refs.and_then(|r| r.replay_line),
    source_refs: candidate_trace_refs.map(|r| r.source_refs.clone()).unwrap_or_default(),
    evidence_refs: candidate_trace_refs.map(|r| r.evidence_refs.clone()).unwrap_or_default(),
},
```

### 1.3 Add SMART goals to VISION.md

**Problem**: VISION.md has zero quantified success criteria. The roadmap (Section 9) defines four phases with qualitative deliverables only.

**File**: `VISION.md` (Section 9, after each phase's bullet list)

**Change**: Add a `**Success Criteria**` subsection under each phase with tiered metrics (minimum threshold + aspirational target):

#### Phase 0: Foundation
1. **Schema CRUD**: Define ontology schema (>=3 object types, >=2 link types) via REST API. Minimum: <2s p99. Target: <500ms p99.
2. **Ingest benchmark**: Import entities from CSV. Minimum: 1K entities in <5 min. Target: 10K entities in <5 min on a 4-core/16GB machine.
3. **Entity resolution**: Rule-based dedup on reference dataset. Minimum: >=80% exact-match. Target: >=90% exact + >=70% fuzzy.
4. **Session durability**: Every turn writes v2-conformant `turns.jsonl`. Minimum: interrupted sessions lose <=2 turns. Target: <=1 turn loss (verified by kill-test).
5. **Cross-runtime compat**: Both Python and desktop can read each other's sessions. Minimum: >=80% of fixture matrix. Target: 100%.

#### Phase 1: Core Visualization & Search
1. **Graph performance**: Expand node to 3 hops, filter 2+ types, >=500 entities. Minimum: >=15fps. Target: >=30fps.
2. **Search recall**: Top-5 results for test suite. Minimum: >=60% of 50 queries. Target: >=80%.
3. **Provenance drill-down**: Revelation cards resolve to evidence. Minimum: >=50% of cards have >=1 drill-down link. Target: 100%.
4. **Connector SDK**: Working connectors pass ingestion test. Minimum: 2 connectors. Target: 3+ (PostgreSQL, CSV, REST API).
5. **Audit completeness**: Minimum: >=90% coverage. Target: 100% of data operations logged.

#### Phase 2: AI & Advanced Analytics
1. **RAG accuracy**: Ontology-grounded answers (human eval). Minimum: >=50% correct, <=10% hallucination. Target: >=70% correct, <=5% hallucination.
2. **NL query translation**: Valid ontology queries. Minimum: >=40% of 40-query suite. Target: >=60%.
3. **Entity extraction**: NER F1 on reference corpus. Minimum: >=60% F1. Target: >=75% F1.
4. **Dashboard builder**: Non-technical user creates 3-widget dashboard. Minimum: <20 min. Target: <10 min.
5. **Pipeline reliability**: 100 consecutive runs. Minimum: <=5% failure. Target: <=2% failure.

#### Phase 3: Actions, Agents & Operational Workflows
1. **Action round-trip**: Flag entity, write-back reflected in ontology. Minimum: <60s. Target: <30s.
2. **Agent sandboxing**: Restricted agent cannot access out-of-scope entities. Minimum: 0 escapes in 10-op test. Target: 0 escapes in 20-op test.
3. **Workflow reliability**: 5-step event-triggered workflow. Minimum: >=90% over 50 runs. Target: >=95%.
4. **Pattern search**: Subgraph pattern on >=100K entities. Minimum: <10s. Target: <5s.

#### Phase 4: Scale & Ecosystem
1. **Horizontal scale**: 10M+ entities, 3-hop traversal. Minimum: <5s p95. Target: <2s p95.
2. **Air-gapped**: Full function without network. Minimum: 24h. Target: 72h+.
3. **Multi-tenancy isolation**: Cross-tenant query provably blocked. Minimum: verified by test suite.

Additionally add a **Success Metrics Dashboard** subsection (Section 9.5) defining ongoing operational metrics:
- Session contract conformance rate (% of sessions with valid v2 metadata)
- Provenance coverage (% of revelation cards with >=1 drill-down target)
- Cross-runtime compatibility score (% of test matrix passing)
- Mean time to evidence (seconds from overview card click to evidence display)

---

## Tier 2: Session Contract Unification (Replay V2 Envelopes)

### 2.1 Thread turn context into `LoggingEmitter`

**Problem**: `bridge.rs` writes `ReplayEntry` records without `turn_id` or `event_id` because the `LoggingEmitter` doesn't have access to the active turn context. The turn lifecycle is managed at a higher level in `bridge.rs`.

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

**Change**: Add an `Arc<Mutex<Option<TurnContext>>>` to `LoggingEmitter` (or a similar shared state) that gets set at turn-start and cleared at turn-end. `TurnContext` holds `turn_id: String`, `session_id: String`, `event_start_seq: u64`. The `append_replay_entry` method reads this context to populate turn-scoped fields.

### 2.2 Wrap replay writes in v2 envelopes

**Problem**: Replay entries at lines 480, 633, 773, 853, 922, 1020 of `bridge.rs` are bare `ReplayEntry` objects — no `schema_version`, `envelope`, `event_id`, `turn_id`, `channel`, `provenance`, or `compat` fields.

**Files**:
- `openplanter-desktop/crates/op-tauri/src/bridge.rs` (all `ReplayEntry` construction sites)
- `openplanter-desktop/crates/op-core/src/session/replay.rs` (reader already handles v2 via `adapt_enveloped_entry`)

**Change**: Modify `append_replay_entry` (line 508) to wrap each `ReplayEntry` in a v2 envelope before writing. The envelope includes:
- `schema_version: 2`
- `envelope: "openplanter.trace.replay.v2"`
- `event_id`: derived from session_id + replay seq
- `turn_id`: from the shared turn context (#2.1)
- `channel: "replay"`
- `compat.legacy_role`: the original `entry.role`

The reader in `replay.rs` already handles v2 envelopes via `adapt_enveloped_entry()`, so backward compatibility is preserved.

### 2.3 Share `event_id` between replay and event projections

**Problem**: When the same logical step produces both an event (in `events.jsonl`) and a replay entry (in `replay.jsonl`), they currently get different IDs (or the replay entry has no ID at all). `wiki.rs` must use text-matching heuristics to correlate them.

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

**Change**: When writing a step summary, generate one `event_id` and use it for both the event stream entry and the replay entry. The event_id format: `evt:{session_id}:{seq:06d}`. The replay seq can differ from the event seq, but the `event_id` field on the replay envelope should reference the event stream's event_id.

### 2.4 Populate `generated_from` provenance

**Problem**: Both runtimes write empty `generated_from` in event provenance.

**Files**:
- `openplanter-desktop/crates/op-tauri/src/commands/session.rs` (lines 479-494)
- `agent/runtime.py` (line 497)

**Change**: Thread the active model provider and model name from settings into the event-writing functions. Populate:
```json
"generated_from": {
  "provider": "openai",
  "model": "gpt-4o",
  "request_id": null,
  "conversation_id": null
}
```

### 2.5 Upgrade Python `ReplayLogger` to v2 envelope mode

**Problem**: `agent/replay_log.py` writes legacy `header`/`call` records. New Python sessions should write v2 replay envelopes for consistency.

**File**: `agent/replay_log.py`

**Change**: Add an `envelope_mode` parameter (default `"v2"`). When set, emit v2-wrapped records. The existing `header`/`call` shapes remain readable by the Rust adapter in `replay.rs`.

---

## Tier 3: Frontend Drill-Down + Conformance Tests

### 3.1 Artifact/wiki drill-down navigation

**Problem**: `OverviewPane.ts` can parse locators and find replay entries, but clicking an `evidence_ref` that points to `artifact:patches/patch-d0-s1-1.patch` or `wiki:findings.md` does nothing.

**File**: `openplanter-desktop/frontend/src/components/OverviewPane.ts` (after line 521)

**Change**: Extend locator resolution to handle three new target types:
1. `evidence_ref` matching `artifact:*` — open the artifact file in a viewer panel
2. `evidence_ref` matching `wiki:*` — navigate to the wiki page
3. `source_ref` matching `event:*` — scroll to and highlight the event in a raw event view (or show a toast with event details if no event inspector exists yet)

### 3.2 Populate `evidence_refs` at event write time

**Problem**: Events are written with empty `evidence_refs` arrays, forcing post-hoc matching.

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

**Change**: When the bridge writes a `step.summary` event (around line 689), check the step's `tool_calls` for any artifact paths written during that step. Include those as `evidence_refs` in the event envelope. When writing a `result` event, include `source_refs` pointing to the event_span of the turn.

### 3.3 Writer conformance tests

**Problem**: No automated verification that Python and Rust writers produce spec-conformant output.

**Files**:
- `tests/test_session_contract_conformance.py` (new)
- Rust tests in `session.rs` or new test module

**Change**: Create a shared conformance test that:
1. Writes a 3-turn session using each runtime
2. Reads back with the other runtime's reader
3. Asserts every replay entry has `event_id`, `turn_id`, `channel`, and `provenance.source_refs`
4. Asserts every turn record has non-empty `provenance.event_span`
5. Asserts metadata `capabilities` flags match actual file presence

### 3.4 Cross-runtime compatibility test matrix

**Problem**: No test verifies that Python-written sessions are readable by the Rust reader and vice versa.

**Files**:
- `tests/fixtures/` (session fixtures from both runtimes)
- `tests/test_cross_runtime_compat.py` (new)
- Rust integration test

**Change**: Create >=10 fixture sessions (mix of legacy Python, desktop, and v2-native) and verify both readers can load them without error, producing equivalent canonical in-memory models.

### 3.5 Model attribution in events

**File**: `openplanter-desktop/crates/op-tauri/src/commands/session.rs`

**Change**: Read the active `provider` and `model` from the app's `Settings` state and pass them to `append_session_event` for the `generated_from` provenance subfield.

---

## Tier 4: Strategic Architectural Alignment

### 4.1 Session change sets — session-local durability (Phase 2 of session-change-sets.md)

**Problem**: Graph baseline filtering in `sessionBaseline.ts` is ephemeral (in-memory only). Change sets don't survive a page reload.

**Files**:
- `openplanter-desktop/frontend/src/graph/sessionBaseline.ts`
- `openplanter-desktop/frontend/src/graph/cytoGraph.ts` (lines 585-631)

**Change**: When a session baseline is captured, persist a `GraphSessionChangeSetV0` object alongside session artifacts. On session resume, reload the change set. The schema is already defined in `docs/session-change-sets.md`.

### 4.2 Handoff packages — wire `checkpoint_ref`

**Problem**: Session handoffs (defined in `docs/session-handoffs.md`) reference `checkpoint_ref` in the turn continuity model, but nothing writes it.

**Files**:
- `openplanter-desktop/crates/op-tauri/src/commands/session.rs` (turn record writing)
- New handoff export command (or extension to existing session commands)

**Change**: When a handoff is exported, write a `checkpoint_ref` into the most recent turn record pointing to the handoff artifact path. When a session is resumed from a handoff, set `continuity.mode: "imported"` and `continuity.checkpoint_ref` to the handoff path.

### 4.3 Event detail inspector UI

**Problem**: No UI surface exists to view raw v2 event envelopes. Users can't verify provenance claims.

**Files**: New frontend component

**Change**: Add a collapsible event inspector panel that:
1. Opens when a user clicks a `source_ref` or `event_id` link in a revelation card
2. Shows the full v2 event envelope as formatted JSON
3. Highlights provenance fields (event_id, turn_id, source_refs, evidence_refs)
4. Provides "copy event ID" and "view in events.jsonl" actions

### 4.4 Ontology-backed session objects (RFC 0001 Stage 2)

**Problem**: Questions, claims, evidence, and tasks are rich in the investigation_state.json but are not queryable ontology objects. Investigations remain siloed.

**Files**:
- `agent/investigation_state.py` (Python-side typed state)
- New Rust module for investigation state reading/writing

**Change**: Promote RFC 0001 objects (entities, claims, evidence, questions, tasks) to graph-queryable objects:
1. On turn completion, project typed objects from `investigation_state.json` into the wiki knowledge graph
2. Add object type definitions for `Question`, `Claim`, `Evidence`, `Task` to the ontology schema
3. Enable graph visualization of investigation structure (questions linked to claims linked to evidence)

This is the highest-complexity item and depends on Tiers 1-3 being stable.

---

## Implementation Order

```
Tier 1 (do first — highest ROI, ~3 files):
  #1.1 Expand OverviewRevelationProvenanceView struct   → events.rs
  #1.2 Wire RevelationTraceRefs into overview output    → wiki.rs
  #1.3 Add SMART goals to VISION.md                     → VISION.md

Tier 2 (do next — foundational infra, ~4 files):
  #2.1 Thread turn context into LoggingEmitter          → bridge.rs
  #2.2 Wrap replay writes in v2 envelopes               → bridge.rs, replay.rs
  #2.3 Share event_id between replay and events         → bridge.rs
  #2.4 Populate generated_from provenance               → session.rs, runtime.py
  #2.5 Upgrade Python ReplayLogger to v2                → replay_log.py

Tier 3 (do after — UX polish + validation, ~6 files):
  #3.1 Artifact/wiki drill-down in OverviewPane         → OverviewPane.ts
  #3.2 Populate evidence_refs at event write time       → bridge.rs
  #3.3 Writer conformance tests                         → new test files
  #3.4 Cross-runtime compatibility test matrix          → new test files + fixtures
  #3.5 Model attribution in events                      → session.rs

Tier 4 (do last — strategic, ~8+ files):
  #4.1 Session change set durability                    → sessionBaseline.ts, cytoGraph.ts
  #4.2 Handoff checkpoint_ref wiring                    → session.rs, new command
  #4.3 Event detail inspector UI                        → new frontend component
  #4.4 Ontology-backed session objects                  → investigation_state.py, new Rust module
```

### Dependency Graph

```
#1.1 → #1.2 → #3.1
                ↓
#2.1 → #2.2 → #2.3 → #3.2
        ↓       ↓
       #3.3 → #3.4
                ↓
         #4.1, #4.2, #4.3, #4.4
```

Items #1.3 (SMART goals), #2.4 (generated_from), #2.5 (Python replay), and #3.5 (model attribution) have no blockers and can be done in parallel with any tier.

---

## Critical Files Reference

| File | Tier | Change |
|------|------|--------|
| `openplanter-desktop/crates/op-core/src/events.rs` | 1 | Expand provenance struct (6 new fields) |
| `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs` | 1 | Wire trace refs into serialized output |
| `VISION.md` | 1 | Add inline SMART goals per phase + metrics dashboard |
| `openplanter-desktop/crates/op-tauri/src/bridge.rs` | 2,3 | Turn context threading, v2 envelopes, shared event_ids, evidence_refs |
| `openplanter-desktop/crates/op-core/src/session/replay.rs` | 2 | Verify v2 envelope reader path handles new fields |
| `openplanter-desktop/crates/op-tauri/src/commands/session.rs` | 2,3 | generated_from provenance, model attribution |
| `agent/runtime.py` | 2 | generated_from provenance |
| `agent/replay_log.py` | 2 | v2 envelope mode |
| `openplanter-desktop/frontend/src/components/OverviewPane.ts` | 3 | Artifact/wiki drill-down navigation |
| `openplanter-desktop/frontend/src/api/types.ts` | — | Already correct (no changes needed) |
| `openplanter-desktop/frontend/src/graph/sessionBaseline.ts` | 4 | Change set persistence |
| `openplanter-desktop/frontend/src/graph/cytoGraph.ts` | 4 | Change set reload on resume |
| `agent/investigation_state.py` | 4 | Ontology object projection |

---

## Verification

### Tier 1 Verification
1. `cargo build` in `openplanter-desktop/` — no compile errors
2. `cargo test` in `openplanter-desktop/` — all existing tests pass, especially `wiki.rs` revelation tests
3. Launch `cargo tauri dev`, open a session with history, open Overview pane
4. Inspect network/console: revelation cards should now include `turn_id`, `event_id`, `replay_seq`, `replay_line`, `source_refs`, `evidence_refs` in their JSON
5. Review VISION.md for coherent, tiered SMART goals under each phase

### Tier 2 Verification
1. `cargo build` + `cargo test` pass
2. Run a new session via desktop, complete 2-3 turns
3. Inspect `replay.jsonl` — entries should be v2 envelopes with `schema_version: 2`, `event_id`, `turn_id`
4. Inspect `events.jsonl` — entries should have populated `generated_from` provenance
5. Verify existing legacy sessions still load correctly (backward compat)
6. Run Python runtime, complete a turn — verify `replay.jsonl` has v2 envelopes

### Tier 3 Verification
1. In the Overview pane, click a revelation card with evidence_refs — verify navigation to artifact/wiki
2. Run conformance test suite — all assertions pass for both runtimes
3. Run cross-runtime matrix — Python-written sessions readable by Rust, and vice versa
4. Inspect events for model attribution in `generated_from`

### Tier 4 Verification
1. Capture a graph baseline, reload the page — change set persists
2. Export a handoff, start a new session from it — `continuity.checkpoint_ref` populated
3. Click an event_id link in a revelation — event inspector opens with full envelope
4. After investigation turns, check graph for `Question`/`Claim`/`Evidence` nodes linked to session
