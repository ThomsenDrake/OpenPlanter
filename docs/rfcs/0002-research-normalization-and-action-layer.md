# RFC 0002: Research Normalization and Action Planning Extensions to `InvestigationState`

- **Status:** Proposed
- **Authors:** OpenPlanter contributors
- **Created:** 2026-03-13
- **Last Updated:** 2026-03-13
- **Depends On:** RFC 0001 (`Typed InvestigationState`)
- **Audience:** Agent/runtime, ontology, and workflow maintainers

## 1. Summary

RFC 0001 established `investigation_state.json` as the canonical persisted session model for ontology-first investigations. This RFC extends that model with two implementation-ready capabilities:

1. **Research normalization**: a deterministic adapter contract for turning heterogeneous research inputs into canonical RFC 0001 state updates.
2. **Action planning**: a deterministic planning contract for turning unresolved questions into ranked, provenance-backed canonical tasks and subsequent executed actions.

This RFC does **not** introduce a second persisted schema for evidence, claims, questions, or actions. The source of truth remains RFC 0001. Stage 5 defines how source-specific ingestion and planning logic project into that canonical state.

## 2. Relationship to RFC 0001

### 2.1 Source of truth

RFC 0001 remains the authoritative persistence contract:

- `investigation_state.json` is the only canonical mutable session state.
- `events.jsonl` and `replay.jsonl` remain immutable append-only traces.
- Python and Rust runtimes MUST persist and read canonical objects using RFC 0001 IDs and top-level collections.

RFC 0002 adds normalization and planning rules for populating these RFC 0001 collections:

- `evidence`
- `claims`
- `questions`
- `tasks`
- `actions`
- `provenance_nodes`
- `confidence_profiles`

### 2.2 No competing top-level records

This RFC intentionally avoids creating new top-level persisted collections such as:

- `next_actions`
- `normalized_evidence`
- `claim_queue`

Instead:

- a **normalized evidence envelope** is an adapter-side contract that compiles into canonical RFC 0001 `evidence`, `provenance_nodes`, and `confidence_profiles`;
- a **next action** is a planner concept that compiles into a canonical RFC 0001 `task`;
- an executed task produces canonical RFC 0001 `actions`.

### 2.3 Terminology mapping

For the rest of this RFC:

- **Evidence envelope** means an adapter-produced intermediate structure before canonical persistence.
- **Canonical evidence** means an entry in `InvestigationState.evidence`.
- **Next action** means a ranked proposed step before admission to state.
- **Task** means the admitted planned step stored in `InvestigationState.tasks`.
- **Action** means an executed step stored in `InvestigationState.actions`.

## 3. Goals

1. Define a single normalization contract that all ingestion paths can implement.
2. Preserve provenance and derivation without introducing a second persistence model.
3. Standardize how freshness, source reliability, and extraction confidence feed RFC 0001 `confidence_profiles`.
4. Standardize how unresolved questions produce canonical `tasks`.
5. Keep the contract deterministic enough that Python and Rust produce the same state shape from the same inputs.
6. Keep the design compatible with the ontology-first product vision: evidence -> claims -> questions -> tasks -> actions.

## 4. Non-goals

- Replacing RFC 0001.
- Defining a storage backend.
- Defining UI pixel details for action queues or lineage views.
- Replacing domain-specific fetchers, extractors, or entity-resolution systems.
- Defining a single universal ranking model beyond the default baseline in this RFC.

## 5. Canonical Extension Rules

### 5.1 Canonical persisted objects

RFC 0002 refines, but does not replace, these RFC 0001 objects:

- `Evidence`
- `Claim`
- `Question`
- `Task`
- `Action`
- `ProvenanceNode`
- `ConfidenceProfile`

### 5.2 Status vocabulary alignment

All runtimes MUST use RFC 0001 status vocabularies when persisting canonical objects.

#### Canonical claim statuses

Claims MUST use:

- `proposed`
- `supported`
- `contested`
- `retracted`

This RFC does **not** introduce `disputed` or `rejected` as canonical claim statuses.

#### Canonical question statuses

Questions MUST use:

- `open`
- `in_progress`
- `blocked`
- `resolved`
- `won't_fix`

