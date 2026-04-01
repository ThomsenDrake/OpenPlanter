# Wire Investigation Context Through All Callers

## Background

`SessionStore.open_session()` already accepts `investigation_id` but no caller passes it. The workspace ontology tracks investigations via `by_investigation` index. We need to:

1. Wire `investigation_id` through the full call chain (Python + Desktop)
2. Add LLM-driven investigation inference when no ID is explicitly provided
3. Let users confirm, change, or create new investigations interactively

---

## Task 1: Wire investigation_id through Python bootstrap chain

**Files**: `agent/runtime.py`, `agent/__main__.py`

### runtime.py

Add `investigation_id` parameter to `SessionRuntime.bootstrap()` (line ~778):

```python
@classmethod
def bootstrap(
    cls,
    engine: RLMEngine,
    config: AgentConfig,
    session_id: str | None = None,
    resume: bool = False,
    investigation_id: str | None = None,  # NEW
) -> "SessionRuntime":
```

Pass it through at line ~793:
```python
sid, state, created_new = store.open_session(
    session_id=session_id, resume=resume, investigation_id=investigation_id
)
```

### __main__.py

Add CLI argument (near line ~200, alongside `--session-id` and `--resume`):
```python
parser.add_argument(
    "--investigation-id",
    help="Investigation ID to associate with the session. If omitted, the agent will infer the investigation from your objective.",
)
```

Pass it at line ~862:
```python
runtime = SessionRuntime.bootstrap(
    engine=engine,
    config=engine.config,
    session_id=args.session_id,
    resume=args.resume,
    investigation_id=investigation_id,  # resolved via Task 2 logic
)
```

**Done criteria**: `--investigation-id` flows from CLI all the way to `investigation_state.json`.

---

## Task 2: Add LLM-driven investigation inference

**Files**: `agent/runtime.py` (new helper), `agent/__main__.py`

When no `--investigation-id` is provided, the system should:

1. **Load available investigations** from `.openplanter/ontology.json` (`indexes.by_investigation` keys) and from session metadata (scan `.openplanter/sessions/*/investigation_state.json` for distinct `active_investigation_id` values and `objective` fields to build a labeled list).

2. **If no investigations exist**, skip inference. Session starts with `active_investigation_id = None` (generic/one-off mode).

3. **If investigations exist**, use the LLM to classify the user's objective against available investigations. Build a prompt like:

```
Given the user's question/objective and the list of existing investigations, determine which investigation this most likely belongs to, or whether it's a new investigation or a one-off query.

User objective: "{objective}"

Available investigations:
1. "{inv_id_1}" - Sessions: {count}, Entities: {count}, Last active: {date}
2. "{inv_id_2}" - Sessions: {count}, Entities: {count}, Last active: {date}
...

Respond with JSON:
{"match": "inv_id_1" | "new" | "generic", "confidence": 0.0-1.0, "reasoning": "..."}
```

4. **Present to user for confirmation** via an interactive prompt (in TUI/CLI) or return suggestion (in API/desktop):

   - "I think this relates to investigation **{name}**. Is that correct?"
   - Options: (a) Yes, proceed (b) No, choose a different investigation (c) Create a new investigation (d) Generic / one-off query

5. If "create new", prompt for an investigation name/ID (or auto-generate from the objective).

### Implementation approach

Add a new module `agent/investigation_resolver.py` with:

```python
@dataclass
class InvestigationChoice:
    investigation_id: str | None  # None = generic/one-off
    is_new: bool
    label: str  # Human-readable name

def list_investigations(workspace: Path) -> list[dict]:
    """Scan ontology and sessions to build investigation catalog."""

async def infer_investigation(
    objective: str,
    investigations: list[dict],
    llm_call: Callable[[str], str],
) -> dict:
    """LLM classifies objective against known investigations."""

def format_investigation_prompt(
    inference_result: dict,
    investigations: list[dict],
) -> str:
    """Format the user-facing confirmation prompt."""
```

Wire this into `__main__.py` `main()` — after the objective is known but before `bootstrap()`:

