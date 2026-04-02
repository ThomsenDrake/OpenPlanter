# Ontology-First Session Unification Implementation Plan

This plan implements all 4 tiers across Rust (op-core, op-tauri), TypeScript (frontend), and Python (agent/) codebases. Tasks follow the dependency graph from the spec, with independent items parallelized.

---

## Task 1: Expand `OverviewRevelationProvenanceView` Rust struct (Tier 1.1)

**File**: `openplanter-desktop/crates/op-core/src/events.rs` (lines 240-245)

Add 6 new fields to match the frontend TypeScript interface at `frontend/src/api/types.ts` (lines 142-151):

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

**Depends on**: Nothing
**Verification**: `cargo build` in `openplanter-desktop/`

---

## Task 2: Wire `RevelationTraceRefs` into overview output (Tier 1.2)

**File**: `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs` (lines 1614-1621)

Populate the expanded struct from `candidate_trace_refs` (which is already looked up at line 1608). Change the `provenance:` construction block to populate all new fields from `candidate_trace_refs` and `candidate.replay_seq`.

**Depends on**: Task 1
**Verification**: `cargo build` + `cargo test` in `openplanter-desktop/`; revelation cards should include `turn_id`, `event_id`, `replay_seq`, `source_refs`, `evidence_refs` in JSON output.

---

## Task 3: Add SMART goals to VISION.md (Tier 1.3)