This RFC does **not** introduce `abandoned` as a canonical persisted question status. Planner-side abandonment should persist as `won't_fix`.

#### Canonical task statuses

RFC 0001 left `task.status` open-ended. RFC 0002 standardizes research/planning tasks to:

- `open`
- `ready`
- `blocked`
- `running`
- `completed`
- `failed`
- `superseded`
- `won't_do`

Executed `actions` continue to record actual outcome and trace references.

## 6. Research Normalization Contract

### 6.1 Adapter-side envelope

Each ingestion path MUST first normalize source material into a temporary adapter-side envelope. This envelope is not a new persisted top-level object; it is a write contract for producing canonical RFC 0001 state updates.

```yaml
NormalizedEvidenceEnvelope:
  envelope_id: nev_<ULID>

  source:
    kind: [local_file, web_fetch, transcript, api_response, search_result, analyst_note]
    source_uri: <file://... | https://... | api://provider/endpoint | note://session/...>
    title: <best available title>
    publisher: <org/person/system optional>

  content:
    raw_ref: <pointer to immutable raw bytes/blob/artifact>
    normalized_text_ref: <pointer to text projection optional>
    normalized_structured_ref: <pointer to JSON/table projection optional>
    primary_excerpt: <short excerpt for canonical Evidence.content>
    chunks:
      - chunk_id: ch_<ULID>
        kind: [paragraph, table_row, json_path, timestamped_utterance, search_hit]
        locator: <offset/span/xpath/jsonpath/timestamp>
        text: <chunk text>
        hash: <sha256>

  provenance:
    acquisition:
      observed_at: <UTC>
      retrieved_at: <UTC>
      method: <tool name>
      method_version: <semver/git sha>
      request_fingerprint: <hash optional>
      response_fingerprint: <hash optional>
    derivation:
      parent_evidence_ids: [ev_...]
      stage: [decode, ocr, asr, parse, chunk, extract, summarize]
      run_id: <pipeline run id optional>

  freshness:
    published_at: <UTC optional>
    effective_from: <UTC optional>
    effective_to: <UTC optional>
    stale_after: <UTC optional>
    decay_policy: [none, linear, exponential, source_defined]
    recency_score: <0..1>

  reliability:
    source_reliability_score: <0..1>
    extraction_confidence: <0..1>
    corroboration_score: <0..1 optional>
    integrity:
      checksum: <sha256 optional>
      signature_verified: <bool optional>

  extraction:
    entity_mentions: [...]
    relation_mentions: [...]
    claim_hints: [...]

  governance:
    sensitivity: [public, internal, restricted]
    license: <SPDX or source term optional>

  normalization_version: v1
```

### 6.2 Required envelope fields

At minimum, adapters MUST provide:

- `source.kind`
- `source.source_uri`
- `provenance.acquisition.retrieved_at`
- one of:
  - `content.raw_ref`
  - `content.normalized_text_ref`
  - `content.normalized_structured_ref`
- `normalization_version`

### 6.3 Canonical projection into RFC 0001

For each envelope, runtimes MUST project into canonical RFC 0001 state as follows:

| Envelope data | Canonical destination |
| --- | --- |
| `source.kind`, `primary_excerpt`, source refs | `InvestigationState.evidence[ev_*]` |
| acquisition + derivation lineage | `InvestigationState.provenance_nodes[prov_*]` |
| reliability + freshness + corroboration inputs | `InvestigationState.confidence_profiles[conf_*]` |
| extracted entity mentions / relations | `entities` and `links` updates, when confidence threshold is met |
| claim hints or verified assertions | `claims` updates |
| detected uncertainty | `questions` updates |

### 6.4 Canonical `Evidence` extension fields

RFC 0001 defined `Evidence` at a high level. RFC 0002 standardizes these additive fields inside canonical evidence records:

```yaml
Evidence:
  id: ev_<ULID>
  evidence_type: [document, api_response, tool_output, human_note]
  content: <short normalized excerpt or summary>
  source_uri: <canonical source URI optional>
  artifact_path: <workspace/session artifact path optional>
  event_ref: <events.jsonl ref optional>

  extraction:
    method: <tool/parser/asr/ocr/extractor>
    extractor_version: <semver/git sha>
    span: <primary locator optional>
    modality: [text, html, json, pdf, audio, video, table, mixed]
    normalized_text_ref: <artifact/blob ref optional>
    normalized_structured_ref: <artifact/blob ref optional>
    chunk_refs: [chunk_id...]

  normalization:
    kind: [local_file, web_fetch, transcript, api_response, search_result, analyst_note]
    raw_ref: <artifact/blob ref optional>
    normalization_version: v1 | legacy-v1

  freshness:
    published_at: <UTC optional>
    effective_from: <UTC optional>
    effective_to: <UTC optional>
    stale_after: <UTC optional>
    decay_policy: [none, linear, exponential, source_defined]

  reliability:
    source_reliability_score: <0..1>
    extraction_confidence: <0..1>
    corroboration_score: <0..1 optional>

  governance:
    sensitivity: [public, internal, restricted]
    license: <SPDX or source term optional>

  provenance_ids: [prov_...]
  confidence_id: conf_<...>
```

These fields are additive refinements to RFC 0001, not a second evidence schema.

### 6.5 Broad evidence type mapping

To avoid fragmenting canonical types, adapters MUST map source kinds into RFC 0001 `evidence_type` as follows:

| Source kind | Canonical `evidence_type` | Canonical `normalization.kind` |
| --- | --- | --- |
| `local_file` | `document` | `local_file` |
| `web_fetch` | `document` | `web_fetch` |
| `transcript` | `document` | `transcript` |
| `api_response` | `api_response` | `api_response` |
| `search_result` | `tool_output` | `search_result` |
| `analyst_note` | `human_note` | `analyst_note` |

This preserves a compact canonical evidence taxonomy while retaining source-specific semantics in `normalization.kind`.

## 7. Provenance and Derivation

### 7.1 Canonical provenance nodes

Every canonical evidence record used by claims or questions MUST reference one or more RFC 0001 provenance nodes.

At minimum, each envelope MUST produce:

1. one acquisition provenance node describing the original source observation/fetch;
2. one derivation provenance node when the evidence is derived from prior evidence or transformed content.

### 7.2 Derivation requirements

Derived evidence MUST persist derivation via provenance nodes using RFC 0001 `derived_from_ids[]`.

This requirement applies to:

- OCR output from PDFs/images
- ASR output from audio/video
- extracted chunks from structured or unstructured documents
- search result records derived from a provider response
- summaries or transformed projections used for downstream claim extraction

### 7.3 Search result lineage

Search result evidence MUST remain distinct from fetched-page evidence.

If a search result leads to a later fetch:

- the search result remains canonical evidence;
- the fetched page becomes a second canonical evidence record;
- derivation/provenance links connect the later fetch to the originating search result.

This preserves replayability and ranking provenance.

## 8. Confidence and Freshness Composition

### 8.1 Source of truth

Raw confidence-related signals may live on canonical `Evidence`, but the authoritative merged score for downstream reasoning MUST be the RFC 0001 `confidence_profile` referenced by `confidence_id`.

### 8.2 Required confidence dimensions

The canonical confidence profile produced from normalized evidence MUST include these dimensions when available:

- `source_reliability`
- `extraction_certainty`
- `recency`
- `corroboration`

### 8.3 Default composition rule

Unless an investigation profile explicitly overrides it, runtimes MUST compute:

`score = (0.35 * source_reliability) + (0.30 * extraction_certainty) + (0.20 * recency) + (0.15 * corroboration)`

Rules:

- if a dimension is unavailable, treat it as unknown rather than zero;
- renormalize weights across known dimensions;
- store both the final score and the per-dimension values in the confidence profile.

### 8.4 Freshness semantics

Freshness affects confidence as a weighting factor, not a hard validity switch, unless the source itself defines an explicit validity window.

Default decay policies:

- `none`: historical facts with stable long-term validity
- `linear`: slow decay for routine public records
- `exponential`: rapidly aging operational or news-like data
- `source_defined`: provider-specific explicit staleness rules

Domain-specific presets may be added later, but all runtimes MUST support the same four baseline policies.

