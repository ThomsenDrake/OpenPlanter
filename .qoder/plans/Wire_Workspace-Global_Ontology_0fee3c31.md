# Wire Workspace-Global Ontology Into Agent Context

## Background

The workspace-global ontology at `.openplanter/ontology.json` is fully implemented in `defrag.py` — it merges entities across all sessions with `source_sessions` tracking and `by_investigation` indexing. However, the running agent never sees it. Five gaps must be closed.

---

## Task 1: Extend retrieval to index workspace ontology

**File**: `agent/retrieval.py`

Modify `_collect_ontology_documents()` (lines 802-812) to also load objects from the workspace-global ontology at `.openplanter/ontology.json`, in addition to the session-scoped `investigation_state.json`.

- Read `.openplanter/ontology.json` if it exists
- Convert its entities, claims, evidence, questions, hypotheses, and links into `SourceDocument` objects using the existing `_ontology_documents_from_investigation_state()` helper (or a parallel helper that handles the workspace schema)
- Tag each workspace-ontology document with metadata `"scope": "workspace"` and its `source_sessions` list, so the agent can distinguish workspace-global hits from session-local ones
- Session-scoped documents remain tagged `"scope": "session"`
- Deduplicate: if the same object_id appears in both session and workspace ontology, prefer the session copy (fresher) and skip the workspace duplicate

This is the highest-impact change — it makes cross-investigation entities discoverable through the existing retrieval pipeline with zero changes to the engine or packet format.

**Done criteria**: `retrieval_packet.hits.ontology_objects` includes workspace-global objects tagged with `scope: "workspace"`.

---

## Task 2: Surface workspace ontology summary in question reasoning packet

**File**: `agent/investigation_state.py`

Extend `build_question_reasoning_packet()` (lines 273-423) to accept an optional `workspace_ontology` parameter (the parsed `.openplanter/ontology.json` dict).

When provided, append a `cross_investigation_context` section to the returned packet:

```python
"cross_investigation_context": {
    "available": True,
    "total_entities": len(ontology.get("entities", {})),
    "total_claims": len(ontology.get("claims", {})),
    "source_sessions": ontology.get("source_sessions", []),
    "investigations": list(ontology["indexes"]["by_investigation"].keys()),
}
```

This is lightweight metadata — not the full ontology dump — so the agent knows cross-investigation data exists and can request it via retrieval.

**Caller update** in `agent/runtime.py` (line 954): Load workspace ontology and pass it:

```python
ws_ontology_path = self.store.workspace / ".openplanter" / "ontology.json"
ws_ontology = json.loads(ws_ontology_path.read_text()) if ws_ontology_path.exists() else None
question_reasoning_packet = build_question_reasoning_packet(typed_state, workspace_ontology=ws_ontology)
```

**Done criteria**: Question reasoning packet includes `cross_investigation_context` when ontology.json exists.

---

## Task 3: Add active investigation tracking to session context

**Files**: `agent/runtime.py`, `agent/investigation_state.py`

The session's `objective` already captures what the user is investigating, but there's no formal `investigation_id` linking it to the ontology's `by_investigation` index.

- In `SessionStore.open_session()` (runtime.py), derive an `investigation_id` from the session metadata or allow it to be passed explicitly. Store it in the session's typed state under a new top-level field `active_investigation_id`.
- In `investigation_state.py`, add `active_investigation_id` to the default state schema (lines 73-106) with default value `None`.
- When `build_question_reasoning_packet()` receives the workspace ontology and `active_investigation_id` is set, include a `related_entities` list — entity IDs from the workspace ontology that share the same investigation, capped at 20 entries to keep the packet bounded.

**Done criteria**: Sessions have an `active_investigation_id` that connects to the ontology's `by_investigation` index.

---

## Task 4: Update system prompt with ontology guidance

**File**: `agent/prompts.py`

Add a new `WORKSPACE_ONTOLOGY_SECTION` (insert after `RETRIEVAL_SECTION`, around line 457):

```
## Workspace-Global Ontology

A workspace-global ontology at `.openplanter/ontology.json` consolidates entities,
claims, evidence, and questions across ALL investigation sessions. When the retrieval
packet includes ontology hits with `scope: "workspace"`, these are cross-investigation
objects discovered from other sessions — use them to:

- Identify entities that appeared in prior investigations
- Trace evidence chains across sessions via `source_sessions` metadata
- Detect contradictions between sessions' claims about the same entity
- Avoid re-discovering facts already established in earlier work

The `cross_investigation_context` section of the question reasoning packet shows
how many cross-investigation entities and claims are available. Use retrieval to
pull specific objects when cross-investigation context would help answer a question.

Your session has an active investigation context. Prioritize objects from your
active investigation but leverage workspace-wide objects when they provide
relevant evidence or context.
```

Wire this section into `build_system_prompt()` (lines 494-512) — always included (not conditional).

**Done criteria**: System prompt explains workspace ontology and how to use cross-investigation hits.

---

## Task 5: Auto-sync session state into workspace ontology on finalization

**Files**: `agent/defrag.py`, `agent/runtime.py`

Add an incremental sync function to `defrag.py`:

```python
def sync_session_to_workspace_ontology(
    workspace: Path,
    session_id: str,
    session_state: dict,
) -> None:
```

This performs a lightweight merge of a single session's state into the existing `ontology.json` — much faster than a full defrag. It:

1. Loads existing `ontology.json` (or creates empty workspace ontology if none exists)
2. Merges the session's entities/claims/evidence/questions/hypotheses/links using the existing `_merge_ontology_objects()` helper
3. Adds session_id to `source_sessions` if not already present
4. Rebuilds indexes via `_rebuild_ontology_indexes()`
5. Writes updated `ontology.json`

Call this from `runtime.py` session finalization (around line 1127-1131), after `_persist_state()`:

```python
try:
    self._persist_state()
    typed_state = self.store.load_typed_state(self.session_id)
    sync_session_to_workspace_ontology(self.store.workspace, self.session_id, typed_state)
except OSError:
    pass
```

**Done criteria**: After each session completes, its ontology contributions are merged into the workspace ontology automatically.

---

## Task 6: Write tests for ontology wiring

**File**: `tests/test_defrag.py` (extend existing), possibly `tests/test_retrieval.py` or new test file

Test cases:
- `test_retrieval_includes_workspace_ontology_objects` — retrieval collects from ontology.json
- `test_retrieval_workspace_objects_tagged_with_scope` — scope metadata is set correctly
- `test_retrieval_deduplicates_session_over_workspace` — session copy wins
- `test_question_packet_cross_investigation_context` — packet includes context when ontology exists
- `test_question_packet_no_ontology` — graceful when ontology.json absent
- `test_active_investigation_id_in_state` — field exists in default state
- `test_sync_session_to_workspace_ontology` — incremental merge works
- `test_sync_creates_ontology_if_missing` — handles first-session case
- `test_sync_deduplicates_entities` — entity dedup on incremental sync
- `test_prompt_includes_ontology_section` — system prompt contains ontology guidance

---

## Execution Order

```
Task 1 (retrieval)  ──┐
Task 2 (q-packet)   ──┤── can run in parallel (independent modules)
Task 3 (investigation ID) ─┘
         │
Task 4 (prompt) ── after Task 1-3 (references their outputs in guidance)
Task 5 (auto-sync) ── after Task 1-3 (uses helpers, touches runtime.py)
Task 6 (tests) ── after all implementation tasks
```

Tasks 1, 2, and 3 are independent and can be parallelized. Tasks 4 and 5 depend on 1-3. Task 6 depends on all.