**File**: `VISION.md` (Section 9, after each phase's bullet list)

Add a `**Success Criteria**` subsection under each of the 5 phases with tiered metrics as specified in the plan document (sections 1.3). Also add a **Success Metrics Dashboard** subsection (Section 9.5) with ongoing operational metrics.

**Depends on**: Nothing (parallel with all tasks)

---

## Task 4: Thread turn context into `LoggingEmitter` (Tier 2.1)

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

Add a `turn_context: Arc<Mutex<Option<TurnContext>>>` field to the `LoggingEmitter` struct (line 252). `TurnContext` holds `turn_id: String`, `session_id: String`, `event_start_seq: u64`. Update `LoggingEmitter::new()` (line 381) to initialize it. Add `set_turn_context()` and `clear_turn_context()` methods. The `append_replay_entry` method (line 508) reads this context to populate turn-scoped fields.

**Depends on**: Nothing

---

## Task 5: Wrap replay writes in v2 envelopes (Tier 2.2)

**Files**:
- `openplanter-desktop/crates/op-tauri/src/bridge.rs` (all `ReplayEntry` construction sites at lines ~480, 633, 773, and `append_replay_entry` at line 508)
- `openplanter-desktop/crates/op-core/src/session/replay.rs` (verify `adapt_enveloped_entry` at line 282 handles new fields)

Modify `append_replay_entry` to wrap each `ReplayEntry` in a v2 envelope before writing, including `schema_version: 2`, `envelope: "openplanter.trace.replay.v2"`, `event_id`, `turn_id` (from TurnContext), `channel: "replay"`, and `compat.legacy_role`.

The reader at `replay.rs` line 282 (`adapt_enveloped_entry`) already handles v2 envelopes, so backward compat should be preserved. Verify the reader path handles any new fields.

**Depends on**: Task 4

---

## Task 6: Share `event_id` between replay and event projections (Tier 2.3)

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

When writing a step summary (around line 689 `append_event_value("step", ...)`) and the corresponding replay entry (line 654), generate one `event_id` and use it for both. Format: `evt:{session_id}:{seq:06d}`. The `append_event_value` already returns `AppendedEventMeta` with `event_id` -- use that to populate the replay envelope.

**Depends on**: Task 5

---

## Task 7: Populate `generated_from` provenance (Tier 2.4)

**Files**:
- `openplanter-desktop/crates/op-tauri/src/commands/session.rs` (lines 479-489) -- add `generated_from` with provider/model from settings
- `agent/runtime.py` (line 497) -- populate `generated_from` with actual provider/model instead of `{}`

Thread the active model provider and model name from settings into the event-writing functions.

**Depends on**: Nothing (parallel)

---

## Task 8: Upgrade Python `ReplayLogger` to v2 envelope mode (Tier 2.5)

**File**: `agent/replay_log.py`

The Python ReplayLogger already writes v2 envelopes (it includes `schema_version`, `envelope`, `event_id`, `turn_id`, `channel`, `provenance`, `compat` fields in both `write_header` and `log_call`). Verify completeness against the spec:
- Ensure `generated_from` in `log_call` provenance includes `provider` and `model` (currently only has `conversation_id`)
- Add provider/model to the `actor` block in `log_call` (currently missing)

**Depends on**: Nothing (parallel)

---

## Task 9: Artifact/wiki drill-down navigation in OverviewPane (Tier 3.1)

**File**: `openplanter-desktop/frontend/src/components/OverviewPane.ts`

Extend `navigateLocator()` (line 626) to handle three new target types:
1. `evidence_ref` matching `artifact:*` -- open the artifact file in a viewer panel (dispatch a custom event or use Tauri invoke)
2. `evidence_ref` matching `wiki:*` -- already partially handled by `extractWikiPath()`, ensure it covers `wiki:` prefix in evidence_refs
3. `source_ref` matching `event:*` -- show a toast with event details or scroll to event

Also extend `isActionableLocator()` (line 682) to return true for `artifact:` prefixed locators.

**Depends on**: Tasks 1, 2 (needs provenance fields populated)

---

## Task 10: Populate `evidence_refs` at event write time (Tier 3.2)

**File**: `openplanter-desktop/crates/op-tauri/src/bridge.rs`

When writing a `step.summary` event (around line 689), check the step's `tool_calls` for any artifact paths written during that step (patch artifacts are already tracked at lines 699-733). Include those as `evidence_refs` in the event's provenance. When writing a `result` event, include `source_refs` pointing to the event_span of the turn.

**Depends on**: Task 6

---

## Task 11: Writer conformance tests (Tier 3.3)

**Files**:
- `tests/test_session_contract_conformance.py` (new)
- Optionally Rust tests in session module

Create a conformance test that:
1. Writes a 3-turn session using the Python runtime
2. Reads back and asserts every replay entry has `event_id`, `turn_id`, `channel`, and `provenance.source_refs`
3. Asserts every turn record has non-empty `provenance.event_span`
4. Asserts metadata `capabilities` flags match actual file presence

**Depends on**: Tasks 5, 8

---

## Task 12: Cross-runtime compatibility test matrix (Tier 3.4)

**Files**:
- `tests/fixtures/` (session fixtures from both runtimes)
- `tests/test_cross_runtime_compat.py` (new)

Create fixture sessions (mix of legacy Python, desktop, and v2-native) and verify both readers can load them without error.

**Depends on**: Task 11

---

## Task 13: Model attribution in events (Tier 3.5)

**File**: `openplanter-desktop/crates/op-tauri/src/commands/session.rs`

Read the active `provider` and `model` from the app's `Settings` state and pass them to `append_session_event` for the `generated_from` provenance subfield. This is related to Task 7 but specifically focuses on wiring Settings state access.

**Depends on**: Task 7

---

## Task 14: Session change set durability (Tier 4.1)

**Files**:
- `openplanter-desktop/frontend/src/graph/sessionBaseline.ts` (169 lines)
- `openplanter-desktop/frontend/src/graph/cytoGraph.ts`

Persist `GraphSessionChangeSet` objects alongside session artifacts (via Tauri invoke to write JSON). On session resume, reload the change set. The schema is already defined in `sessionBaseline.ts` (lines 12-22).

**Depends on**: Tasks 1-12 (Tiers 1-3 stable)

---

## Task 15: Wire `checkpoint_ref` for session handoffs (Tier 4.2)

**Files**:
- `openplanter-desktop/crates/op-tauri/src/commands/session.rs` (turn record writing)
- Handoff export/import commands

When a handoff is exported, write a `checkpoint_ref` into the most recent turn record. When resumed, set `continuity.mode: "imported"` and `continuity.checkpoint_ref`.

**Depends on**: Tasks 1-12

---

## Task 16: Event detail inspector UI (Tier 4.3)

**Files**: New frontend component

Add a collapsible event inspector panel that opens when clicking a `source_ref` or `event_id` link. Shows full v2 event envelope as formatted JSON, highlights provenance fields, provides copy/view actions.

**Depends on**: Task 9

---

## Task 17: Ontology-backed session objects (Tier 4.4)

**Files**:
- `agent/investigation_state.py`
- New Rust module for investigation state reading/writing

Promote `Question`, `Claim`, `Evidence`, `Task` objects from `investigation_state.json` (already defined with entities, claims, evidence, questions, tasks dicts) to graph-queryable ontology objects. On turn completion, project typed objects into the wiki knowledge graph.

**Depends on**: All of Tiers 1-3

---

## Execution Strategy

**Parallel Wave 1** (no dependencies):
- Tasks 1, 3, 4, 7, 8

**Wave 2** (after Wave 1):
- Task 2 (needs 1)
- Task 5 (needs 4)

**Wave 3** (after Wave 2):
- Task 6 (needs 5)
- Task 9 (needs 1, 2)

**Wave 4** (after Wave 3):
- Task 10 (needs 6)
- Task 11 (needs 5, 8)
- Task 13 (needs 7)

**Wave 5** (after Wave 4):
- Task 12 (needs 11)

**Wave 6 -- Tier 4** (after Tiers 1-3 stable):
- Tasks 14, 15, 16, 17

**Verification at each tier boundary**: `cargo build`, `cargo test`, frontend build, Python test suite.
