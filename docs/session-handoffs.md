# Session Handoffs

This document defines the durable investigation checkpoint artifact used by the desktop export/import path.

The current implementation stays narrow on purpose:

- it projects from existing session durability files instead of introducing a second persistence model
- it lives under `openplanter-desktop`
- it focuses on stable resume/review snapshots for investigation work

## Package

- Format: `openplanter.session_handoff.v1`
- Schema version: `1`
- Default export path: `.openplanter/sessions/<session_id>/artifacts/handoffs/<handoff_id>.json`
- Import path normalization: the package is copied into the target session's `artifacts/handoffs/` directory

Each handoff package contains:

- `objective`
- `open_questions`
- `candidate_actions`
- `evidence_index`
- `replay_span`
- `source`
- `provenance`
- `compat`

## Field Shape

`source` captures the stable turn/session anchor for the snapshot:

- `session_id`
- optional `turn_id`
- optional `turn_index`
- optional `turn_line`
- optional `status`
- optional `started_at`
- optional `ended_at`
- optional `event_span`
- optional `continuity_mode`
- optional `session_status`

`provenance` keeps the package aligned with the session trace contract:

- `source_refs`
- `evidence_refs`
- `ontology_refs`

The handoff preserves `open_questions`, `candidate_actions`, and `evidence_index` directly from the typed reasoning packet so later ontology-native consumers do not need a lossy remap.

## Export

`export_session_handoff(session_id, turn_id?)`

Export:

- reads `metadata.json`, `turns.jsonl`, `replay.jsonl`, and `investigation_state.json`
- prefers the requested turn when provided
- otherwise prefers `metadata.last_turn_id`, then the last turn record
- falls back to the replay stream when no turn replay span is available
- writes the normalized handoff artifact under `artifacts/handoffs/`
- appends audit events for the exported artifact

## Import

`import_session_handoff({ package_path, target_session_id?, activate_session? })`

Import:

- validates schema version, package format, and replay span ordering
- imports into an existing session or creates a new target session when none is supplied
- stores a normalized copy under the target session's `artifacts/handoffs/`
- updates target session metadata with `continuity_mode = "imported"` and the handoff objective
- appends a curator replay note so the imported checkpoint is visible in review surfaces
- can activate the imported session unless an agent task is currently running

## Ontology-First Alignment

This artifact is a durable transport layer, not a parallel investigation state. The snapshot stays aligned with the ontology-first direction by:

- reusing the typed question reasoning packet
- keeping evidence references and ontology references alongside the handoff
- anchoring the package to turn provenance and replay spans from the session trace contract

## Current Limits

- import persists and annotates the handoff, but it does not yet wire `checkpoint_ref` into future turns
- export/import currently packages a single selected turn snapshot, not a multi-turn range
- provenance references are best-effort projections from existing turn outputs and evidence metadata