## 9. Claims, Questions, and Uncertainty

### 9.1 Claims

Claims generated from normalized evidence MUST persist as RFC 0001 `claims` and MUST follow RFC 0001 invariants:

- `supported` requires at least one support evidence reference;
- `contested` is used when contradictory evidence materially exists;
- `retracted` is used when the claim should no longer participate in active reasoning.

### 9.2 Question creation triggers

Runtimes MUST open or update canonical RFC 0001 questions when any of the following occur:

- an entity remains unresolved after resolution attempts;
- a material claim lacks sufficient supporting evidence;
- support and contradiction evidence materially conflict;
- required freshness threshold is not met for a claim-critical evidence set;
- a task cannot proceed because required inputs are missing.

### 9.3 Canonical question extension fields

RFC 0002 adds these optional question fields:

```yaml
Question:
  origin:
    evidence_ids: [ev_...]
    claim_ids: [cl_...]
    trigger: [missing_evidence, unresolved_entity, contradiction, freshness_risk, dependency_gap]
```

Canonical question priority remains RFC 0001 `priority`:

- `low`
- `medium`
- `high`
- `critical`

## 10. Action Planning as Canonical Tasks

### 10.1 Core rule

A "next action" is a planner concept, not a persisted top-level schema object.

When admitted to canonical state, a next action MUST be persisted as an RFC 0001 `task`. When executed, that task produces one or more RFC 0001 `actions`.

### 10.2 Canonical task planning extension

RFC 0002 standardizes these additive task fields:

```yaml
Task:
  title: <short user-facing action description>
  description: <why this task exists>
  status: [open, ready, blocked, running, completed, failed, superseded, won't_do]
  assignee: [agent, human, system]
  depends_on_task_ids: [task_...]
  produced_ids: [claim_id | evidence_id | entity_id ...]
  consumed_ids: [claim_id | evidence_id | entity_id ...]
  opened_by_question_id: q_<...>

  planning:
    action_type: [
      fetch,
      search,
      extract,
      resolve_entity,
      verify_claim,
      request_human_input,
      external_write,
      monitor
    ]
    required_inputs:
      evidence_ids: [ev_...]
      entity_ids: [ent_...]
      claim_ids: [cl_...]
      external_dependencies: [api_key:provider, tool:ocr_v2]
    payoff:
      uncertainty_reduction: <0..1>
      decision_impact: <0..1>
      graph_expansion_value: <0..1>
      estimated_cost: <normalized scalar or structured estimate>
      payoff_score: <normalized scalar>
    suggested_tools: [web_search, fetch_url, read_file, ...]
    acceptance_criteria:
      - <completion criterion>
    stop_conditions:
      - <stop condition>
    generated_by: <planner component + version>
    generated_at: <UTC>
```

### 10.3 Task readiness

Task readiness rules:

- `ready`: all required inputs and dependencies are available;
- `blocked`: one or more required inputs or dependencies are unresolved;
- `open`: admitted to state but not yet scheduled;
- `running`: currently being executed;
- `completed` / `failed` / `superseded` / `won't_do`: closed outcomes.

Blocked tasks SHOULD include dependency hints in `description` or `planning.required_inputs`.

### 10.4 Default payoff scoring

Unless a profile override exists, planners MUST compute:

`payoff_score = (0.45 * uncertainty_reduction) + (0.35 * decision_impact) + (0.20 * graph_expansion_value) - cost_penalty`

Where:

- `cost_penalty` is normalized from estimated latency, compute, API spend, and human effort;
- payoff is advisory for ranking, not a replacement for policy constraints or explicit human ordering.

## 11. Executed Actions

When a task is executed, runtimes MUST persist canonical RFC 0001 `actions` with:

- `task_id`
- `action_type`
- `started_at`
- `ended_at`
- `outcome`
- `event_refs[]`
- `replay_refs[]`
- `artifact_paths[]`

This is the only canonical record of execution. Planner metadata stays on the task; execution trace stays on actions and append-only logs.

## 12. Source-Specific Adapter Rules

### 12.1 Local files

- MUST produce `normalization.kind=local_file`
- SHOULD fingerprint raw bytes
- SHOULD emit paragraph or structured chunks when feasible

