# Workspace Defrag Feature

## Architecture Decision

The defrag feature will be implemented as:
1. **A core defrag module** (`agent/defrag.py`) containing all defrag logic
2. **A built-in agent tool** so the agent can invoke defrag during sessions
3. **A CLI entry point** so users can run `python -m agent defrag` directly

The defrag operation runs in phases: Scan -> Analyze -> Plan -> Execute -> Report. It supports a `dry_run` mode that reports what would change without modifying anything.

---

## Task 1: Create the core defrag module (`agent/defrag.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/defrag.py` (new)

Implement a `WorkspaceDefrag` class with these phases:

### Phase 1 — Scan
- Walk the workspace directory (excluding `.git`, `__pycache__`, `node_modules`, `.openplanter/sessions`)
- Fingerprint every file via SHA256 (reuse pattern from `retrieval.py`)
- Build a file manifest: `{path, size, hash, extension, modified_at}`
- Detect text files that contain data (`.md`, `.json`, `.csv`, `.txt`, `.yaml`)

### Phase 2 — Duplicate Detection (LLM-Driven)

Duplicate detection is **LLM-driven, not content-hash-driven**. This catches near-duplicates from failed retry loops, re-runs, and incremental rewrites that differ in timestamps, minor wording, or formatting.

**Pre-filter (fast, no LLM calls):**
- Group files by extension and similar filename stems (e.g., `ANALYSIS_SUMMARY.md` vs `ANALYSIS_SUMMARY_2026-02-27.md`)
- Group files by similar size (within 30% of each other) within the same directory or sibling directories
- Exact content-hash matches are auto-grouped without LLM (obvious duplicates)
- This produces candidate clusters to send to the LLM, avoiding sending every file pair

**LLM Similarity Pass:**
- For each candidate cluster, send the first ~500 chars + last ~200 chars of each file to the LLM as a batch
- Prompt asks the LLM to classify each cluster: `exact_duplicate`, `near_duplicate` (same content, minor variations), `versioned` (same topic, meaningfully different versions to keep), or `unrelated` (false positive from pre-filter)
- For `exact_duplicate` and `near_duplicate` groups, LLM picks the canonical file (most complete/recent version)
- For `versioned` groups, LLM recommends which versions to keep and which are superseded

**Output:**
- Each duplicate group includes: canonical file, duplicates to remove, LLM confidence, and a one-line rationale
- Track total reclaimable space
- Exclude `.openplanter/` internal files from deletion candidates
- User can review the LLM's decisions in the report before committing (dry_run default)

### Phase 3 — Un-ingested Data Detection
- Load the wiki index (`wiki_graph.py` `WikiGraph`) and get the set of known source paths
- Scan workspace for `.md` and `.json` files NOT referenced in the wiki index
- Classify un-ingested files by likely category using filename/path heuristics:
  - Files containing "investigation", "analysis", "summary" -> investigation artifacts
  - Files containing "foia", "prr" -> government records
  - JSON files with structured data -> data artifacts
  - Other markdown -> general notes
- For each un-ingested file, extract a title (first `#` heading for .md, or filename) and generate a candidate wiki entry

### Phase 4 — Wiki Ingestion
- For each candidate wiki entry, create the appropriate category directory under `.openplanter/wiki/` if needed
- Write/copy the source file into the wiki structure
- Update `.openplanter/wiki/index.md` with new entries in the appropriate category table
- Rebuild the wiki graph cross-references via `WikiGraph.rebuild()`

### Phase 5 — Ontology Sync (Workspace-Global)

The ontology layer is **workspace-global, not session-scoped**. All investigations share a single unified ontology at `.openplanter/ontology.json`. Individual sessions specify an active investigation context (scoping what the agent focuses on), but the agent always has read/write access to the full ontology.

**Unified ontology file**: `.openplanter/ontology.json`
- Merges entities, claims, evidence, questions, hypotheses, links, and provenance from ALL session states
- Each object retains a `source_sessions: list[str]` field tracking which session(s) contributed it
- Objects are keyed by stable IDs; cross-session duplicates are merged by name/label matching

**Defrag ontology sync steps:**
- Load all session states from `.openplanter/sessions/*/state.json`
- Merge into the workspace-global ontology, deduplicating entities by name/type (LLM-assisted for fuzzy matches)
- Identify and merge duplicate entities across sessions (same entity discovered independently in different investigations)
- Resolve conflicting claims: keep both with provenance, flag contradictions
- Rebuild global indexes (`by_external_ref`, `by_tag`, `by_investigation`)
- Add a `by_investigation` index mapping investigation IDs to their constituent object IDs, so sessions can scope queries
- Re-project the full ontology to wiki graph via `project_to_wiki_graph()`
- Write updated `.openplanter/ontology.json`

### Phase 6 — Cleanup
- Delete duplicate files (non-canonical copies), with a backup manifest written first
- Remove empty directories left behind
- Generate before/after statistics report

### Data Structures

```python
@dataclass
class DefragReport:
    workspace_path: Path
    timestamp: str
    dry_run: bool
    files_scanned: int
    total_size_bytes: int
    duplicates_found: int
    duplicate_groups: list[DuplicateGroup]
    space_reclaimable_bytes: int
    files_deleted: int
    space_reclaimed_bytes: int
    un_ingested_files: list[UnIngestedFile]
    files_ingested: int
    wiki_entries_added: int
    entities_merged: int
    indexes_rebuilt: bool
    errors: list[str]

@dataclass
class DuplicateGroup:
    classification: str          # "exact_duplicate", "near_duplicate", "versioned"
    canonical: Path              # Best/most complete version to keep
    duplicates: list[Path]       # Files to remove
    keep: list[Path]             # For "versioned": additional files worth keeping
    size_bytes: int              # Total reclaimable bytes
    confidence: float            # LLM confidence 0.0-1.0
    rationale: str               # One-line LLM explanation

@dataclass
class UnIngestedFile:
    path: Path
    suggested_category: str
    suggested_title: str
    size_bytes: int
    ingested: bool
```

