# Investigation: Session Traces vs Vision

## Summary

OpenPlanter already behaves like a serious long-form investigation system, not a toy chat app. The trace corpus shows users running deep, multi-turn research sessions with heavy file reads, long synthesis writes, curator updates, and resumable session histories. The main gap is not lack of telemetry. It is that the telemetry is split across two incompatible session contracts and only a thin slice is surfaced in the UI.

That matters because `VISION.md` promises an ontology-first platform with shared graphs, maps, timelines, grounded AI, audit logging, and provenance. Today, OpenPlanter has the raw ingredients for that promise, but the session layer is still closer to "logs plus post-hoc summaries" than "ontology as the universal API."

## Corpus Snapshot

- I inspected 27 real session directories under `freebee-investigation/.openplanter/sessions/`.
- 10 sessions use legacy metadata keys: `session_id`, `workspace`, `created_at`, `updated_at`.
- 17 sessions use desktop metadata keys: `id`, `created_at`, `turn_count`, `last_objective`.
- 13 sessions contain both `events.jsonl` and `replay.jsonl`.
- 9 sessions contain `replay.jsonl` but no `events.jsonl`.
- 2 sessions contain `events.jsonl` but no `replay.jsonl`.
- 3 sessions have neither `events.jsonl` nor `replay.jsonl`, only metadata.
- Across the sessions that do have events, I saw 3316 `trace` events, 1572 `step` events, 57 `objective` events, 51 `result` events, and 22 `session_started` events.

## Concrete Trace Patterns

### 1. Users are running long, iterative investigations

The strongest sessions are not short prompts. They are deep evidence-gathering loops with many step summaries and big write operations.

- `freebee-investigation/.openplanter/sessions/20260311-223418-f70fbbcf/replay.jsonl:1-16` shows a multi-turn investigation session with repeated `step-summary` entries, explicit tool call traces, and long synthesis writes.
- Session `20260226-210523-84c1ba` logged 2664 events and 321 replay lines.
- Session `20260220-191025-f2b099` logged 1178 events and 157 replay lines.

Interpretation: OpenPlanter is already being used more like an investigative workbench than a terminal wrapper. The product should lean into durability, handoffs, and evidence navigation instead of optimizing only for single-turn polish.

### 2. The product has split into two trace eras

Legacy sessions and desktop sessions record different metadata and different notions of replay.

- Legacy metadata example: `freebee-investigation/.openplanter/sessions/20260220-151132-925540/metadata.json:1-6`
- Desktop metadata example: `freebee-investigation/.openplanter/sessions/20260311-172148-e9bb0a17/metadata.json:1-6`
- Legacy Python replay logger writes `header` and `call` records with conversation IDs and exact provider payload context: `agent/replay_log.py:38-46`, `agent/replay_log.py:90-116`.
- Desktop Rust replay logger writes `ReplayEntry` records with roles like `user`, `step-summary`, `assistant`, and `curator`: `openplanter-desktop/crates/op-core/src/session/replay.rs:11-38`.

Interpretation: OpenPlanter currently has two incompatible ideas of what a session trace is. That weakens continuity, observability, and tooling.

### 3. Reliability failures hit even trivial tasks

The earliest sample sessions failed on a one-line objective.

- `freebee-investigation/.openplanter/sessions/20260220-151132-925540/events.jsonl:1-6` shows `"Reply with exactly: OK"` ending in an HTTP 429 model error and a failed result event.

Interpretation: users will judge trust long before they appreciate the ontology model. Reliability and graceful degradation are product features here, not just infra hygiene.

### 4. OpenPlanter already captures richer state than the UI reveals

The session system stores session metadata, state, investigation state, events, replay, and artifacts.

- Python session store paths: `agent/runtime.py:85-105`
- Python event append path: `agent/runtime.py:286-295`
- Python solve logs `objective`, `trace`, `step`, and patch artifacts: `agent/runtime.py:473-533`
- Desktop bridge also logs `trace`, `step`, `artifact`, `assistant`, `assistant-cancelled`, and `result`: `openplanter-desktop/crates/op-tauri/src/bridge.rs:452-456`, `openplanter-desktop/crates/op-tauri/src/bridge.rs:536-616`, `openplanter-desktop/crates/op-tauri/src/bridge.rs:657-747`

Interpretation: the main opportunity is not "collect more data." It is "turn existing session evidence into navigable, trustworthy product surfaces."

### 5. The overview layer is useful but provenance is still shallow

The overview synthesizes focus questions, candidate actions, gaps, and recent revelations, but revelation provenance is limited.

- The typed reasoning packet already produces unresolved questions, supported and contested findings, evidence indexes, and candidate actions: `agent/investigation_state.py:235-385`
- The overview builds recent revelations from replay roles such as `curator`, `step-summary`, and `assistant`: `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs:1082-1155`
- The final overview object simply attaches those synthesized revelations: `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs:1165-1192`
- The frontend renders only timestamp, source, and optional step number for a revelation: `openplanter-desktop/crates/op-core/src/events.rs:233-249`, `openplanter-desktop/frontend/src/components/OverviewPane.ts:458-475`

Interpretation: the product is already generating executive summaries, but users still cannot reliably jump from a claim to the exact replay entry, event line, artifact, or ontology object that supports it.

### 6. The graph session feature is promising but still session-local and presentation-only

- Session baselining captures a set of node IDs once and then filters the graph to only "new" nodes plus their 1-hop neighbors: `openplanter-desktop/frontend/src/graph/sessionBaseline.ts:3-29`, `openplanter-desktop/frontend/src/graph/cytoGraph.ts:585-631`

Interpretation: this is a strong UX seed. It hints at a powerful product direction: session-aware investigative diffs. But right now it is a display trick, not a durable ontology-level change model.