### 12.2 Web fetches

- MUST preserve the final canonical URL in `source_uri`
- SHOULD preserve redirect and HTTP metadata in provenance details
- SHOULD retain raw HTML/PDF bytes plus extracted text projection when possible

### 12.3 Transcripts

- MUST record ASR engine and version in provenance
- SHOULD emit `timestamped_utterance` chunks
- SHOULD persist diarization metadata when available

### 12.4 API responses

- MUST persist request fingerprint and endpoint identity
- SHOULD retain normalized structured projection as the primary representation
- SHOULD capture pagination context when relevant

### 12.5 Search results

- MUST persist each result item as separate canonical evidence
- MUST record provider, rank, and score in provenance or extraction metadata
- MUST remain distinct from follow-up fetch evidence

### 12.6 Analyst notes

Human-authored notes are standardized as:

- `evidence_type=human_note`
- `normalization.kind=analyst_note`
- provenance `source_kind=user_input` or equivalent compatible source

This resolves the earlier ambiguity around modeling notes.

## 13. Workflow Integration

RFC 0002 extends the RFC 0001 lifecycle, not replaces it:

1. **Ingest**: fetch/read/receive source data.
2. **Normalize**: emit `NormalizedEvidenceEnvelope`.
3. **Project**: write canonical evidence, provenance nodes, confidence profiles, and derived entities/claims/questions.
4. **Plan**: rank candidate next actions and admit selected ones as canonical tasks.
5. **Act**: execute tasks and persist canonical actions plus append-only trace references.
6. **Review**: recompute claim status, question status, and confidence after new evidence arrives.
7. **Persist**: atomically update `investigation_state.json`.

## 14. Backward Compatibility and Migration

### 14.1 Legacy adapters

Existing fetch/extract scripts remain valid if they can emit the adapter-side envelope defined here.

### 14.2 Legacy normalization marker

Legacy data MUST use:

- `Evidence.normalization.normalization_version = legacy-v1`

This replaces the ambiguous earlier `normalization_version=legacy` wording.

### 14.3 Migration boundary

Migration still follows RFC 0001:

- legacy records are projected into canonical `investigation_state.json`;
- this RFC only refines how evidence and planning fields are populated during that migration and during native operation.

## 15. Minimal Implementation Plan

### Phase 1: Canonical evidence extension

- Add adapter interfaces that emit `NormalizedEvidenceEnvelope`.
- Extend canonical RFC 0001 `Evidence` writes with `normalization`, `freshness`, `reliability`, and `governance`.
- Extend canonical provenance and confidence writers to support derivation and confidence composition.

### Phase 2: Claim/question projection

- Project extraction output into canonical `claims`, `questions`, `entities`, and `links`.
- Enforce RFC 0001 claim and question vocabularies.

### Phase 3: Task planning

- Add planner that ranks candidate next actions.
- Admit ranked candidates as canonical `tasks` with `planning` metadata.
- Preserve execution traces as canonical `actions`.

### Phase 4: Observability

- Add lineage views for claim -> evidence -> provenance -> raw source.
- Add task diagnostics for blocked inputs, ranking rationale, and payoff fields.

## 16. Acceptance Criteria

This RFC is accepted when:

1. Every ingestion pathway can emit the adapter-side envelope and persist canonical RFC 0001 evidence/provenance/confidence updates.
2. No new competing top-level persisted collection is introduced for normalized evidence or next actions.
3. Every claim persisted from normalized evidence uses RFC 0001 claim statuses and is traceable to canonical evidence plus provenance nodes.
4. Every high/critical open question can produce at least one canonical task with planning metadata, unless explicitly marked `won't_fix`.
5. Executed tasks produce canonical actions with event and replay references.
6. Python and Rust runtimes can project the same source input into materially equivalent canonical state.

## 17. Deferred Questions

The following are intentionally deferred because they do not block the core contract in this RFC:

1. Domain-specific freshness presets beyond the baseline decay policies.
2. Profile-specific payoff weighting beyond the default baseline.
3. Whether search-result deduplication should collapse visually in the UI while remaining distinct canonically in state.