```python
if not args.investigation_id:
    investigation_id = resolve_investigation(
        workspace=workspace_path,
        objective=objective,
        llm_call=engine.model.generate,  # or appropriate callable
        interactive=True,  # CLI/TUI mode
    )
else:
    investigation_id = args.investigation_id
```

For the TUI (both Rich and Textual), the interactive prompt integrates with the existing input flow.

**Done criteria**: When no `--investigation-id` is passed, the agent infers the investigation, presents its guess, and lets the user confirm/change/create.

---

## Task 3: Wire investigation_id through Tauri/Rust layer

**File**: `openplanter-desktop/crates/op-tauri/src/commands/session.rs`

Update the `open_session` Tauri command (line ~612):

```rust
#[tauri::command]
pub async fn open_session(
    id: Option<String>,
    resume: bool,
    investigation_id: Option<String>,  // NEW
    state: State<'_, AppState>,
) -> Result<SessionInfo, String> {
```

Pass `investigation_id` through to wherever the session state is initialized in the Rust layer. If the Rust layer delegates to Python, pass it as a CLI argument or IPC parameter. If it manages sessions independently, store `active_investigation_id` in the session's investigation state file.

**Done criteria**: Tauri `open_session` command accepts and stores `investigation_id`.

---

## Task 4: Wire investigation_id through TypeScript frontend

**Files**: `openplanter-desktop/frontend/src/api/invoke.ts`, `openplanter-desktop/frontend/src/components/App.ts`

### invoke.ts (line ~81)

```typescript
export async function openSession(
  id?: string,
  resume: boolean = false,
  investigationId?: string,
): Promise<SessionInfo> {
  return invoke("open_session", {
    id: id ?? null,
    resume,
    investigation_id: investigationId ?? null,
  });
}
```

### App.ts call sites

Update both call sites (~lines 140 and 220) to pass `investigationId` from app state. The desktop UI will need an investigation selector component (or can start with passing `undefined` to trigger server-side inference).

For now, pass through from app state if available:

```typescript
// New session
const session = await openSession(undefined, false, this.activeInvestigationId);

// Resume
const resumed = await openSession(sessionId, true);  // Keep investigation from original session
```

**Done criteria**: TypeScript API and frontend callers can pass `investigationId` through to the Tauri backend.

---

## Task 5: Add investigation catalog to settings/workspace

**Files**: `agent/settings.py`, `agent/investigation_resolver.py`

Add `default_investigation_id` to `PersistentSettings` in `agent/settings.py`:

```python
@dataclass(slots=True)
class PersistentSettings:
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    # ... existing fields ...
    default_investigation_id: str | None = None  # NEW
```

In the investigation resolver, when no `--investigation-id` is provided AND no objective-based inference is possible (e.g., no objective yet at session start), fall back to `default_investigation_id` from settings.

**Done criteria**: Workspace settings can specify a default investigation; resolver uses it as fallback.

---

## Task 6: Write tests

**File**: `tests/test_investigation_resolver.py` (new), extend `tests/test_ontology_wiring.py`

Test cases:
- `test_list_investigations_from_ontology` — finds investigations from ontology.json
- `test_list_investigations_empty` — handles no ontology gracefully
- `test_infer_investigation_matches` — LLM returns matching investigation
- `test_infer_investigation_new` — LLM suggests new investigation
- `test_infer_investigation_generic` — LLM suggests one-off/generic
- `test_bootstrap_passes_investigation_id` — bootstrap flows investigation_id to open_session
- `test_cli_investigation_id_arg` — CLI argument is parsed and passed
- `test_default_investigation_from_settings` — fallback to settings default
- `test_resolve_skips_inference_when_explicit` — explicit ID bypasses LLM

---

## Execution Order

```
Task 1 (bootstrap + CLI wiring) ──┐
Task 3 (Tauri/Rust)              ──┤── independent, can parallelize
Task 4 (TypeScript frontend)     ──┘
         |
Task 2 (LLM inference + resolver) ── after Task 1 (needs bootstrap wiring)
Task 5 (settings default)         ── after Task 2 (extends resolver)
Task 6 (tests)                    ── after all implementation tasks
```

Tasks 1, 3, and 4 are independent (different languages/layers). Task 2 depends on Task 1. Task 5 depends on Task 2. Task 6 depends on all.