---

## Task 2: Register the defrag tool definition (`agent/tool_defs.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/tool_defs.py`

Add a new tool definition to `TOOL_DEFINITIONS`:

```python
{
    "name": "defrag_workspace",
    "description": "Scan and optimize the workspace: detect duplicate files, ingest un-indexed data into the wiki and ontology, merge duplicate entities, and clean up structure. Returns a before/after report.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["full", "scan_only", "dedup", "ingest", "cleanup"],
                "description": "Operation mode: 'full' runs all phases, 'scan_only' reports without changes, 'dedup' removes duplicates only, 'ingest' ingests un-indexed files into wiki only, 'cleanup' removes duplicates and empty dirs"
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, report what would change without modifying anything. Defaults to false."
            }
        },
        "required": ["mode"],
        "additionalProperties": False
    }
}
```

Place it in the recon/artifact tool section so it's available in normal agent execution (not delegation-only mode).

---

## Task 3: Wire tool dispatch in engine and tools (`agent/tools.py`, `agent/engine.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/tools.py`

Add a `defrag_workspace` method to `WorkspaceTools`:

```python
def defrag_workspace(self, mode: str = "full", dry_run: bool = False) -> str:
    from .defrag import WorkspaceDefrag
    defrag = WorkspaceDefrag(
        workspace=self.root,
        wiki_dir=self.root / ".openplanter" / "wiki",
        sessions_dir=self.root / ".openplanter" / "sessions",
    )
    report = defrag.run(mode=mode, dry_run=dry_run)
    return report.to_summary()
```

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/engine.py`

Add dispatch case in `_apply_tool_call()`:

```python
elif name == "defrag_workspace":
    obs = self.tools.defrag_workspace(**args)
    return False, obs
```

Classify `defrag_workspace` as an artifact-phase tool (it modifies workspace).

---

## Task 4: Add CLI entry point (`agent/__main__.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/__main__.py`

Add a `defrag` subcommand that can be run directly:

```bash
python -m agent defrag [workspace_path] [--mode full|scan_only|dedup|ingest|cleanup] [--dry-run]
```

This invokes `WorkspaceDefrag.run()` directly without starting the agent loop.

---

## Task 5: Write tests (`tests/test_defrag.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/tests/test_defrag.py` (new)

Test cases:
- **test_scan_finds_all_files**: Create temp workspace with known files, verify manifest
- **test_duplicate_detection_exact**: Create files with identical content, verify auto-grouped as exact_duplicate without LLM
- **test_duplicate_detection_near**: Create files with minor variations (timestamps, whitespace), mock LLM to return near_duplicate, verify grouping
- **test_duplicate_detection_versioned**: Create meaningfully different versions of same topic, mock LLM to return versioned with keep list
- **test_duplicate_prefilter_clustering**: Verify pre-filter groups by filename stem and size similarity
- **test_duplicate_llm_prompt_construction**: Verify correct file snippets sent to LLM (first 500 + last 200 chars)
- **test_un_ingested_detection**: Create wiki index with some files, add others outside wiki, verify detection
- **test_wiki_ingestion**: Verify new entries added to index.md and files copied to wiki dir
- **test_entity_dedup**: Create investigation state with duplicate entities, verify merge
- **test_ontology_cross_session_merge**: Create multiple session state.json files with overlapping entities, verify merged into single ontology.json
- **test_ontology_by_investigation_index**: Verify by_investigation index maps investigation IDs to their objects
- **test_ontology_source_sessions_tracking**: Verify merged objects retain source_sessions provenance
- **test_dry_run_no_changes**: Verify dry_run mode reports changes but modifies nothing
- **test_mode_scan_only**: Verify scan_only mode collects stats without modifications
- **test_mode_dedup_only**: Verify only duplicates removed, no ingestion
- **test_mode_ingest_only**: Verify only ingestion, no deletions
- **test_cleanup_empty_dirs**: Verify empty directories removed after dedup
- **test_tool_definition_valid**: Verify defrag_workspace tool def schema
- **test_tool_dispatch**: Verify engine dispatches to defrag_workspace correctly

---

## Task 6: Update system prompt guidance (`agent/prompts.py`)

**File**: `/Volumes/SSK SSD/OpenPlanter/agent/prompts.py`

Add a brief mention in the data management section of the system prompt so the agent knows when to use defrag:

```
When a workspace accumulates redundant files, un-indexed artifacts, or duplicate data,
use the defrag_workspace tool to consolidate. Run with mode="scan_only" first to preview,
then mode="full" to execute. Always review the report before proceeding with analysis.
```

---

## Dependency Graph

```
Task 1 (core module) ──┬──> Task 3 (tool dispatch wiring)
                       ├──> Task 4 (CLI entry point)
                       └──> Task 5 (tests)
Task 2 (tool def)     ──┬──> Task 3 (tool dispatch wiring)
                        └──> Task 5 (tests)
Task 3 (dispatch)     ───> Task 6 (prompt update)
```

Tasks 1 and 2 can run in parallel.
Task 3 depends on both 1 and 2.
Tasks 4 and 5 depend on Task 1 (and 5 also on 2).
Task 6 depends on Task 3.

---

## Verification Plan

- All new tests in `test_defrag.py` pass
- Existing tests remain green (216 tests baseline)
- `python -m agent defrag --help` prints usage
- `python -m agent defrag /path/to/workspace --mode scan_only` produces a report without modifications
- Tool definition passes schema validation in `test_tool_defs.py`
