# Session Change Sets: From Baseline Filter to Durable Ontology Deltas

Date: 2026-03-24
Status: Draft for frontend-safe scaffolding

## Context

`docs/session-trace-deepdive-2026-03-23.md` identified the current graph-level "new this session" experience as a strong UX seed but still a presentation-only diff. `VISION.md` sets a higher bar: OpenPlanter should be ontology-first, provenance-aware, and able to reuse the same semantic change model across graph, overview, replay, timeline, and future action surfaces.

Today the graph session feature works like this:

1. Capture one baseline set of node IDs for the current session generation.
2. On refresh, treat any node outside that baseline as "new this session."
3. Show those new nodes plus their 1-hop neighbors.
4. Hide everything else while the session filter is active.

That gives users a fast answer to "what appeared after I started this session?", but it does not yet create a durable record of what changed or why it changed.

## Problem Statement

The baseline filter is a view heuristic, not a durable change model.

It cannot currently answer:

- What exactly changed during this session after the UI reloads?
- Which delta came from an agent turn, a curator update, a replayed trace, or a merge?
- Which graph highlight maps to a replay span, event line, artifact, or ontology object?
- How should timeline, overview, and graph agree on the same session delta?

That mismatch matters because the session deep dive and the product vision both point toward the same outcome: session history should become a first-class investigative artifact, not just a temporary filter.

## Design Goals

1. Keep the current graph UX stable in this pass.
2. Split semantic change detection from graph rendering affordances.
3. Add low-risk frontend scaffolding for future durable change sets.
4. Avoid backend or Tauri contract changes in this pass.
5. Define a concrete rollout path to ontology-backed, provenance-linked change sets.

## Non-Goals For This Pass

- No backend schema changes.
- No new RPC or Tauri command requirements.
- No change to the existing graph payload shape.
- No persistence requirement yet.
- No changes outside `sessionBaseline.ts`, `cytoGraph.ts`, and this doc.

## Current Behavior And Its Limitation

The current implementation in `sessionBaseline.ts` and `cytoGraph.ts` mixes two concerns:

- Semantic delta: which nodes are newly observed relative to the baseline.
- Render context: which surrounding nodes should stay visible so the new nodes are understandable.

Right now those are both derived inside the graph flow at render time. That is why the feature feels useful but ephemeral: the app knows what is visible, but it does not yet own a durable change object that other surfaces can consume.

## Transitional Model Introduced In This Pass

This pass introduces a frontend-only v0 change-set envelope that remains baseline-derived but establishes the abstraction boundary we need later.

Conceptual shape:

```ts
GraphSessionChangeSetV0 {
  id: string
  version: "graph-session-change-set/v0"
  kind: "baseline-diff"
  generation: number
  capturedAtIso: string
  baselineNodeIds: string[]
  currentNodeIds: string[]
  addedNodeIds: string[]
  removedNodeIds: string[]
}
```

Important constraint:

- `addedNodeIds` and `removedNodeIds` are semantic delta candidates.
- 1-hop context expansion is not part of the semantic change set. It remains a graph rendering concern.

That separation matters because future ontology-backed change sets should describe the change itself, while graph, timeline, and overview can each project that change in different ways.

## Frontend Scaffolding Added In This Pass

### `openplanter-desktop/frontend/src/graph/sessionBaseline.ts`

This module continues to own the existing baseline lifecycle and now also exposes a frontend-safe change-set layer:

- `GraphSessionChangeSet` defines a serializable v0 envelope.
- `computeGraphSessionChangeSet(...)` derives a change set from the current baseline plus a graph snapshot.
- `captureGraphSessionChangeSet(...)` caches the latest derived change set in memory.
- `getGraphSessionChangeSet()` returns a defensive copy.
- Baseline capture and async baseline priming now initialize a zero-delta change set automatically.

Why this is low-risk:

- The baseline capture contract is unchanged.
- No existing caller has to adopt the new helpers yet.
- The cached change set is additive state, not a new dependency.

### `openplanter-desktop/frontend/src/graph/cytoGraph.ts`

This module now separates diff preview from diff application:

- `previewSessionVisibilityDelta(...)` computes the graph-facing view of a baseline-derived diff.
- `filterBySessionDelta(...)` applies a precomputed visibility delta.
- `filterBySession(...)` remains the public compatibility path used by existing callers and now delegates through the shared delta logic.

