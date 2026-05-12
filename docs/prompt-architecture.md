# OpenPlanter Prompt Architecture

OpenPlanter has two runtime prompt stacks: the Python agent runtime and the Rust
desktop core. Shared prompt contracts should stay aligned, while runtime-specific
sections may differ when the available tools or recursion behavior differ.

## Prompt Sources

- `agent/prompts.py` builds the Python runtime system prompt.
- `openplanter-desktop/crates/op-core/src/prompts.rs` builds the Rust runtime system prompt.
- `agent/engine.py` and `openplanter-desktop/crates/op-core/src/engine/mod.rs` contain finalizer rescue prompts and runtime-injected policy messages.
- `agent/investigation_resolver.py` contains the investigation-continuity classifier prompt used before a session is attached to an existing investigation.
- `openplanter-desktop/crates/op-core/src/engine/curator.rs` contains the wiki curator system prompt.
- `agent/tool_defs.py` and `openplanter-desktop/crates/op-core/src/tools/defs.rs` contain tool descriptions shown to models.
- CLI and frontend prompt-like copy lives in command/help surfaces such as `agent/tui.py`, `agent/textual_tui.py`, and `openplanter-desktop/frontend/src/commands/`.

## Shared Contracts

The main system prompts should consistently preserve these contracts:

- Treat the current objective as the controlling scope.
- Final answers must be usable deliverables, not progress notes.
- Distinguish observed facts, computed results, inferences, and proposed next actions.
- Treat turn history, retrieval hits, and candidate actions as bounded context that must be verified before high-confidence use.
- Use durable artifacts for nontrivial investigations, transformations, and report-style deliverables.
- Keep evidence chains explicit and cite source records, provenance IDs, or artifact paths.
- Avoid turning machine-readable `candidate_actions` into lossy prose; preserve IDs, rationale, required sources, expected payoff, evidence gaps, and ontology refs.

## Runtime-Specific Contracts

Some sections intentionally differ:

- Python forced recursion currently requires exactly one `subtask(...)` at the delegation floor.
- Rust forced recursion allows one or more parallel `subtask(...)` calls at the delegation floor.
- Python exposes `defrag_workspace`; Rust currently frames cleanup as optional when a cleanup or defrag tool is available.
- Acceptance-criteria enforcement depends on runtime configuration, so tool schemas and prompt sections must be checked with both enabled and disabled modes.

## Rescue And Curator Prompts

Finalizer rescue prompts run in a separate context with tools disabled. They should only rewrite supplied evidence into a final deliverable. They must not mention rescue machinery, failure labels, rejected candidates, new verification, or new work.

The wiki curator prompt treats `.openplanter/wiki/` as a derived source map, not a transcript store. It may only mutate wiki files, must use exact source names from `index.md`, and should return the exact no-op string when no durable source facts are present.

The investigation resolver prompt is a bounded classifier. It must return JSON only, use exact investigation IDs from the supplied catalog, and choose between an existing investigation, `"new"`, or `"generic"` without inventing continuity.

## Testing Expectations

Prompt changes should include focused tests for the behavior they protect:

- Python prompt tests in `tests/test_engine.py`, `tests/test_ontology_wiring.py`, and `tests/test_tool_defs.py`.
- Python finalizer tests in `tests/test_engine_complex.py`.
- Investigation resolver prompt tests in `tests/test_investigation_resolver.py`.
- Rust prompt tests in `openplanter-desktop/crates/op-core/src/prompts.rs`.
- Rust tool and curator tests in `openplanter-desktop/crates/op-core/src/tools/defs.rs` and `openplanter-desktop/crates/op-core/src/engine/curator.rs`.

When changing shared prompt language, update both runtimes in the same patch unless the difference is intentional and documented here.