## What The Traces Say About Actual Use

### OpenPlanter is being used as an investigation memory engine

The most valuable thing in the traces is continuity. Sessions are not just execution logs. They are the skeleton of a durable investigation narrative. The replay history shows repeated synthesis, recursive review, wiki updates, and follow-up objectives that build on prior work.

### Users value curated progress more than raw token streams

The later sessions center on `step-summary` and `curator` entries rather than low-level trace spam. That is a strong signal that the right default product surface is "curated replay with drill-down," not "raw trace console first."

### Users are performing analysis across artifacts, not just asking questions

The trace corpus repeatedly shows reading many files, generating large markdown outputs, updating wiki pages, and persisting patch artifacts. This supports the idea that OpenPlanter should present investigations as evolving evidence graphs with outputs, not just chats with attachments.

## Where Current Behavior Misses The Vision

`VISION.md` says OpenPlanter should win through integration: ontology, visualization, grounded AI, actions, audit logging, and provenance all operating through one semantic layer.

- The vision calls for a unified semantic layer and exploration through graphs, maps, and timelines: `VISION.md:27-31`
- It explicitly states "Ontology-First" and requires audit logging and data provenance from day one: `VISION.md:141-148`
- It frames the differentiator as a unified workspace where graph, map, timeline, charts, and AI all share one ontology: `VISION.md:456-464`

Current mismatch:

- Session metadata is split across two schemas instead of a shared contract.
- Replay is split across two different formats instead of one durable event model.
- Revelation provenance stops at source and step number instead of supporting exact evidence jumps.
- Session diffing exists only as a frontend baseline, not as ontology-level change tracking.
- The reasoning packet is rich, but it is mainly used to synthesize the overview rather than drive the full end-to-end session model.

Inference: OpenPlanter is closest to the vision when it behaves like a durable investigative operating system. It is furthest from the vision when it behaves like a terminal session recorder with clever summaries on top.

## Highest-Leverage Improvements

### Next

1. Unify the session contract across Python and desktop.
2. Require a minimum durable per-turn record: objective, continuity policy, step summary, final result or error, artifact references.
3. Add evidence-linked overview cards so every revelation can open the exact replay entry, event, patch artifact, or wiki update that produced it.
4. Expose reliability state explicitly: rate limit, timeout, cancelled, degraded retrieval, resumed-from-partial.
5. Make session history browseable as curated replay by default, with raw logs as drill-down.

Why this is first: it addresses the biggest trust and coherence gaps without requiring a full ontology rewrite.

### Later

1. Persist ontology-native session objects at turn time: question, claim, gap, action, evidence, provenance node, artifact.
2. Turn "new this session" into durable ontology change sets instead of baseline-only node filtering.
3. Add handoff packages that bundle objective, open questions, evidence index, candidate actions, and replay span.
4. Add branch and checkpoint semantics so investigations can fork and later merge.

Why this is second: it turns traces from logs into actual ontology-backed collaboration primitives.

### Much Later

1. Add tamper-evident append chains for replay and event logs.
2. Add policy-governed provenance attestations for regulated and air-gapped environments.
3. Add real multi-user concurrent investigation sessions with merge conflict handling at the ontology layer.

Why this is later: it is strategically aligned with the vision, but only after the session schema is stable.

## Best Product Bets

### Bet 1: Curated replay should be the main interface

The traces say the most useful unit is not a token stream. It is the step summary plus its evidence. Make "investigation replay" a first-class screen.

### Bet 2: Reliability UX will buy more trust than a smarter prompt

The trivial `OK` session failed. A visible, resumable, graceful failure model will likely improve user confidence more than another round of prompt tuning.

### Bet 3: Session traces should become ontology events

The vision wants ontology as the universal API. That should include the investigative process itself. Questions, claims, gaps, and evidence are domain objects, not just summary text.

### Bet 4: Handoffs are a differentiator

The corpus already looks like investigative baton-passing. If OpenPlanter can make a session checkpoint portable, reviewable, and resumable, it starts to feel like a true intelligence operating system.

## Evidence Map

- Vision integration and ontology-first posture: `VISION.md:27-31`, `VISION.md:141-148`, `VISION.md:456-464`
- Legacy session storage shape: `agent/runtime.py:85-105`, `agent/runtime.py:286-295`, `agent/runtime.py:473-533`
- Desktop session storage shape: `openplanter-desktop/crates/op-tauri/src/commands/session.rs:18-50`, `openplanter-desktop/crates/op-tauri/src/commands/session.rs:64-73`, `openplanter-desktop/crates/op-tauri/src/commands/session.rs:192-210`
- Desktop replay format: `openplanter-desktop/crates/op-core/src/session/replay.rs:11-38`
- Desktop logging bridge: `openplanter-desktop/crates/op-tauri/src/bridge.rs:452-456`, `openplanter-desktop/crates/op-tauri/src/bridge.rs:536-616`, `openplanter-desktop/crates/op-tauri/src/bridge.rs:657-747`
- Overview synthesis and revelation heuristics: `openplanter-desktop/crates/op-tauri/src/commands/wiki.rs:1082-1192`
- Limited revelation provenance fields: `openplanter-desktop/crates/op-core/src/events.rs:233-249`
- Graph baseline filtering: `openplanter-desktop/frontend/src/graph/sessionBaseline.ts:3-29`, `openplanter-desktop/frontend/src/graph/cytoGraph.ts:585-631`
- Durability and corruption handling in tests: `tests/test_session.py:144-205`, `tests/test_session.py:333-390`, `tests/test_session_complex.py:326-356`, `tests/test_replay_log.py:405-487`