The graph-facing visibility delta stays deliberately small:

```ts
GraphSessionVisibilityDelta {
  addedNodeIds: string[]
  contextNodeIds: string[]
}
```

Why this boundary matters:

- Future durable change sets can feed the same graph filter path.
- Graph rendering can keep using neighbor expansion without pretending that the neighbors themselves are semantic changes.
- Other surfaces can consume the semantic change set without inheriting graph-specific expansion rules.

## Concrete Rollout Plan

### Phase 0: Baseline Filter UX

Status: already shipped.

- Capture one baseline node snapshot per session generation.
- Highlight newly observed nodes.
- Reveal 1-hop context.

Strength:

- Useful and fast.

Limitation:

- Ephemeral and graph-only.

### Phase 1: Frontend Change-Set Scaffolding

Status: this pass.

- Add an in-memory `GraphSessionChangeSet` envelope.
- Keep graph rendering backwards-compatible.
- Introduce a graph visibility-delta path that can accept precomputed changes later.

Exit criteria:

- No user-facing regression in the graph session toggle.
- No backend changes required.
- The codebase has a clean seam between semantic delta and render context.

### Phase 2: Session-Local Durability Without Contract Breaks

- Capture a fresh change set whenever graph data meaningfully refreshes.
- Store or emit that change set through existing session-local channels such as artifacts or replay-adjacent metadata.
- Surface lightweight counts and timestamps in the UI once the storage path is stable.

Exit criteria:

- "What changed this session?" survives reload/resume where session artifacts survive.
- Graph and overview can read the same derived session delta.

### Phase 3: Replay-Linked Durable Change Sets

- Associate each change set with replay/event/artifact references.
- Add reason codes for how a change entered the graph.
- Support navigation from a highlighted node to the trace evidence that produced it.

Exit criteria:

- A user can jump from a graph-highlighted session change to supporting replay or artifact evidence.
- Change-set ordering is stable within a session.

### Phase 4: Ontology-Backed Session Change Sets

- Promote session change sets from baseline-derived graph snapshots to ontology-addressable records.
- Track object, link, and property deltas rather than node-presence heuristics alone.
- Make graph, timeline, overview, and action layers consume the same semantic contract.

Conceptual target shape:

```ts
SessionChangeSet {
  id: string
  sessionId: string
  turnSpan: { from: string, to: string }
  createdAt: string
  objectDeltas: ObjectDelta[]
  linkDeltas: LinkDelta[]
  propertyDeltas: PropertyDelta[]
  evidenceRefs: EvidenceRef[]
}
```

Exit criteria:

- "New this session" becomes one projection of a broader change-set model.
- The semantic delta is queryable independent of graph rendering.

### Phase 5: Collaboration, Branches, And Handoffs

- Support branch-aware change sets and merge semantics.
- Build handoff packages from selected change-set ranges.
- Add stronger audit and provenance guarantees for regulated environments.

Exit criteria:

- Teams can compare, hand off, and reconcile session changes across investigations.

## Compatibility Guarantees For This Pass

- Existing `filterBySession(...)` behavior remains the same from the user’s perspective.
- The graph still treats "new this session" as "new nodes plus 1-hop context."
- If no new nodes exist, the active session filter still hides all nodes.
- No backend payload or command changes are required.

## Risks And Mitigations

1. Risk: the v0 shape drifts from the eventual persisted contract.
   Mitigation: keep the semantic envelope small and serializable, and keep graph-specific context expansion out of it.

2. Risk: graph behavior regresses while introducing a new abstraction layer.
   Mitigation: keep `filterBySession(...)` as the compatibility API and route it through shared internal helpers.

3. Risk: "session change set" sounds more durable than the current baseline heuristic.
   Mitigation: document the v0 model explicitly as baseline-derived scaffolding and phase the persistence/provenance work separately.

## Verification For This Pass

- Re-read `docs/session-trace-deepdive-2026-03-23.md` and `VISION.md` to keep the design aligned with the ontology-first direction.
- Re-read `sessionBaseline.ts` and `cytoGraph.ts` to confirm the graph/session lifecycle remains consistent with current behavior.
- Run the narrowest relevant frontend checks for the modified graph modules.

